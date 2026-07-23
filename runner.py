"""
Daily runner: calls the free Mistral API for 5 carousel scripts, runs them
through a second "critic" pass to catch weak hooks, renders them into
images using carousel_engine.py, saves them into the repo (so they get
public URLs for Instagram posting), writes a manifest for the Instagram
posting step, and emails all 5 carousels to you.

Runs inside GitHub Actions on a schedule — see .github/workflows/daily.yml.

TWO-CALL GENERATION (new): a single Mistral call, even with a very detailed
system prompt, tends to settle for the first phrasing that satisfies the
rules instead of the sharpest one. So this runner now makes a second call
after the draft — a separate "critic" persona (critic_system_prompt.txt)
whose only job is to find weak hooks/bridges in the draft and rewrite them
before anything gets rendered or posted. If the critic call fails for any
reason, the draft is used as-is rather than blocking the whole run.

PERFORMANCE-AWARE GENERATION (new): if performance_history.json has enough
real Instagram engagement data (written by fetch_performance.py, which runs
before this script in the workflow), a summary of what's actually working —
by angle, format, niche, plus concrete top/bottom hook examples — is passed
to the content brain alongside the existing anti-repetition history. This is
what makes the bot self-aware about real performance instead of only
tracking what it has already said.
"""

import os
import json
import time
import smtplib
import requests
from email.message import EmailMessage
from carousel_engine import render_carousel

MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

# How many of the day's carousels get auto-posted to Instagram.
# The rest are still generated and emailed, just not auto-posted.
AUTO_POST_COUNT = 2

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
TAVILY_URL = "https://api.tavily.com/search"

# How many days of past hooks/angles/formats to remember and feed back to
# Mistral so it stops repeating itself across days, not just within a
# single day's batch. Kept short so it stays cheap and doesn't bloat the
# prompt.
HISTORY_PATH = "history.json"
HISTORY_DAYS_TO_KEEP = 10

# Real engagement data, written by fetch_performance.py.
PERFORMANCE_PATH = "performance_history.json"
MIN_SCORED_FOR_BRIEFING = 4  # don't draw conclusions from a tiny sample

