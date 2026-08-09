"""
Pulls real Instagram performance data for carousels AND reels that were
auto-posted at least SCORE_AFTER_DAYS ago, scores them, and rolls the results
into performance_history.json — the file runner.py reads to tell the content
brain which hooks/angles/formats are actually working, not just which ones
haven't been repeated yet.

Runs BEFORE generation in the daily workflow — see .github/workflows/daily.yml.
Safe to run even with zero eligible posts; it just does nothing that day.

Requires posted_log.json (written by instagram_post.py) for carousels and
reel_posted_log.json (written by instagram_reel_post.py) for reels.

Carousels land in performance_history.json under "scored_posts" (unchanged);
reels land under "scored_reels". Every existing consumer — runner.py,
performance_report.py, self_improve.py — reads "scored_posts" with .get(), so
the new key is invisible to them until something is written to consume it.

REEL METRIC NAMES (verified against Meta's live docs 2026-08-09, API v26.0,
developers.facebook.com/documentation/instagram-platform/reference/instagram-media/insights):
  - "views" is the play count. "plays" no longer exists on this endpoint — it
    was removed, and deprecated names fail SILENTLY here: the API returns an
    empty data set rather than an error, which reads as a reel with zero
    everything. That is why the metric list below must be re-verified against
    the live docs before ever being edited.
  - Watch time metrics are "ig_reels_avg_watch_time" and
    "ig_reels_video_view_total_time" — plural "reels". The singular variants
    circulating in older blog posts return nothing.
  - "reels_skip_rate" (% of viewers gone inside the first 3 seconds) is marked
    "in development", so it rides in a separate best-effort request where its
    failure cannot poison the core metrics. It is the closest thing Meta
    exposes to a direct hook-quality score.
  - "comments" and "likes" ARE insights metrics for REELS (unlike older media),
    so reels don't need the second media-fields request carousels use.
  - Do NOT add "crossposted_views" or "facebook_views": they THROW when the
    media isn't shared to Facebook, and one bad metric fails the whole request.
"""

import os
import json
import datetime
import requests

IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_GRAPH = "https://graph.instagram.com/v21.0"

POSTED_LOG_PATH = "posted_log.json"
REEL_LOG_PATH = "reel_posted_log.json"
PERFORMANCE_PATH = "performance_history.json"

SCORE_AFTER_DAYS = 3          # let engagement settle before scoring a post
PERFORMANCE_WINDOW_DAYS = 45  # how far back performance_history.json keeps entries

# Weights reflect what actually earns reach on Instagram: saves and shares
# matter far more than likes, comments sit in between. This mirrors the
# priority order already baked into the CTA rules in
# content_brain_system_prompt.txt (saves are "3x weighted by algorithm").
W_LIKE, W_COMMENT, W_SAVE, W_SHARE = 1, 3, 4, 3

# Reels are weighted differently from carousels: sends (shares) per reach is
# the single strongest ranking signal for cold Reels/Explore distribution —
# worth roughly 3-5x a like for reaching non-followers — with saves second.
# At this account size likes are close to noise, so they stay at 1.
W_R_LIKE, W_R_COMMENT, W_R_SAVE, W_R_SHARE = 1, 2, 4, 5

REEL_CORE_METRICS = "reach,views,saved,shares,comments,likes,total_interactions"
REEL_EXTRA_METRICS = "ig_reels_avg_watch_time,ig_reels_video_view_total_time,reels_skip_rate"


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


def _insights(media_id, metric_list):
    resp = requests.get(
        f"{IG_GRAPH}/{media_id}/insights",
        params={"metric": metric_list, "access_token": IG_ACCESS_TOKEN},
        timeout=30,
    )
    resp.raise_for_status()
    return {row["name"]: row["values"][0]["value"] for row in resp.json().get("data", [])}


