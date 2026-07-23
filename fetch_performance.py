"""
Pulls real Instagram performance data for carousels that were auto-posted
at least SCORE_AFTER_DAYS ago, scores them, and rolls the results into
performance_history.json — the file runner.py reads to tell the content
brain which hooks/angles/formats are actually working, not just which
ones haven't been repeated yet.

Runs BEFORE generation in the daily workflow — see .github/workflows/daily.yml.
Safe to run even with zero eligible posts; it just does nothing that day.

Requires posted_log.json, which instagram_post.py writes every time a
carousel is actually published (media_id + niche/angle/format/hook).
"""

import os
import json
import datetime
import requests

IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_GRAPH = "https://graph.instagram.com/v21.0"

POSTED_LOG_PATH = "posted_log.json"
PERFORMANCE_PATH = "performance_history.json"

SCORE_AFTER_DAYS = 3          # let engagement settle before scoring a post
PERFORMANCE_WINDOW_DAYS = 45  # how far back performance_history.json keeps entries

# Weights reflect what actually earns reach on Instagram: saves and shares
# matter far more than likes, comments sit in between. This mirrors the
# priority order already baked into the CTA rules in
# content_brain_system_prompt.txt (saves are "3x weighted by algorithm").
W_LIKE, W_COMMENT, W_SAVE, W_SHARE = 1, 3, 4, 3


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {path}, using default ({e})")
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_metrics(media_id):
    """Returns a dict with reach, saved, shares, likes, comments — or None on failure."""
    try:
        insights_resp = requests.get(
            f"{IG_GRAPH}/{media_id}/insights",
            params={"metric": "reach,saved,shares,total_interactions", "access_token": IG_ACCESS_TOKEN},
            timeout=30,
        )
        insights_resp.raise_for_status()
        insights = {row["name"]: row["values"][0]["value"] for row in insights_resp.json().get("data", [])}

        # like_count / comments_count are standard media fields, not
        # insights metrics — fetched separately since the insights endpoint
        # doesn't reliably expose them for every media type.
        fields_resp = requests.get(
            f"{IG_GRAPH}/{media_id}",
            params={"fields": "like_count,comments_count", "access_token": IG_ACCESS_TOKEN},
            timeout=30,
        )
        fields_resp.raise_for_status()
        fields = fields_resp.json()

        return {
            "reach": insights.get("reach", 0),
            "saved": insights.get("saved", 0),
            "shares": insights.get("shares", 0),
            "likes": fields.get("like_count", 0),
            "comments": fields.get("comments_count", 0),
        }
    except Exception as e:
        print(f"Could not fetch metrics for {media_id}: {e}")
        return None


def score(metrics):
    reach = max(metrics["reach"], 1)
    weighted = (
        metrics["likes"] * W_LIKE
        + metrics["comments"] * W_COMMENT
        + metrics["saved"] * W_SAVE
        + metrics["shares"] * W_SHARE
    )
    return round((weighted / reach) * 100, 3)


def main():
    if not IG_ACCESS_TOKEN:
        print("IG_ACCESS_TOKEN not set — skipping performance fetch.")
        return

    posted_log = load_json(POSTED_LOG_PATH, {"posts": []})
    performance = load_json(PERFORMANCE_PATH, {"scored_posts": []})

    today = datetime.date.today()
    log_updated = False
    performance_updated = False

    for post in posted_log["posts"]:
        if post.get("scored"):
            continue
        if not post.get("date") or not post.get("media_id"):
            continue
        try:
            posted_date = datetime.date.fromisoformat(post["date"])
        except ValueError:
            continue
        if (today - posted_date).days < SCORE_AFTER_DAYS:
            continue  # not enough time has passed to score this one yet

        metrics = fetch_metrics(post["media_id"])
        if metrics is None:
            continue  # try again on the next run

        engagement_rate = score(metrics)
        performance["scored_posts"].append({
            "date": post["date"],
            "media_id": post["media_id"],
            "niche": post.get("niche", ""),
            "angle": post.get("angle", ""),
            "format": post.get("format", ""),
            "hook": post.get("hook", ""),
            "metrics": metrics,
            "engagement_rate": engagement_rate,
        })
        post["scored"] = True
        log_updated = True
        performance_updated = True
        print(f"Scored {post['media_id']} (\"{post.get('hook', '')[:50]}\"): engagement_rate={engagement_rate}")

    if not performance_updated:
        print("No posts were eligible for scoring today.")
        return

    cutoff = (today - datetime.timedelta(days=PERFORMANCE_WINDOW_DAYS)).isoformat()
    performance["scored_posts"] = [p for p in performance["scored_posts"] if p["date"] >= cutoff]

    save_json(PERFORMANCE_PATH, performance)
    if log_updated:
        save_json(POSTED_LOG_PATH, posted_log)


if __name__ == "__main__":
    main()