with open("content_brain_system_prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read()

with open("critic_system_prompt.txt", "r") as f:
    CRITIC_PROMPT = f.read()


def load_history():
    """Read the rolling history file. Missing or corrupt file = start fresh."""
    if not os.path.exists(HISTORY_PATH):
        return {"recent_batches": []}
    try:
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {HISTORY_PATH}, starting fresh ({e})")
        return {"recent_batches": []}


def build_history_briefing(history):
    """
    Flatten recent batches into a compact exclusion list Mistral can read
    before writing today's batch. This is what stops it from reusing a
    hook, angle+niche+format combo, or industry example it already used
    last week — without this, every daily call starts from a blank slate.
    """
    lines = []
    for entry in history.get("recent_batches", []):
        for c in entry.get("carousels", []):
            lines.append(
                f"- [{entry.get('date', '?')}] {c.get('niche', '?')} / "
                f"{c.get('angle', '?')} / {c.get('format', '?')}: "
                f"\"{c.get('hook', '')}\""
            )
    return "\n".join(lines) if lines else None


def update_history(history, batch, batch_date):
    """Append today's batch to the rolling history and write it back to disk."""
    entry = {
        "date": batch_date,
        "carousels": [
            {
                "niche": c.get("niche", ""),
                "angle": c.get("angle", ""),
                "format": c.get("format", ""),
                "hook": c.get("hook_slide", ""),
            }
            for c in batch.get("carousels", [])
        ],
    }
    batches = [b for b in history.get("recent_batches", []) if b.get("date") != batch_date]
    batches.append(entry)
    history["recent_batches"] = batches[-HISTORY_DAYS_TO_KEEP:]
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def load_performance():
    """Read real Instagram engagement data. Missing/corrupt file = no briefing today."""
    if not os.path.exists(PERFORMANCE_PATH):
        return {"scored_posts": []}
    try:
        with open(PERFORMANCE_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {PERFORMANCE_PATH}, ignoring ({e})")
        return {"scored_posts": []}


def build_performance_briefing(performance):
    """
    Turn scored posts into a short, honest summary: which angle/format/niche
    is over/under-performing on average (with sample size, so the content
    brain can weight its confidence), plus a handful of concrete top and
    bottom hooks to study the shape of, not copy.
    """
    posts = performance.get("scored_posts", [])
    if len(posts) < MIN_SCORED_FOR_BRIEFING:
        return None

    def avg_by(key):
        buckets = {}
        for p in posts:
            k = p.get(key) or "unknown"
            buckets.setdefault(k, []).append(p["engagement_rate"])
        ranked = [(k, sum(v) / len(v), len(v)) for k, v in buckets.items()]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    lines = [
        f"Real Instagram engagement data from your last {len(posts)} scored carousels "
        "(engagement rate = weighted likes+comments+saves+shares ÷ reach, higher is better):"
    ]

    for label, key in (("Angle", "angle"), ("Format", "format"), ("Niche", "niche")):
        ranked = avg_by(key)
        if len(ranked) < 2:
            continue
        best = ranked[0]
        worst = ranked[-1]
        lines.append(
            f"- {label}: '{best[0]}' performs best so far (avg {best[1]:.2f}, n={best[2]}); "
            f"'{worst[0]}' trails (avg {worst[1]:.2f}, n={worst[2]})"
        )

    top_posts = sorted(posts, key=lambda p: p["engagement_rate"], reverse=True)[:3]
    if top_posts:
        lines.append("Actual top-performing hooks (study the structure, never reuse the wording):")
        for p in top_posts:
            lines.append(f"  • [{p['engagement_rate']:.2f}] \"{p['hook']}\" ({p['angle']}/{p['format']})")

    bottom_posts = sorted(posts, key=lambda p: p["engagement_rate"])[:2]
    if bottom_posts:
        lines.append("Actual under-performing hooks (avoid repeating this shape):")
        for p in bottom_posts:
            lines.append(f"  • [{p['engagement_rate']:.2f}] \"{p['hook']}\" ({p['angle']}/{p['format']})")

    return "\n".join(lines)


def call_tavily():
    """
    Pull a short, recent-news briefing about Google/Meta Ads to hand to
    Mistral so hooks can reference something genuinely current — this is
    what the content brain prompt's "recent news briefing" paragraph
    refers to. Entirely optional: if TAVILY_API_KEY isn't set, or the
    request fails for any reason (rate limit, timeout, outage), we just
    skip the briefing and generate the batch as normal. Never blocks.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.post(
            TAVILY_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "query": "Google Ads OR Meta Ads update change 2026",
                "topic": "news",
                "search_depth": "basic",
                "time_range": "week",
                "max_results": 3,
                "include_answer": True,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Tavily briefing skipped (non-fatal): {e}")
        return None

    bits = []
    if data.get("answer"):
        bits.append(data["answer"])
    for r in data.get("results", [])[:3]:
        title = r.get("title")
        if title:
            bits.append(title)

    if not bits:
        return None
    return " | ".join(bits)[:800]  # keep it a briefing, not an essay


def call_mistral(system_prompt, user_content, temperature=0.9):
    """Generic single-call helper — used for both the draft pass and the critic pass."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
    }
    body = {
        # Free tier on Mistral's La Plateforme includes Large, not just
        # Small, at no extra cost — Large follows the nuanced instructions
        # in the system prompt far more reliably than Small does.
        "model": "mistral-large-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    last_error = None
    for attempt in range(5):
        resp = requests.post(MISTRAL_URL, headers=headers, json=body, timeout=90)
        if resp.status_code in (503, 429, 500):
            last_error = resp
            wait = min(60, 2 ** attempt) + 1
            print(f"Mistral returned {resp.status_code}, retrying in {wait}s (attempt {attempt + 1}/5)...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)
    last_error.raise_for_status()


def generate_batch(briefing, history_briefing, performance_briefing):
    """Draft pass, then a critic pass that rewrites weak hooks before anything renders."""
    user_content = "Generate today's batch."
    if history_briefing:
        user_content += (
            "\n\nHooks, angles, and formats used in recent batches. Treat "
            "this as a hard exclusion list, not a style reference — do not "
            "repeat any of these hooks, reuse the same angle+niche+format "
            "combination, or write anything that's a close paraphrase of "
            "one of these:\n" + history_briefing
        )
    if performance_briefing:
        user_content += (
            "\n\nPerformance feedback from real posted carousels — this is the "
            "closest thing you have to ground truth on what this specific "
            "audience responds to. Weight it accordingly, but don't discard "
            "angle/format variety entirely just because one bucket is "
            "currently ahead — a small sample can be noisy:\n" + performance_briefing
        )
    if briefing:
        user_content += (
            "\n\nRecent Google/Meta Ads news briefing (optional context — "
            "weave in only where it's genuinely useful, never force it, "
            "never quote it verbatim):\n" + briefing
        )

    draft = call_mistral(SYSTEM_PROMPT, user_content, temperature=0.9)

    critique_user = (
        "Here is today's draft batch of 5 carousels. Review it against your "
        "checklist and return the corrected full JSON.\n\n" + json.dumps(draft)
    )
    try:
        refined = call_mistral(CRITIC_PROMPT, critique_user, temperature=0.4)
        if refined.get("carousels") and len(refined["carousels"]) == len(draft.get("carousels", [])):
            refined["batch_date"] = draft.get("batch_date", refined.get("batch_date"))
            return refined
        print("Critic pass returned a malformed batch — using the draft instead.")
        return draft
    except Exception as e:
        print(f"Critic pass failed, using draft instead ({e})")
        return draft


def send_email(image_paths, batch_date):
    msg = EmailMessage()
    msg["Subject"] = f"Your carousels for {batch_date}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"Today's batch of {len(image_paths)} slide images is attached.\n"
        f"The first {AUTO_POST_COUNT} carousels are also being auto-posted to Instagram.\n"
        "Save the rest to your camera roll for TikTok / manual posting."
    )
    for path in image_paths:
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        subtype = "jpeg" if ext in ("jpg", "jpeg") else ext
        with open(path, "rb") as f:
            msg.add_attachment(
                f.read(), maintype="image", subtype=subtype,
                filename=os.path.basename(os.path.dirname(path)) + "_" + os.path.basename(path),
            )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def main():
    history = load_history()
    history_briefing = build_history_briefing(history)
    if history_briefing:
        print(f"Loaded history: {len(history.get('recent_batches', []))} past day(s) on file.")

    performance = load_performance()
    performance_briefing = build_performance_briefing(performance)
    if performance_briefing:
        print(f"Loaded performance data: {len(performance.get('scored_posts', []))} scored post(s) — informing today's batch.")
    else:
        print("Not enough scored performance data yet — generating on style rules alone.")

    briefing = call_tavily()
    if briefing:
        print(f"Tavily briefing pulled ({len(briefing)} chars) — passing to Mistral.")

    batch = generate_batch(briefing, history_briefing, performance_briefing)
    batch_date = batch.get("batch_date", "today")
    # Use the actual system date rather than trusting the model's
    # self-reported date, which can drift or be wrong.
    import datetime
    batch_date = datetime.date.today().isoformat()

    update_history(history, batch, batch_date)

    # Images go into ./posts/{date}/carousel_{n}/ — inside the repo working
    # directory (not /tmp) so they can be committed and get public raw URLs
    # for the Instagram posting step.
    base_dir = os.path.join("posts", batch_date)
    all_images = []
    manifest = {"batch_date": batch_date, "carousels": []}

    for i, carousel in enumerate(batch["carousels"], start=1):
        out_dir = os.path.join(base_dir, f"carousel_{i}")
        images = render_carousel(carousel, batch_date, out_dir, carousel_index=i - 1)
        all_images.extend(images)
        manifest["carousels"].append({
            "index": i,
            "caption": carousel.get("caption", ""),
            "niche": carousel.get("niche", ""),
            # angle/format/hook are carried through so instagram_post.py can
            # log them alongside the media_id once posted — that's what lets
            # fetch_performance.py tie real engagement back to a specific
            # angle/format/hook later.
            "angle": carousel.get("angle", ""),
            "format": carousel.get("format", ""),
            "hook": carousel.get("hook_slide", ""),
            "image_paths": images,
            "post_to_instagram": i <= AUTO_POST_COUNT,
        })

    with open(os.path.join(base_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    send_email(all_images, batch_date)
    print(f"Generated {len(all_images)} images across {len(batch['carousels'])} carousels.")
    print(f"Manifest written to {base_dir}/manifest.json")


if __name__ == "__main__":
    main()
