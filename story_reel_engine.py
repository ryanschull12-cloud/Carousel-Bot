"""
Story Reel Engine — single-clip B-roll + on-screen hook + full-caption format.

Distinct from reel_engine.py (the carousel-to-reel, multi-beat animated renderer
that also auto-posts to Instagram). This format was explicitly decided to NEVER
auto-post (see claude/story_reel_format_brief.md in the project) — it only
renders two reels a day and emails them to Ryan, same pattern as the two
hand-posted reel slots already emailed by instagram_reel_post.py, so he can
add a trending sound himself and post manually.

Design spec locked in over several iterations (2026-08-17), do not change
without a reason logged here:
  - Font: IBM Plex Sans Bold, installed via `apt-get install fonts-ibm-plex`
    (same mechanism as the existing Inter install step, not an upload).
  - Size: 68px on the 1080-wide canvas.
  - Colour: warm gold #FFE9C7 — chosen over plain white after comparing
    against readability research; still light enough to keep full contrast.
  - Layout: up to 4 short lines (~24 chars each), independently centered
    (not left-aligned as a block), positioned near the TOP of the frame.
    Top, not the lower third: Instagram's own Reels UI (caption preview,
    like/comment/share icons) occupies the bottom-right on a real phone and
    will cover text placed there — this is deliberate, not an accident.
  - Styling: soft shadow only (shadowx=2 shadowy=2 black@0.5), no boxed
    border — a boxed/bordered look tested worse and read as dated.
  - Motion: subtle Ken Burns zoom (1.0x -> 1.08x over the clip) instead of a
    static loop — a completely static background reads as a dead visual hook.
  - Silent by default (-an). Trending audio is a real distribution lever but
    cannot be attached through any API here (same limitation documented in
    instagram_reel_post.py for the hand-posted reel slots) — Ryan adds sound
    himself if he wants it, from the emailed file.
"""

import argparse, glob, json, os, random, smtplib, subprocess, sys, time
from email.message import EmailMessage

import requests

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
# Same reasoning as instagram_reel_post.py: NOT os.environ.get("TO_EMAIL", GMAIL_ADDRESS).
# GitHub Actions sets referenced secrets to "" rather than leaving them unset, which
# defeats a .get() fallback silently.
TO_EMAIL = os.environ.get("TO_EMAIL") or GMAIL_ADDRESS

FOOTAGE_DIR = "assets/story_reel_footage"
LOG_PATH = "story_reel_log.json"
SYSTEM_PROMPT_PATH = "story_reel_system_prompt.txt"

FONT = "/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Bold.ttf"
FONT_SIZE = 68
LINE_HEIGHT = 82
TEXT_COLOR = "0xFFE9C7"
TOP_Y = 340          # vertical center of the 4-line text block
REEL_DURATION = 18   # seconds, looped/trimmed regardless of source clip length
MAX_LINE_CHARS = 26  # safety-net wrap width if a hook line comes back too long


