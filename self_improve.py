"""
Weekly self-improvement pass: reads real Instagram engagement data
(performance_history.json) alongside the current content/critic prompts
and carousel_engine.py's design constants, and asks Claude to propose
concrete, specific edits -- to the prompts AND to the visual design --
that the data actually supports. Emails the suggestions; never edits or
commits anything itself.

REPORT ONLY BY DESIGN. An earlier version of this script auto-committed
its own suggested changes directly to the prompt files (and was reverted
-- see git history), so this version deliberately stops at "here's what
I'd change and why" and leaves applying it to you. If you want to make
this auto-apply again later, layer that on top rather than reverting to
the old approach blind.

Runs weekly -- see .github/workflows/weekly_report.yml. Safe to re-run
any time; it has no side effects besides sending an email.
"""

import os
import json
import datetime
import smtplib
import requests
from email.message import EmailMessage

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"

PERFORMANCE_PATH = "performance_history.json"
CONTENT_BRAIN_PATH = "content_brain_system_prompt.txt"
CRITIC_PATH = "critic_system_prompt.txt"
CAROUSEL_ENGINE_PATH = "carousel_engine.py"
REPORT_WINDOW_DAYS = 14  # wider window than the weekly report email -- more
                          # data points to reason about trends from, since
                          # this runs less often than it's read

MIN_SCORED_POSTS = 6  # below this, there's not enough signal to trust any
                       # pattern -- skip the pass rather than have Claude
                       # invent a story from noise


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {path}, using default ({e})")
        return default


def load_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_design_constants(engine_source):
    """Pull just the FIXED FONT SIZES block out of carousel_engine.py rather
    than sending the whole file -- keeps the prompt focused on the numbers
    that are actually safe/sane for Claude to suggest changing, instead of
    inviting a rewrite of the rendering logic itself."""
    lines = engine_source.splitlines()
    start = next((i for i, l in enumerate(lines) if "FIXED FONT SIZES" in l), None)
    if start is None:
        return "(could not locate the FIXED FONT SIZES block in carousel_engine.py)"
    block = []
    for line in lines[start:]:
        block.append(line)
        if line.strip() == "" and len(block) > 1:
            break
    return "\n".join(block)


def avg_by(posts, key):
    buckets = {}
    for p in posts:
        k = p.get(key) or "unknown"
        buckets.setdefault(k, []).append(p["engagement_rate"])
    ranked = [(k, sum(v) / len(v), len(v)) for k, v in buckets.items()]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def build_performance_summary(scored_posts):
    lines = [f"{len(scored_posts)} scored post(s) in the last {REPORT_WINDOW_DAYS} days:\n"]
    for label, key in (("Niche", "niche"), ("Angle", "angle"), ("Format", "format")):
        ranked = avg_by(scored_posts, key)
        lines.append(f"{label} performance (avg engagement_rate, n=sample size):")
        for name, avg, n in ranked:
            lines.append(f"  {name}: {avg:.2f} (n={n})")
        lines.append("")

    ranked_posts = sorted(scored_posts, key=lambda p: p["engagement_rate"], reverse=True)
    lines.append("Top 5 hooks by engagement_rate:")
    for p in ranked_posts[:5]:
        lines.append(f"  [{p['engagement_rate']:.2f}] ({p.get('niche')}/{p.get('angle')}/{p.get('format')}) \"{p.get('hook', '')}\"")
    lines.append("")
    lines.append("Bottom 5 hooks by engagement_rate:")
    for p in ranked_posts[-5:]:
        lines.append(f"  [{p['engagement_rate']:.2f}] ({p.get('niche')}/{p.get('angle')}/{p.get('format')}) \"{p.get('hook', '')}\"")

    return "\n".join(lines)


