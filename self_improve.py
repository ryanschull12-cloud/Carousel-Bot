"""
Weekly self-improvement pass: reads real Instagram engagement data
(performance_history.json, written by fetch_performance.py) and asks the
actual Claude API — not Mistral, which only writes the content itself —
to analyze it and rewrite learned_patterns.txt, a short guidance file that
runner.py injects into every day's generation prompt from then on.

This is the "then fix it" half of the self-review loop: performance_report.py
makes the same data visible to you by email; this script is what actually
acts on it, automatically, every week, without needing you or a live
Claude session involved.

Runs on the same weekly schedule as the report — see
.github/workflows/weekly_report.yml. Requires ANTHROPIC_API_KEY (a repo
secret you add once, see README notes) — this is the one part of the
pipeline that isn't on a free tier. At this volume (one short call a
week) the cost is negligible, but flagging it since the rest of this bot
deliberately avoids paid APIs.
"""

import os
import json
import datetime
import smtplib
import requests
from email.message import EmailMessage

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-5"

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

PERFORMANCE_PATH = "performance_history.json"
LEARNED_PATTERNS_PATH = "learned_patterns.txt"
# Don't let Claude draw conclusions from too little real data — below this,
# any "pattern" it finds is more likely noise than signal.
MIN_SCORED_FOR_ANALYSIS = 6

with open("self_improve_system_prompt.txt") as f:
    SYSTEM_PROMPT = f.read()


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {path}, using default ({e})")
        return default


def load_current_patterns():
    if not os.path.exists(LEARNED_PATTERNS_PATH):
        return "(No learned patterns file exists yet — this is the first run.)"
    with open(LEARNED_PATTERNS_PATH) as f:
        content = f.read().strip()
    return content or "(File exists but is currently empty.)"


def avg_by(posts, key):
    buckets = {}
    for p in posts:
        k = p.get(key) or "unknown"
        buckets.setdefault(k, []).append(p["engagement_rate"])
    ranked = [(k, sum(v) / len(v), len(v)) for k, v in buckets.items()]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def build_analysis_input(performance):
    posts = performance.get("scored_posts", [])
    lines = [f"Real Instagram engagement data, {len(posts)} scored post(s) total:", ""]

    for label, key in (("Angle", "angle"), ("Format", "format"), ("Niche", "niche")):
        ranked = avg_by(posts, key)
        if ranked:
            lines.append(f"{label} averages (engagement rate = weighted likes+comments+saves+shares ÷ reach, higher is better):")
            for k, avg, n in ranked:
                lines.append(f"  {k}: avg {avg:.2f} (n={n})")
            lines.append("")

    lines.append("Every individual scored post, ranked best to worst (engagement rate, date, niche/angle/format, hook):")
    for p in sorted(posts, key=lambda p: p["engagement_rate"], reverse=True):
        lines.append(
            f"  [{p['engagement_rate']:.2f}] {p.get('date', '')} — "
            f"{p.get('niche', '')}/{p.get('angle', '')}/{p.get('format', '')} — \"{p.get('hook', '')}\""
        )

    return "\n".join(lines)


def call_claude(current_patterns, analysis_input):
    user_content = (
        f"Your current learned_patterns.txt content:\n\n{current_patterns}\n\n"
        f"---\n\nThis week's real performance data:\n\n{analysis_input}\n\n"
        "---\n\nWrite the complete replacement content for learned_patterns.txt."
    )
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def send_update_email(new_patterns, skipped_reason=None):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("Gmail credentials not set — skipping notification email.")
        return

    msg = EmailMessage()
    if skipped_reason:
        msg["Subject"] = "Carousel Bot self-improvement — skipped this week"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = TO_EMAIL
        msg.set_content(f"No update to learned_patterns.txt this week.\n\nReason: {skipped_reason}")
    else:
        msg["Subject"] = f"Carousel Bot self-improvement — updated {datetime.date.today().isoformat()}"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = TO_EMAIL
        msg.set_content(
            "Claude reviewed this week's real Instagram performance data and updated the "
            "guidance that feeds into every day's content generation from here on.\n\n"
            "New learned_patterns.txt:\n\n" + new_patterns
        )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def main():
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set — skipping self-improvement pass.")
        return

    performance = load_json(PERFORMANCE_PATH, {"scored_posts": []})
    posts = performance.get("scored_posts", [])

    if len(posts) < MIN_SCORED_FOR_ANALYSIS:
        reason = (
            f"Only {len(posts)} scored post(s) on file — not enough real data yet "
            "to update guidance responsibly."
        )
        print(reason)
        send_update_email(None, skipped_reason=reason)
        return

    current_patterns = load_current_patterns()
    analysis_input = build_analysis_input(performance)

    try:
        new_patterns = call_claude(current_patterns, analysis_input)
    except Exception as e:
        reason = f"The Claude API call failed: {e}"
        print(reason)
        send_update_email(None, skipped_reason=reason)
        return

    if not new_patterns or len(new_patterns) < 30:
        reason = "Claude returned an empty or suspiciously short response — not applying it."
        print(reason)
        send_update_email(None, skipped_reason=reason)
        return

    with open(LEARNED_PATTERNS_PATH, "w") as f:
        f.write(new_patterns + "\n")

    print("learned_patterns.txt updated.")
    send_update_email(new_patterns)


if __name__ == "__main__":
    main()