def fetch_reel_metrics(media_id):
    """Reel-specific insights. Returns a dict, or None if the core call failed.

    Two requests on purpose. The core set is stable, released metrics; the
    extra set (watch time, skip rate) is partly "in development" per Meta's
    docs, and one unsupported metric in a request fails the entire request.
    Losing skip rate on a bad day is fine; losing reach and shares is not.
    """
    try:
        core = _insights(media_id, REEL_CORE_METRICS)
    except Exception as e:
        print(f"Could not fetch reel metrics for {media_id}: {e}")
        return None

    metrics = {
        "reach": core.get("reach", 0),
        "views": core.get("views", 0),
        "saved": core.get("saved", 0),
        "shares": core.get("shares", 0),
        "likes": core.get("likes", 0),
        "comments": core.get("comments", 0),
        "total_interactions": core.get("total_interactions", 0),
    }

    try:
        extra = _insights(media_id, REEL_EXTRA_METRICS)
        # Stored verbatim under their metric names. NOTE: Meta's docs do not
        # state the unit for the watch-time metrics; community reports say
        # milliseconds. Check the first live values against the known reel
        # durations (14.3-17.1s) before deriving retention from them.
        for k in ("ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate"):
            if k in extra:
                metrics[k] = extra[k]
    except Exception as e:
        print(f"Watch-time metrics unavailable for {media_id} (non-fatal): {e}")

    return metrics