SYSTEM_PROMPT = """You are reviewing a week's worth of real Instagram performance data for an \
automated marketing carousel bot, alongside the exact prompts and design constants currently \
driving content and visual design. Your job is to propose concrete, specific changes that the \
data actually supports -- not generic best-practice advice.

Rules:
1. Every suggestion must cite the specific data point that motivated it (an engagement_rate \
comparison, a pattern across top/bottom hooks, etc.) -- if you can't point to the number, don't \
suggest it.
2. For prompt changes: quote the exact sentence or rule you'd add, remove, or reword in \
content_brain_system_prompt.txt or critic_system_prompt.txt, so it can be copy-pasted directly.
3. For design changes: only propose edits to the specific constants shown to you (font sizes, \
etc.) -- never propose new rendering logic, new slide types, or structural changes to \
carousel_engine.py.
4. If the data is too thin, mixed, or contradictory to support a confident suggestion in some \
area, say so plainly instead of forcing a recommendation.
5. Cap it at the 3-5 highest-conviction suggestions total, ranked by how strongly the data \
supports each one. Quality over quantity -- this gets reviewed by a human every week, so a long \
list of weak suggestions is worse than three strong ones.

Output plain text only (this goes straight into an email body) -- no markdown fences, no JSON. \
Structure it as a short numbered list, each item: the suggestion, the data it's based on, and \
which specific file it applies to."""


def call_claude(performance_summary, content_brain, critic, design_constants):
    user_content = (
        f"PERFORMANCE DATA:\n{performance_summary}\n\n"
        f"CURRENT content_brain_system_prompt.txt:\n{content_brain}\n\n"
        f"CURRENT critic_system_prompt.txt:\n{critic}\n\n"
        f"CURRENT carousel_engine.py design constants:\n{design_constants}\n"
    )
    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 2000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=120,
    )
    if not resp.ok:
        raise RuntimeError(f"Anthropic API call failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def send_email(body, skipped_reason=None):
    msg = EmailMessage()
    if skipped_reason:
        msg["Subject"] = f"Carousel Bot self-improvement — skipped this week"
        msg.set_content(skipped_reason)
    else:
        msg["Subject"] = f"Carousel Bot self-improvement suggestions — {datetime.date.today().isoformat()}"
        msg.set_content(
            "These are suggestions only -- nothing has been changed automatically. "
            "Review and copy in whatever you agree with.\n\n" + body
        )
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def main():
    today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=REPORT_WINDOW_DAYS)).isoformat()

    performance = load_json(PERFORMANCE_PATH, {"scored_posts": []})
    scored_posts = [p for p in performance.get("scored_posts", []) if p.get("date", "") >= cutoff]

    if len(scored_posts) < MIN_SCORED_POSTS:
        reason = (
            f"Only {len(scored_posts)} scored post(s) in the last {REPORT_WINDOW_DAYS} days "
            f"(need at least {MIN_SCORED_POSTS}) -- skipping this week rather than drawing "
            "conclusions from too little data."
        )
        print(reason)
        send_email(None, skipped_reason=reason)
        return

    performance_summary = build_performance_summary(scored_posts)
    content_brain = load_text(CONTENT_BRAIN_PATH)
    critic = load_text(CRITIC_PATH)
    design_constants = extract_design_constants(load_text(CAROUSEL_ENGINE_PATH))

    # call_claude had no error handling at all -- a single timeout or 5xx
    # from Anthropic crashed the whole script with nothing caught, so the
    # weekly step just showed a red X in Actions and Ryan got NO email
    # that week (not even a "skipped" notice, unlike the low-data path
    # above). Same silent-failure shape as the Mistral timeout bug found
    # in runner.py on 2026-07-27, just lower-stakes since this only feeds
    # the weekly suggestions email, not daily posting.
    try:
        suggestions = call_claude(performance_summary, content_brain, critic, design_constants)
    except Exception as e:
        reason = f"Self-improvement suggestions failed this week due to an API error: {e}"
        print(reason)
        send_email(None, skipped_reason=reason)
        return
    print(suggestions)
    send_email(suggestions)


if __name__ == "__main__":
    main()
