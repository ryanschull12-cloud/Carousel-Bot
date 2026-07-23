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

VIRALITY CHECKER (new): instead of asking Mistral for exactly 5 full
carousels straight away, this runner first asks for a larger POOL of cheap
concepts (just niche/angle/format/hook/bridge — a fraction of the tokens of
a full carousel), then scores every concept 1-10 with a dedicated "virality
checker" persona (virality_check_system_prompt.txt). Anything scoring below
8 is discarded; if fewer than 5 concepts clear the bar, another pool gets
generated (capped at a few attempts so a bad API day can't hang the job).
Only the top 5 surviving concepts get fully written out into complete
carousels — so the hook/bridge you see in the final batch already survived
a real quality bar before a single body slide was drafted. The concept's
score also decides which 3 carousels get auto-posted: instead of always
posting carousels 1-3 by position, the highest-scoring 3 get
post_to_instagram=true, so the auto-posted picks are the ones most likely
to actually perform, not just whichever came out of the model first. If the
pool/scoring step fails outright for any reason, this falls back to the
simpler direct-generation path rather than blocking the whole run.
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

# How many of the day's carousels get auto-posted to Instagram. The rest
# are still generated and emailed, just not auto-posted. These 3 go out at
# different times of day, not all at once — whichever carousel lands the
# top score posts right after generation here (see daily.yml, ~8:30am),
# the next posts from posts_later.yml (~1pm), and the third from
# evening-post.yml (~8pm), each reading this same morning's
# already-committed manifest. All three post fully automatically —
# nothing holds a post back; the virality checker and critic pass earlier
# in this file are what raise the bar on the copy itself, and pick which
# 3 of the 5 are the ones worth the auto-post slots, before any of this
# runs.
AUTO_POST_COUNT = 3

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

# Virality checker tuning. Concepts (not full carousels) are cheap to
# generate, so the pool can comfortably be bigger than the 5 we actually
# need — that's what gives the scorer something real to discriminate
# between. VIRALITY_THRESHOLD is the "remake anything below an 8" bar.
CONCEPT_POOL_SIZE = 10
CONCEPT_POOL_RETRY_SIZE = 8
MAX_POOL_ATTEMPTS = 3
VIRALITY_THRESHOLD = 8.0
WINNERS_NEEDED = 5

with open("content_brain_system_prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read()

with open("critic_system_prompt.txt", "r") as f:
    CRITIC_PROMPT = f.read()

with open("virality_check_system_prompt.txt", "r") as f:
    VIRALITY_PROMPT = f.read()


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


def _briefing_block(history_briefing, performance_briefing, briefing):
    """Shared block of optional context appended to both the concept-pool
    call and the direct-generation fallback, so the two paths stay in
    sync instead of drifting apart over time."""
    block = ""
    if history_briefing:
        block += (
            "\n\nHooks, angles, and formats used in recent batches. Treat "
            "this as a hard exclusion list, not a style reference — do not "
            "repeat any of these hooks, reuse the same angle+niche+format "
            "combination, or write anything that's a close paraphrase of "
            "one of these:\n" + history_briefing
        )
    if performance_briefing:
        block += (
            "\n\nPerformance feedback from real posted carousels — this is the "
            "closest thing you have to ground truth on what this specific "
            "audience responds to. Weight it accordingly, but don't discard "
            "angle/format variety entirely just because one bucket is "
            "currently ahead — a small sample can be noisy:\n" + performance_briefing
        )
    if briefing:
        block += (
            "\n\nRecent Google/Meta Ads news briefing (optional context — "
            "weave in only where it's genuinely useful, never force it, "
            "never quote it verbatim):\n" + briefing
        )
    return block


def generate_concept_pool(pool_size, history_briefing, performance_briefing, briefing, exclude_concepts=None):
    """
    Cheap first pass: ask for a pool of CONCEPTS only (niche/angle/format/
    hook/bridge), not full carousels. This is what makes a pool of 10+
    candidates affordable on Mistral's free tier — a concept is a few dozen
    tokens, a full carousel with body slides/recap/caption is many times
    that. Returns a list of dicts, each tagged with a local "index".
    """
    user_content = (
        f"Generate a POOL of {pool_size} candidate carousel CONCEPTS — not full "
        "carousels. For each concept, give only: niche, angle, format, "
        "hook_slide, and bridge_slide, following every rule in your system "
        "prompt that applies to those fields (word limits, originality "
        "rules, the GENERAL NOT HYPER-LOCAL rule, topic-focus weighting, "
        "hook-angle variety, etc). Since this pool is larger than a normal "
        "batch, push for real variety across niches, angles, and formats "
        "rather than converging on the same few ideas — a pool where half "
        "the concepts feel interchangeable defeats the point of having a pool."
    )
    if exclude_concepts:
        prior = "\n".join(f"- {c['hook_slide']}" for c in exclude_concepts)
        user_content += (
            "\n\nThese concepts were already generated and scored too low "
            "in an earlier round — do not repeat these or anything shaped "
            "like them:\n" + prior
        )
    user_content += _briefing_block(history_briefing, performance_briefing, briefing)
    user_content += (
        "\n\nReturn ONLY valid JSON matching this schema, nothing else: "
        '{"concepts": [{"niche": "...", "angle": "...", "format": "...", '
        '"hook_slide": "...", "bridge_slide": "..."}]}'
    )

    result = call_mistral(SYSTEM_PROMPT, user_content, temperature=0.95)
    concepts = result.get("concepts", [])
    for i, c in enumerate(concepts):
        c["index"] = i
    return concepts


def score_concepts(concepts):
    """Run the virality-checker pass over a pool of concepts. Returns the
    same list with a 'score' and 'reason' merged onto each concept."""
    payload = {
        "concepts": [
            {
                "index": c["index"],
                "niche": c.get("niche", ""),
                "angle": c.get("angle", ""),
                "format": c.get("format", ""),
                "hook_slide": c.get("hook_slide", ""),
                "bridge_slide": c.get("bridge_slide", ""),
            }
            for c in concepts
        ]
    }
    result = call_mistral(VIRALITY_PROMPT, json.dumps(payload), temperature=0.3)
    scores_by_index = {s["index"]: s for s in result.get("scored", [])}
    for c in concepts:
        s = scores_by_index.get(c["index"])
        c["score"] = float(s["score"]) if s else 0.0
        c["reason"] = s.get("reason", "") if s else "no score returned"
    return concepts


def select_winning_concepts(history_briefing, performance_briefing, briefing):
    """
    The virality checker loop: generate a pool, score it, keep anything
    scoring >= VIRALITY_THRESHOLD, and regenerate a fresh pool for whatever
    shortfall remains — up to MAX_POOL_ATTEMPTS rounds so a rough day on
    the model can't hang the job forever. Whatever happens, returns exactly
    WINNERS_NEEDED concepts: the highest-scoring ones seen across all
    rounds, even if a few never cleared the bar (better to post the best
    available than to fail the whole day's batch).
    """
    winners = []
    seen = []
    pool_size = CONCEPT_POOL_SIZE
    for attempt in range(1, MAX_POOL_ATTEMPTS + 1):
        print(f"Concept pool attempt {attempt}/{MAX_POOL_ATTEMPTS}: requesting {pool_size} concepts...")
        pool = generate_concept_pool(pool_size, history_briefing, performance_briefing, briefing, exclude_concepts=seen)
        pool = score_concepts(pool)
        for c in pool:
            print(f"  [{c['score']:.1f}] ({c.get('niche','?')}/{c.get('angle','?')}) \"{c.get('hook_slide','')}\" — {c.get('reason','')}")
        seen.extend(pool)
        passing = [c for c in seen if c["score"] >= VIRALITY_THRESHOLD]
        # De-dupe by hook text in case a retry pool echoes something close to a prior round.
        deduped = []
        seen_hooks = set()
        for c in sorted(passing, key=lambda c: c["score"], reverse=True):
            key = c.get("hook_slide", "").strip().lower()
            if key in seen_hooks:
                continue
            seen_hooks.add(key)
            deduped.append(c)
        winners = deduped
        print(f"  -> {len(winners)}/{WINNERS_NEEDED} concepts scoring >= {VIRALITY_THRESHOLD} so far.")
        if len(winners) >= WINNERS_NEEDED:
            return winners[:WINNERS_NEEDED]
        pool_size = CONCEPT_POOL_RETRY_SIZE

    # Ran out of attempts without enough concepts clearing the bar. Fill
    # the remaining slots with the best-scoring leftovers rather than
    # failing the run outright — a below-threshold concept that's still
    # the best available beats no post at all.
    if len(winners) < WINNERS_NEEDED:
        remaining = sorted(
            [c for c in seen if c not in winners],
            key=lambda c: c["score"], reverse=True,
        )
        needed = WINNERS_NEEDED - len(winners)
        if remaining:
            print(f"Only {len(winners)} concept(s) cleared {VIRALITY_THRESHOLD} after {MAX_POOL_ATTEMPTS} attempts — "
                  f"filling remaining {needed} slot(s) with the best-scoring leftovers instead of blocking the run.")
        winners.extend(remaining[:needed])
    return winners[:WINNERS_NEEDED]


def generate_batch(briefing, history_briefing, performance_briefing, winning_concepts=None):
    """
    Draft pass, then a critic pass that rewrites weak hooks before anything
    renders. If winning_concepts is given (the virality checker's picks),
    the draft pass writes full carousels for EXACTLY those pre-approved
    concepts instead of inventing new ones from scratch — the concept
    already earned its spot, so niche/angle/format/hook/bridge are locked
    in and only the body/recap/CTA/caption get generated fresh.
    """
    if winning_concepts:
        concepts_json = json.dumps([
            {
                "niche": c.get("niche", ""),
                "angle": c.get("angle", ""),
                "format": c.get("format", ""),
                "hook_slide": c.get("hook_slide", ""),
                "bridge_slide": c.get("bridge_slide", ""),
            }
            for c in winning_concepts
        ])
        user_content = (
            "Write full carousels for EXACTLY these 5 pre-approved concepts — "
            "they already passed a virality screen, so keep niche, angle, "
            "format, hook_slide, and bridge_slide exactly as given for each "
            "one (do not alter or improve them). Your job is to write the "
            "body_slides (6, following the standalone-value rules), "
            "recap_slide, cta_slide, cta_word, cta_promise, caption, and "
            "suggested_audio_style for each:\n\n" + concepts_json
        )
    else:
        user_content = "Generate today's batch."
    user_content += _briefing_block(history_briefing, performance_briefing, briefing)

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
        f"Carousels 1-{AUTO_POST_COUNT} are also being auto-posted to Instagram today, spread "
        "across the day (carousel 1 shortly, 3 around 1pm, 2 around 8pm).\n"
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

    # Virality checker: screen a pool of cheap concepts before spending
    # tokens writing out full carousels. Falls back to the old
    # direct-generation path if the pool/scoring step errors out for any
    # reason (Mistral outage, malformed response, etc.) — a rough patch in
    # the virality checker should never be able to block the whole run.
    winning_concepts = None
    try:
        winning_concepts = select_winning_concepts(history_briefing, performance_briefing, briefing)
        print(f"Virality checker selected {len(winning_concepts)} concepts to write up in full.")
    except Exception as e:
        print(f"Virality checker failed, falling back to direct generation ({e})")

    batch = generate_batch(briefing, history_briefing, performance_briefing, winning_concepts=winning_concepts)
    batch_date = batch.get("batch_date", "today")
    # Use the actual system date rather than trusting the model's
    # self-reported date, which can drift or be wrong.
    import datetime
    batch_date = datetime.date.today().isoformat()

    update_history(history, batch, batch_date)

    # Match each finished carousel back to its concept's virality score by
    # hook text, so the manifest (and the post_to_instagram decision below)
    # can use it. Full carousels should carry the same hook_slide the
    # concept pool proposed, since generate_batch is told to keep it as-is
    # — but if the critic pass tweaked it, or there's no score on file
    # (fallback path), that carousel just gets no score rather than a
    # guessed one.
    scores_by_hook = {}
    if winning_concepts:
        scores_by_hook = {c["hook_slide"].strip().lower(): c["score"] for c in winning_concepts}

    # Images go into ./posts/{date}/carousel_{n}/ — inside the repo working
    # directory (not /tmp) so they can be committed and get public raw URLs
    # for the Instagram posting step.
    base_dir = os.path.join("posts", batch_date)
    all_images = []
    carousel_entries = []

    for i, carousel in enumerate(batch["carousels"], start=1):
        out_dir = os.path.join(base_dir, f"carousel_{i}")
        images = render_carousel(carousel, batch_date, out_dir, carousel_index=i - 1)
        all_images.extend(images)
        score = scores_by_hook.get(carousel.get("hook_slide", "").strip().lower())
        carousel_entries.append({
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
            "virality_score": score,
        })

    # Which carousels actually get auto-posted: the AUTO_POST_COUNT
    # highest virality scores, not just whichever came out in positions
    # 1-3. Carousels with no score (virality checker fell back, or this
    # ran on the old direct path) sort after every scored one, so a scored
    # carousel always wins a posting slot over an unscored one.
    ranked = sorted(
        carousel_entries,
        key=lambda c: c["virality_score"] if c["virality_score"] is not None else -1,
        reverse=True,
    )
    post_indices = {c["index"] for c in ranked[:AUTO_POST_COUNT]}
    for entry in carousel_entries:
        entry["post_to_instagram"] = entry["index"] in post_indices

    manifest = {"batch_date": batch_date, "carousels": carousel_entries}
    with open(os.path.join(base_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    send_email(all_images, batch_date)
    print(f"Generated {len(all_images)} images across {len(batch['carousels'])} carousels.")
    posted_summary = ", ".join(
        f"#{c['index']} ({c['virality_score']:.1f})" if c["virality_score"] is not None else f"#{c['index']} (unscored)"
        for c in ranked[:AUTO_POST_COUNT]
    )
    print(f"Auto-posting today: {posted_summary}")
    print(f"Manifest written to {base_dir}/manifest.json")


if __name__ == "__main__":
    main()