def load_manifest_entry(date, index):
    """
    Look up a specific carousel's manifest entry by date+index, so its
    experiment_id/experiment_arm tags (written by runner.py, see
    experiments.json / experiment_loop.py) can be carried over onto the
    scored_posts entry. posts/{date}/manifest.json stays committed in the
    repo permanently, so this works no matter how long ago the post went
    out. Missing manifest or missing tags (older posts, pre-dating this
    feature) just means experiment_id/experiment_arm come back None —
    exactly like any other untagged post.
    """
    path = os.path.join("posts", date, "manifest.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            manifest = json.load(f)
    except Exception:
        return None
    for c in manifest.get("carousels", []):
        if c.get("index") == index:
            return c
    return None


def reel_beat_structure(manifest_entry):
    """Recompute the beat structure a reel was rendered with, from its manifest.

    Reuses reel_engine's own beats_from_carousel()/trim_to_budget() rather than
    duplicating the timing model — the numbers here are the same ones the
    renderer used, not a parallel approximation that would drift. Pure
    computation: no fonts are loaded, no frames rendered.

    This join is what turns scoring into an experiment rather than a
    scoreboard: it lets watch time and sends be read against beat count,
    duration, and whether a proof beat was present.

    Returns None (and the reel still gets scored) if the import or the
    computation fails — e.g. Pillow missing in a local run.
    """
    if not manifest_entry:
        return None
    try:
        import reel_engine
        beats = reel_engine.beats_from_carousel(dict(manifest_entry))
        if not beats:
            return None
        return {
            "beat_count": len(beats),
            "beat_kinds": [b.kind for b in beats],
            "body_beats": sum(1 for b in beats if b.kind == "body"),
            "has_stat": any(b.kind == "stat" for b in beats),
            "has_proof": any(b.kind == "proof" for b in beats),
            "duration_s": round(sum(b.dur for b in beats) + reel_engine.TAIL_S, 2),
        }
    except Exception as e:
        print(f"Could not derive beat structure (non-fatal): {e}")
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


def reel_score(metrics):
    reach = max(metrics["reach"], 1)
    weighted = (
        metrics["likes"] * W_R_LIKE
        + metrics["comments"] * W_R_COMMENT
        + metrics["saved"] * W_R_SAVE
        + metrics["shares"] * W_R_SHARE
    )
    return round((weighted / reach) * 100, 3)


def _eligible(entry, today):
    """Shared gate: unscored, has a media_id and a parseable date old enough to settle."""
    if entry.get("scored"):
        return False
    if not entry.get("date") or not entry.get("media_id"):
        return False
    try:
        posted_date = datetime.date.fromisoformat(entry["date"])
    except ValueError:
        return False
    return (today - posted_date).days >= SCORE_AFTER_DAYS


def score_carousels(posted_log, performance, today):
    updated = False
    for post in posted_log["posts"]:
        if not _eligible(post, today):
            continue

        metrics = fetch_metrics(post["media_id"])
        if metrics is None:
            continue  # try again on the next run

        engagement_rate = score(metrics)
        manifest_entry = load_manifest_entry(post["date"], post.get("index")) or {}
        performance["scored_posts"].append({
            "date": post["date"],
            "media_id": post["media_id"],
            "niche": post.get("niche", ""),
            "angle": post.get("angle", ""),
            "format": post.get("format", ""),
            "hook": post.get("hook", ""),
            "metrics": metrics,
            "engagement_rate": engagement_rate,
            # Design/copy feedback loop tags, if this post was part of an
            # experiment (see experiments.json / experiment_loop.py).
            "experiment_id": manifest_entry.get("experiment_id"),
            "experiment_arm": manifest_entry.get("experiment_arm"),
        })
        post["scored"] = True
        updated = True
        print(f"Scored {post['media_id']} (\"{post.get('hook', '')[:50]}\"): engagement_rate={engagement_rate}")
    return updated


def score_reels(reel_log, performance, today):
    updated = False
    for reel in reel_log:
        if not _eligible(reel, today):
            continue

        metrics = fetch_reel_metrics(reel["media_id"])
        if metrics is None:
            continue  # try again on the next run

        engagement_rate = reel_score(metrics)
        reach = max(metrics["reach"], 1)
        manifest_entry = load_manifest_entry(reel["date"], reel.get("index"))
        performance["scored_reels"].append({
            "date": reel["date"],
            "media_id": reel["media_id"],
            "niche": reel.get("niche", ""),
            "angle": reel.get("angle", ""),
            "format": reel.get("format", ""),
            "hook": reel.get("hook", ""),
            "trial": reel.get("trial", False),
            "metrics": metrics,
            "engagement_rate": engagement_rate,
            # The headline signal, kept out front rather than buried in the
            # composite: sends per reach is what earns cold distribution.
            "sends_per_reach": round(metrics["shares"] / reach, 4),
            "views_per_reach": round(metrics["views"] / reach, 2),
            "beat_structure": reel_beat_structure(manifest_entry),
            "experiment_id": (manifest_entry or {}).get("experiment_id"),
            "experiment_arm": (manifest_entry or {}).get("experiment_arm"),
        })
        reel["scored"] = True
        updated = True
        print(f"Scored reel {reel['media_id']} (\"{reel.get('hook', '')[:50]}\"): "
              f"engagement_rate={engagement_rate}, sends_per_reach={metrics['shares']}/{metrics['reach']}")
    return updated


def main():
    posted_log = load_json(POSTED_LOG_PATH, {"posts": []})
    reel_log = load_json(REEL_LOG_PATH, [])
    performance = load_json(PERFORMANCE_PATH, {"scored_posts": []})
    performance.setdefault("scored_posts", [])
    performance.setdefault("scored_reels", [])

    # Guarantee these files exist on disk from the very first run onward,
    # even if there's nothing to score yet. The workflow's next step
    # unconditionally `git add`s these paths — a literal missing file
    # makes `git add` fail the whole job (exit 128, "did not match any
    # files"), even though "nothing to score on a brand new repo" is a
    # completely normal, expected state, not an error.
    if not os.path.exists(POSTED_LOG_PATH):
        save_json(POSTED_LOG_PATH, posted_log)
    if not os.path.exists(REEL_LOG_PATH):
        save_json(REEL_LOG_PATH, reel_log)
    if not os.path.exists(PERFORMANCE_PATH):
        save_json(PERFORMANCE_PATH, performance)

    if not IG_ACCESS_TOKEN:
        print("IG_ACCESS_TOKEN not set — skipping performance fetch.")
        return

    today = datetime.date.today()
    carousels_updated = score_carousels(posted_log, performance, today)
    reels_updated = score_reels(reel_log, performance, today)

    if not (carousels_updated or reels_updated):
        print("No posts were eligible for scoring today.")
        return

    cutoff = (today - datetime.timedelta(days=PERFORMANCE_WINDOW_DAYS)).isoformat()
    performance["scored_posts"] = [p for p in performance["scored_posts"] if p["date"] >= cutoff]
    performance["scored_reels"] = [p for p in performance["scored_reels"] if p["date"] >= cutoff]

    save_json(PERFORMANCE_PATH, performance)
    if carousels_updated:
        save_json(POSTED_LOG_PATH, posted_log)
    if reels_updated:
        save_json(REEL_LOG_PATH, reel_log)


if __name__ == "__main__":
    main()
