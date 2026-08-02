"""
generate_copy.py

Generates the text content for one LinkedIn "swap chart" post using the
Mistral API. This is a SEPARATE persona/prompt from the Instagram Carousel
Bot - different voice, different goal.

Instagram bot goal: viral reach, loss-aversion hooks, punchy fragments.
LinkedIn bot goal:  CREDIBILITY for cold outreach. Ryan runs a Google
Ads / Meta Ads / Email Marketing agency for small businesses in Ireland.
Every post should read like something a genuinely sharp agency operator
would post - the kind of post a prospect sees right before Ryan messages
them, and thinks "okay, this guy actually knows what he's talking about."

FORMAT (do not deviate - this is the one format proven to work on this
account): a "swap chart". Title with one highlighted word, subtitle,
8-10 rows of "weak phrase / thing owners say" -> "strong phrase / what
actually works", short intro, short closing, a save-CTA and a
comment-bait question, hashtags.

Historical performance on this account (for context, not literal reuse):
- "Email Like a CEO" (universal swap chart) -> 110,217 impressions, best post by far
- "14 Negotiation Phrases" (repost of someone else's graphic) -> 32,473 impressions
- "Market Like a Pro" (generic marketer-jargon swap) -> 1,177 impressions, underperformed

Lesson: the swap-chart FORMAT works. Purely internal marketer-jargon
topics underperform. The fix used here: keep the format, change the
angle to speak TO small business owners about Google Ads / Meta Ads /
Email Marketing - their pain points, not marketer shop-talk.
"""

import json
import os
import random
from datetime import date

import requests

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")  # checked in generate_post()
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Same three niches as the Instagram Carousel Bot, for consistency.
NICHES = ["Google Ads", "Meta/Instagram Ads", "Email Marketing"]

# Rotate the "shape" of the swap chart so five posts in a row don't all
# read the same way even though they use the same template.
ANGLES = [
    "what small business owners say to their ad agency vs what they should say",
    "questions to ask before hiring a Google/Meta ads agency vs the vague version most owners ask",
    "weak excuses owners give for bad ad performance vs the real diagnosis",
    "what a bad email marketing setup looks like vs what a good one says",
    "phrases that reveal an agency is coasting on your budget vs what a good agency actually says",
    "what owners think ad success looks like vs what it actually looks like in the numbers",
]

SYSTEM_PROMPT = """You are writing LinkedIn posts for Ryan O'Driscoll, who runs a Google Ads / \
Meta Ads / email marketing agency for small businesses in Ireland. These posts exist for ONE \
reason: to build enough credibility that when Ryan messages a small business owner cold, they \
check his profile and think "this person clearly knows what they're doing" - not to go viral for \
its own sake.

VOICE
Direct, no fluff, sharp operator who manages ad accounts daily. Specific numbers over vague \
claims. Speaks to ONE business owner, not a crowd. Leads with a real pain point, not a listicle \
intro. Never apologises for being direct. Text-message casual, never corporate, never slang.

FORMAT - always a "swap chart" post. This is the only format that has actually worked on this \
account, so do not invent a new structure:
- title_main: 2-3 words, all caps, e.g. "RUN ADS LIKE"
- title_highlight: ONE short word or two-word phrase only (max ~10 characters), all caps, e.g. "A PRO" or "AN EXPERT" - this must be short, it renders large and bold, so title_main + title_highlight combined must be 5 words or fewer total
- subtitle: one line under the title stating what the graphic delivers, e.g. "9 Questions Every Business Owner Should Ask Their Ad Agency". If the subtitle contains a count ("9 Questions", "7 Mistakes"), that number MUST equal the exact number of objects in "pairs"
- hook_line: the opening line of the LinkedIn caption - a real tension, under 20 words
- intro: 2-3 short sentences setting up why this matters, written to a business owner not a marketer
- pairs: 8-10 objects, each with "weak" (what owners typically say/think/do - the naive version) \
and "strong" (what actually works / what a sharp operator would say instead). Each side under 14 \
words. These populate the red/green swap chart image, so they must work standalone with zero other context.
- closing: 1-2 sentences that land the point
- cta_save: a save-this-post line
- cta_question: a comment-bait question tied to the topic
- hashtags: 5-6 relevant hashtags, no spaces, each starting with #
- image_prompt: a short MOOD/TEXTURE description for an abstract background image - colour \
palette and energy only (e.g. "deep teal and warm cream, calm and confident" or "cool blue-grey, \
precise and analytical"). Never describe a person, object, scene, or literal subject - the \
renderer explicitly strips those out and asks for pure abstract gradients/geometry, so a \
character description here only fights the renderer. Vary the palette/mood to loosely match the \
topic's energy each time.

Never mention Ryan's agency name or pitch services directly in the post - the credibility has to \
be implicit, earned by the content being genuinely useful, not a pitch.

Output ONLY valid JSON matching this exact schema, nothing else:
{
  "topic": "string",
  "title_main": "string",
  "title_highlight": "string",
  "subtitle": "string",
  "hook_line": "string",
  "intro": "string",
  "pairs": [{"weak": "string", "strong": "string"}],
  "closing": "string",
  "cta_save": "string",
  "cta_question": "string",
  "hashtags": ["string"],
  "image_prompt": "string"
}
"""


def build_user_prompt() -> str:
    niche = random.choice(NICHES)
    angle = random.choice(ANGLES)
    today = date.today().isoformat()
    return (
        f"Date: {today}\n"
        f"Niche for this post: {niche}\n"
        f"Angle: {angle}\n\n"
        "Write one swap-chart LinkedIn post for this niche and angle. "
        "8 to 10 pairs. Make every pair specific - real numbers, real settings, real scenarios. "
        "No generic marketing filler."
    )


def generate_post() -> dict:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set - add it as a GitHub Actions secret.")
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt()},
        ],
        "temperature": 0.9,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    data = json.loads(content)

    required = [
        "topic", "title_main", "title_highlight", "subtitle", "hook_line",
        "intro", "pairs", "closing", "cta_save", "cta_question", "hashtags",
        "image_prompt",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Mistral response missing keys: {missing}")
    if not (6 <= len(data["pairs"]) <= 12):
        raise ValueError(f"Expected 6-12 pairs, got {len(data['pairs'])}")

    return data


def build_caption(data: dict) -> str:
    """Assembles the actual LinkedIn post text (the 'commentary' field)."""
    lines = [
        data["hook_line"],
        "",
        data["intro"],
        "",
        data["closing"],
        "",
        data["cta_save"],
        "",
        data["cta_question"],
        "",
        " ".join(data["hashtags"]),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    post = generate_post()
    print(json.dumps(post, indent=2, ensure_ascii=False))
    print("\n--- CAPTION PREVIEW ---\n")
    print(build_caption(post))