def call_mistral(system_prompt, user_content, temperature=0.95):
    """Same retry/timeout shape as runner.py's call_mistral — Mistral's API has
    documented transient 503/429/500s and slow responses that should not be fatal
    on the first hit."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
    }
    body = {
        "model": "mistral-large-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    last_error, last_exception = None, None
    for attempt in range(5):
        wait = min(60, 2 ** attempt) + 1
        try:
            resp = requests.post(MISTRAL_URL, headers=headers, json=body, timeout=180)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exception = e
            print(f"Mistral request timed out/failed to connect ({e}), retrying in {wait}s "
                  f"(attempt {attempt + 1}/5)...")
            time.sleep(wait)
            continue
        if resp.status_code in (503, 429, 500):
            last_error = resp
            print(f"Mistral returned {resp.status_code}, retrying in {wait}s "
                  f"(attempt {attempt + 1}/5)...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)
    if last_error is not None:
        last_error.raise_for_status()
    raise RuntimeError(f"Mistral request failed after 5 attempts: {last_exception}")


def load_log():
    if os.path.exists(LOG_PATH):
        try:
            return json.load(open(LOG_PATH))
        except Exception:
            return []
    return []


def save_log(log):
    json.dump(log, open(LOG_PATH, "w"), indent=2)


def pick_clips(n):
    """Rotate through the footage bank so the same clip doesn't repeat until every
    other clip has been used — same spirit as reel_posted_log.json's dedupe for the
    carousel-to-reel pipeline, just against clip filename instead of carousel index."""
    all_clips = sorted(glob.glob(os.path.join(FOOTAGE_DIR, "*.mp4")))
    if not all_clips:
        raise RuntimeError(f"No footage found in {FOOTAGE_DIR} — has the bank been committed?")
    log = load_log()
    recently_used = [entry["clip"] for entry in log[-len(all_clips):]] if log else []
    fresh = [c for c in all_clips if c not in recently_used]
    pool = fresh if len(fresh) >= n else all_clips
    random.shuffle(pool)
    chosen = pool[:n]
    # top up if the fresh pool was smaller than n
    i = 0
    while len(chosen) < n:
        candidate = all_clips[i % len(all_clips)]
        if candidate not in chosen:
            chosen.append(candidate)
        i += 1
    return chosen


def wrap_hook_lines(hook_lines):
    """Safety net: Mistral is instructed to keep each line under ~24 chars, but
    re-wrap defensively in case a line comes back long, so a render never overflows
    the frame the way an early manual draft did (script5_v2_centered.mp4, fixed
    2026-08-17 by shortening lines rather than shrinking font past readability)."""
    out = []
    for line in hook_lines[:4]:
        line = line.strip()
        if len(line) <= MAX_LINE_CHARS:
            out.append(line)
            continue
        words = line.split()
        cur = ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if len(trial) > MAX_LINE_CHARS and cur:
                out.append(cur)
                cur = w
            else:
                cur = trial
        if cur:
            out.append(cur)
    return out[:4] if out else ["Read the caption", "below ↓"]


def render_reel(clip_path, hook_lines, out_path, duration=REEL_DURATION):
    lines = wrap_hook_lines(hook_lines)
    n = len(lines)
    # center the block of n lines around TOP_Y
    offset_start = -(n - 1) / 2
    text_files = []
    filters = [
        f"scale={1200 if True else 1080}:2133,"
        f"zoompan=z='min(zoom+0.0015,1.08)':d=1:s=1080x1920:fps=30"
    ]
    for i, line in enumerate(lines):
        tf = f"/tmp/story_reel_line_{i}.txt"
        with open(tf, "w") as fh:
            fh.write(line)
        text_files.append(tf)
        y_mult = offset_start + i
        filters.append(
            f"drawtext=fontfile={FONT}:textfile={tf}:fontcolor={TEXT_COLOR}:"
            f"fontsize={FONT_SIZE}:shadowx=2:shadowy=2:shadowcolor=black@0.5:"
            f"x=(w-text_w)/2:y={TOP_Y}+({LINE_HEIGHT}*{y_mult})"
        )
    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-stream_loop", "-1", "-i", clip_path, "-t", str(duration),
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-level", "4.0", "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    for tf in text_files:
        try:
            os.remove(tf)
        except OSError:
            pass


def email(subject, body, attachments=None):
    """attachments: list of file paths, or None. Same non-fatal, loud-on-missing-
    credentials shape as instagram_reel_post.py's email() — a silent failure here
    previously meant a rendered file that never reached Ryan looked identical, from
    the outside, to one that was never made at all."""
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD):
        print("WARNING: GMAIL_ADDRESS/GMAIL_APP_PASSWORD not set in this step's env — "
              f"NOT sending {subject!r}.")
        return
    if not TO_EMAIL:
        print(f"WARNING: no recipient — TO_EMAIL secret is unset. NOT sending {subject!r}.")
        return
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subject, GMAIL_ADDRESS, TO_EMAIL
    m.set_content(body)
    total_size = 0
    for path in (attachments or []):
        if not os.path.exists(path):
            print(f"WARNING: attachment {path} does not exist — skipping")
            continue
        size = os.path.getsize(path)
        if total_size + size > 20 * 1024 * 1024:
            print(f"attachment {path} would push the email over 20MB — skipping")
            continue
        with open(path, "rb") as fh:
            m.add_attachment(fh.read(), maintype="video", subtype="mp4",
                              filename=os.path.basename(path))
        total_size += size
        print(f"attached {path} ({size / 1048576:.2f} MB)")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            s.send_message(m)
        print(f"emailed {subject!r} to {TO_EMAIL}")
    except Exception as e:
        print(f"EMAIL FAILED (non-fatal) sending {subject!r} to {TO_EMAIL}: "
              f"{type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2,
                     help="How many story reels to generate today (default 2, per the "
                          "locked format decision — never auto-posted, always emailed).")
    args = ap.parse_args()

    if not MISTRAL_API_KEY:
        print("MISTRAL_API_KEY not set — cannot generate story reel copy. Exiting.")
        sys.exit(1)

    system_prompt = open(SYSTEM_PROMPT_PATH).read()
    user_content = (
        f"Generate {args.count} story reels for today's batch. Each must be genuinely "
        f"different in angle, mechanism, and specific numbers from the others."
    )
    result = call_mistral(system_prompt, user_content)
    reels = result.get("reels", [])[: args.count]
    if not reels:
        print("Mistral returned no reels — nothing to render.")
        sys.exit(1)

    clips = pick_clips(len(reels))
    os.makedirs("posts/story_reels", exist_ok=True)
    today = time.strftime("%Y-%m-%d")

    log = load_log()
    rendered_paths = []
    email_body_parts = [
        f"Today's story reels ({today}) — rendered silently, same as the two hand-posted "
        f"value-reel slots. Add a trending sound yourself before posting if you want one; "
        f"nothing here can attach one automatically.\n"
    ]

    for i, (reel, clip) in enumerate(zip(reels, clips), start=1):
        hook_lines = reel.get("hook_lines", [])
        caption = reel.get("caption", "")
        cta_word = reel.get("cta_word", "")
        cta_promise = reel.get("cta_promise", "")
        out_path = f"posts/story_reels/{today}_reel{i}.mp4"
        try:
            render_reel(clip, hook_lines, out_path)
            rendered_paths.append(out_path)
            log.append({
                "date": today,
                "index": i,
                "clip": clip,
                "hook_lines": hook_lines,
                "cta_word": cta_word,
            })
            print(f"rendered {out_path} from {clip}")
        except subprocess.CalledProcessError as e:
            print(f"RENDER FAILED for reel {i} (clip {clip}): {e.stderr.decode(errors='replace')[:500]}")
            continue

        email_body_parts.append(
            f"--- Reel {i} ({os.path.basename(clip)}) ---\n"
            f"Hook: {' / '.join(hook_lines)}\n\n"
            f"Caption (copy-paste this when you post):\n{caption}\n\n"
            f"CTA keyword: {cta_word}  |  Promise: {cta_promise}\n"
        )

    save_log(log)

    if rendered_paths:
        email(
            subject=f"Story Reels — {today}",
            body="\n".join(email_body_parts),
            attachments=rendered_paths,
        )
    else:
        print("No reels rendered successfully — not sending an email.")


if __name__ == "__main__":
    main()
