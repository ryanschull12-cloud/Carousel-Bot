"""
Weekly self-review email: reads real Instagram engagement data
(performance_history.json, written by fetch_performance.py) and sends a
plain-language summary of what's actually working and what isn't — which
angles, formats, and niches are over/under-performing, and the actual
top and bottom hooks by real engagement.

This is retrospective only — it never blocks or delays a post. It's the
same data that already quietly biases what runner.py writes next (see
build_performance_briefing there); this just makes it visible to you
instead of only feeding the model.

Runs on a weekly schedule — see .github/workflows/weekly_report.yml.
Read-only: doesn't write or commit anything, safe to re-run any time.
"""

import os
import json
import datetime
import smtplib
from email.message import EmailMessage

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

PERFORMANCE_PATH = "performance_history.json"
POSTED_LOG_PATH = "posted_log.json"
REPORT_WINDOW_DAYS = 7


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {path}, using default ({e})")
        return default


def avg_by(posts, key):
    buckets = {}
    for p in posts:
        k = p.get(key) or "unknown"
        buckets.setdefault(k, []).append(p["engagement_rate"])
    ranked = [(k, sum(v) / len(v), len(v)) for k, v in buckets.items()]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def build_report():
    today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=REPORT_WINDOW_DAYS)).isoformat()

    performance = load_json(PERFORMANCE_PATH, {"scored_posts": []})
    recent_scored = [p for p in performance.get("scored_posts", []) if p.get("date", "") >= cutoff]

    posted_log = load_json(POSTED_LOG_PATH, {"posts": []})
    recent_posts = [p for p in posted_log.get("posts", []) if p.get("date", "") >= cutoff]

    lines = []
    lines.append(f"Self-review for {cutoff} to {today.isoformat()}")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Auto-posted this week: {len(recent_posts)}")
    lines.append("")

    if recent_scored:
        lines.append(
            f"Real Instagram engagement on {len(recent_scored)} post(s) that had time to "
            "accrue data this week (engagement rate = weighted likes+comments+saves+shares "
            "÷ reach, higher is better):"
        )
        for label, key in (("Angle", "angle"), ("Format", "format"), ("Niche", "niche")):
            ranked = avg_by(recent_scored, key)
            if len(ranked) >= 2:
                best, worst = ranked[0], ranked[-1]
                lines.append(
                    f"  {label}: best = {best[0]} (avg {best[1]:.2f}, n={best[2]}), "
                    f"worst = {worst[0]} (avg {worst[1]:.2f}, n={worst[2]})"
                )
        lines.append("")

        top = sorted(recent_scored, key=lambda p: p["engagement_rate"], reverse=True)[:3]
        if top:
            lines.append("Top-performing hooks this week:")
            for p in top:
                lines.append(f"  - [{p['engagement_rate']:.2f}] \"{p.get('hook', '')}\"")
            lines.append("")

        bottom = sorted(recent_scored, key=lambda p: p["engagement_rate"])[:2]
        if bottom:
            lines.append("Lowest-performing hooks this week:")
            for p in bottom:
                lines.append(f"  - [{p['engagement_rate']:.2f}] \"{p.get('hook', '')}\"")
            lines.append("")
    else:
        lines.append(
            "No posts from this window had enough time to accrue scored engagement data yet "
            "(scoring happens ~3 days after posting) — check back next week."
        )
        lines.append("")

    lines.append(
        "This is the same data already feeding into what gets written going forward — "
        "nothing here requires action from you unless something looks off."
    )

    return "\n".join(lines)


def send_report(body):
    msg = EmailMessage()
    msg["Subject"] = f"Carousel Bot weekly self-review — {datetime.date.today().isoformat()}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def main():
    body = build_report()
    print(body)
    send_report(body)


if __name__ == "__main__":
    main()
