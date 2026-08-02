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

# Rendering constraints, enforced in code because prompt instructions alone
# don't hold. A card line longer than this forces the renderer to step the
# font down, which is what kills legibility in the mobile feed.
MAX_LINE_CHARS = 62
MAX_HIGHLIGHT_CHARS = 13
# Secondary lines ("detail", "value") render smaller so they get more room.
MAX_DETAIL_CHARS = 90
# Below this many compliant items the graphic looks thin, so retry instead.
MIN_USABLE_PAIRS = 4

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

SHARED FIELDS - every post has these regardless of format:
- title_main: 2-3 words, all caps, e.g. "RUN ADS LIKE"
- title_highlight: ONE short word or two-word phrase, HARD MAXIMUM 13 CHARACTERS INCLUDING SPACES, \
all caps, e.g. "A PRO" or "AN EXPERT". It renders very large inside a coloured chip; anything \
longer breaks the layout and the response will be rejected. Count the characters before you answer.
- subtitle: one line under the title stating what the graphic delivers, e.g. "5 Questions Every Business Owner Should Ask Their Ad Agency". If the subtitle contains a count ("5 Questions", "4 Mistakes"), that number MUST equal the exact number of body items you produce
- hook_line: the opening line of the LinkedIn caption - a real tension, under 20 words
- intro: 2-3 short sentences setting up why this matters, written to a business owner not a marketer
- (body field): defined by the FORMAT BRIEF appended at the end of this prompt. Produce exactly \
the field it names, with exactly the number of items it specifies.

  LENGTH IS A HARD CONSTRAINT: every body item string must be 62 CHARACTERS OR FEWER, including \
spaces (the "detail" line may run to 90). This is not a style preference - longer lines shrink the \
type until the graphic is unreadable on a phone, and any response breaking this limit is rejected \
and regenerated. Count characters. Cut every word that isn't load-bearing: "What's our cost per \
qualified lead?" not "What is the average cost per qualified lead across all of our campaigns?"

  Keep the audience consistent across every item. These are small business owners in Ireland. Do \
not switch between "ecommerce accounts" and "service industry" within one post, and don't assume \
the reader runs a shop unless the topic says so.

  Body items populate the graphic, so each line must work standalone with zero other context.

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

ACCURACY GATE - THIS OVERRIDES EVERYTHING ELSE, INCLUDING PUNCHINESS

This account is read by people who buy and run ads. One wrong claim destroys the exact \
credibility these posts exist to build. A boring-but-correct line always beats a punchy-but-wrong \
one. Apply every rule below before you consider phrasing:

1. NEVER invent platform mechanics. Do not claim a platform does something unless it is \
well-established, documented behaviour. Specifically banned: made-up algorithm rules, invented \
"tricks" (e.g. pausing campaigns to reset costs, magic bid numbers that unlock reach), fake \
thresholds, or anything phrased as a hidden lever the platform doesn't actually have.
2. NEVER fabricate statistics. Do not produce invented percentages, euro amounts, or "X% of \
businesses..." claims presented as fact. If you have no real figure, do not invent one - write the \
line without a number, or frame it explicitly as an example ("if your margin is 40%, ...") or as a \
question the owner should ask ("what's our actual cost per qualified lead?").
3. NEVER assert a causal claim you cannot support. "Do X and you'll get Y% more leads" is banned \
unless it is a definitional relationship. Prefer diagnostic framing: what to check, what to ask, \
what the number should be measured against.
4. Numbers that ARE allowed: arithmetic that is true by definition (break-even ROAS is 1 divided \
by margin), the user's own metrics referred to generically, and clearly-labelled illustrative \
examples.
4b. NEVER state an industry benchmark as if it were a standard. "Show me accounts above 3.0 ROAS", \
"good CPA is under EUR 40", "aim for a 2% CTR" are all banned - those numbers vary enormously by \
sector, margin and offer, and quoting them marks you as someone who doesn't run accounts. Ask what \
the number IS and what it's measured against, never assert what it SHOULD be.
4c. Avoid jargon-flexing. A question is only good if the answer would actually change a hiring or \
budget decision. "What's your benchmark CPM for reach campaigns?" is noise; "What did we pay per \
booked job last month?" is signal. Favour money-and-outcome questions over platform-metric trivia.
5. Every "strong" line must be something a competent practitioner would actually say in an account \
review. If it sounds like a growth-hack tweet, it's wrong. Read each line back and ask: "would a \
media buyer with ten years of experience nod, or wince?" If wince, rewrite.
6. Prefer questions and checks over promises. The strongest content here makes an owner realise \
they don't know a number they should know.
7. If uncertain whether a claim is true, leave it out. There is no penalty for a shorter, safer \
post. There is a large penalty for being wrong in public.

Never mention Ryan's agency name or pitch services directly in the post - the credibility has to \
be implicit, earned by the content being genuinely useful, not a pitch.

The body of the graphic changes by format - the format brief below tells you which body field to \
produce. Output ONLY valid JSON, nothing else, with these shared keys plus the body key named in \
the format brief:
{
  "topic": "string",
  "title_main": "string",
  "title_highlight": "string",
  "subtitle": "string",
  "hook_line": "string",
  "intro": "string",
  "closing": "string",
  "cta_save": "string",
  "cta_question": "string",
  "hashtags": ["string"],
  "image_prompt": "string"
}
"""


# ---------------------------------------------------------------------------
# FORMAT REGISTRY
#
# One archetype per day, rotated by date so consecutive posts never share a
# shape. Each entry defines the body field, its per-item character budget, and
# the brief appended to the system prompt. "layout" tells generate_image which
# body renderer to use.
# ---------------------------------------------------------------------------

FORMATS = {
    "swap": {
        "layout": "two_column",
        "body_key": "pairs",
        "item_fields": ("weak", "strong"),
        "count": 5,
        "brief": """FORMAT: SWAP CHART. Two columns - what owners say vs what actually works.
- pairs: EXACTLY 5 objects with "weak" and "strong".
  "weak" = genuinely naive or vague, the kind of thing someone says when they don't yet know what \
to measure ("Can you get us more leads?"). If the weak line is actually a sensible question the \
contrast collapses and the graphic has no point.
  "strong" = a specific, answerable question or concrete check that would expose whether an agency \
knows its numbers.
  Each pair must attack a DIFFERENT problem (no two about budget, no two about tracking).""",
    },
    "checklist": {
        "layout": "marked_list",
        "body_key": "items",
        "item_fields": ("action", "detail"),
        "count": 5,
        "brief": """FORMAT: AUDIT CHECKLIST. A list of checks the reader can actually run this week.
- items: EXACTLY 5 objects with "action" and "detail".
  "action" = an imperative instruction, specific enough to do today ("Open your search terms \
report"). Start with a verb.
  "detail" = one line on what they're looking for or why it matters. Not a promise of results - \
a description of the signal.
  Order them so someone could work top to bottom. Each check must target a different part of the \
account. This format earns saves, so every line must be genuinely actionable rather than advice.""",
    },
    "red_flags": {
        "layout": "marked_list",
        "marker": "warn",
        "body_key": "items",
        "item_fields": ("action", "detail"),
        "count": 5,
        "brief": """FORMAT: RED FLAGS. Warning signs the reader can spot in their own account or \
in an agency's reporting.
- items: EXACTLY 5 objects with "action" and "detail".
  "action" = the red flag itself, stated as a short observable symptom ("Your report leads with \
impressions"). Not a verb instruction - a thing they'd notice.
  "detail" = what it usually indicates, stated carefully. Use hedged language ("usually means", \
"often indicates") because a symptom is evidence, not proof. Never claim certainty about someone \
else's account.
  Five different symptoms, no overlap.""",
    },
    "the_math": {
        "layout": "ledger",
        "body_key": "steps",
        "item_fields": ("label", "value"),
        "count": 4,
        "brief": """FORMAT: THE MATH. A short worked calculation the reader can redo with their \
own numbers. This is the safest format for numbers because the arithmetic is true by definition - \
but ONLY use relationships that genuinely are definitional (break-even ROAS = 1 / gross margin; \
max cost per lead = order value x margin x close rate). Never present a benchmark as the answer.
- steps: EXACTLY 4 objects with "label" and "value".
  "label" = what this line of the calculation is ("Average order value", "Gross margin").
  "value" = the illustrative figure or expression ("EUR 400", "40%", "= EUR 160"). Keep it very \
short - it renders large on the right.
  State clearly via the subtitle that the figures are an example. The final step should be the \
result the reader actually needs.
- takeaway: one sentence, under 90 characters, on what to do with the result.""",
    },
    "teardown": {
        "layout": "marked_list",
        "marker": "step",
        "body_key": "items",
        "item_fields": ("action", "detail"),
        "count": 4,
        "brief": """FORMAT: TEARDOWN. Walk through a generic, anonymised situation the way you'd \
diagnose it in an account review. This format demonstrates judgement, which is what actually \
builds credibility.
- items: EXACTLY 4 objects with "action" and "detail", in this fixed order:
  1. action = "The setup" - detail describes a common, generic situation (no real client, no \
invented specifics presented as fact).
  2. action = "What's actually wrong" - detail names the diagnosis.
  3. action = "The fix" - detail gives the concrete change.
  4. action = "The principle" - detail states the general rule worth remembering.
  Keep it generic and illustrative. Do NOT invent a client, a company name, or specific results \
that sound like a case study - that would be fabrication.""",
    },
}

# Rotation order. Date-driven so the same format never lands twice in a row and
# the week has a predictable rhythm.
FORMAT_ORDER = ["swap", "checklist", "the_math", "red_flags", "teardown"]


def pick_format(today: date | None = None) -> str:
    today = today or date.today()
    return FORMAT_ORDER[today.toordinal() % len(FORMAT_ORDER)]


def build_user_prompt(fmt_name: str) -> str:
    spec = FORMATS[fmt_name]
    niche = random.choice(NICHES)
    angle = random.choice(ANGLES)
    today = date.today().isoformat()
    return (
        f"Date: {today}\n"
        f"Niche for this post: {niche}\n"
        f"Theme to explore: {angle}\n\n"
        f"{spec['brief']}\n\n"
        f"Write one LinkedIn post in the format above for this niche and theme. "
        f"Produce the '{spec['body_key']}' field with EXACTLY {spec['count']} items. "
        "Name real settings and real metrics, but obey the accuracy gate: no invented platform "
        "mechanics, no fabricated statistics, no benchmarks asserted as standards. "
        "Before you output, re-read every body line and delete any that an experienced media "
        "buyer would call wrong, hand-wavy, or growth-hacky. No generic marketing filler."
    )


# Keys the image renderer genuinely needs - a response without these is unusable.
CRITICAL_KEYS = ["topic", "title_main", "title_highlight", "subtitle",
                 "hook_line", "intro", "pairs"]

# Caption-only keys - if the model drops one, fall back rather than fail the run.
OPTIONAL_DEFAULTS = {
    "closing": "",
    "cta_save": "Save this for your next ad account review.",
    "cta_question": "Which side of this chart sounds more like you?",
    "hashtags": ["#GoogleAds", "#MetaAds", "#EmailMarketing",
                 "#SmallBusiness", "#DigitalMarketingIreland"],
    "image_prompt": "",
}


def _call_mistral_once(fmt_name: str) -> dict:
    spec = FORMATS[fmt_name]
    body_key = spec["body_key"]
    fields = spec["item_fields"]

    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(fmt_name)},
        ],
        "temperature": 0.9,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = json.loads(resp.json()["choices"][0]["message"]["content"])

    missing = [k for k in CRITICAL_KEYS if k not in data]
    if missing:
        raise ValueError(f"Mistral response missing keys: {missing}")
    if body_key not in data or not isinstance(data[body_key], list):
        raise ValueError(f"missing or malformed body field '{body_key}'")

    # Length gate, enforced in code because prompt instructions alone don't
    # hold. Drop non-compliant items and keep the rest; only retry if too few
    # survive. An unattended daily bot should degrade, not die.
    kept, dropped = [], []
    for item in data[body_key]:
        if not isinstance(item, dict):
            dropped.append("not an object")
            continue
        vals = {f: str(item.get(f, "")).strip() for f in fields}
        if not all(vals.values()):
            dropped.append("empty field")
            continue
        # The secondary field ("detail"/"value") gets a looser budget than the
        # primary headline field, which renders larger.
        over = False
        for i, f in enumerate(fields):
            limit = MAX_LINE_CHARS if i == 0 else MAX_DETAIL_CHARS
            if len(vals[f]) > limit:
                dropped.append(f"{f} {len(vals[f])} chars: {vals[f][:45]}")
                over = True
        if not over:
            kept.append(vals)

    for d in dropped:
        print(f"  dropped item ({d})")

    need = min(MIN_USABLE_PAIRS, spec["count"])
    if len(kept) < need:
        raise ValueError(
            f"only {len(kept)} of {len(data[body_key])} {body_key} met the "
            f"length limits (need {need})"
        )
    data[body_key] = kept[:spec["count"]]

    if len(data["title_highlight"].strip()) > MAX_HIGHLIGHT_CHARS:
        raise ValueError(
            f"title_highlight is {len(data['title_highlight'])} chars "
            f"(max {MAX_HIGHLIGHT_CHARS}): {data['title_highlight']}"
        )

    data["format"] = fmt_name
    data["layout"] = spec["layout"]
    if "marker" in spec:
        data["marker"] = spec["marker"]
    return data


def generate_post() -> dict:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not set - add it as a GitHub Actions secret.")

    fmt_name = pick_format()
    print(f"Format for today: {fmt_name}")

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            data = _call_mistral_once(fmt_name)
            break
        except Exception as e:  # bad JSON, missing keys, transient API errors
            last_error = e
            print(f"Mistral attempt {attempt}/3 failed: {e}")
    else:
        raise RuntimeError(f"Mistral failed after 3 attempts: {last_error}")

    for key, default in OPTIONAL_DEFAULTS.items():
        if not data.get(key):
            print(f"Filling missing optional key with default: {key}")
            data[key] = default

    # Second pass: skeptical review + rewrite. Non-fatal by design.
    print("Running critic pass...")
    data = critique_and_revise(data, fmt_name)
    return data


CRITIC_PROMPT = """You are a media buyer with fifteen years running Google and Meta accounts for \
small businesses. You are reviewing a draft LinkedIn graphic before it is published to an audience \
that includes other marketers and business owners who buy ads. Your job is to catch anything that \
would embarrass the author or mislead a reader. You are blunt and you do not praise.

You are given the format brief, the item field names, and the items. Review every item against \
these tests, in priority order:

1. FACTUAL: does any line state something untrue, or assert a platform behaviour that doesn't \
exist? Does any line quote an industry benchmark ("good ROAS is 3.0", "aim for 2% CTR") as if it \
were a standard? Benchmarks vary by sector and margin - asserting one is an error.
2. FABRICATION: is any statistic invented, or any causal promise made that can't be supported \
("do X and get Y% more leads")?
3. USEFULNESS: would the answer to this question actually change a hiring or budget decision? \
Platform-metric trivia ("what's your benchmark CPM?") is noise. Money-and-outcome questions \
("what did we pay per booked job?") are signal. Cut the noise.
4. FORMAT FIT: does every item do the job the format brief describes? For a swap chart the "weak" \
side must be genuinely naive - if it's a sensible question the contrast collapses. For a checklist \
every action must be something the reader can actually do this week. For red flags every line must \
be an observable symptom, hedged rather than asserted as proof. For a teardown the four steps must \
actually diagnose, not just describe. For the math every relationship must be true by definition.
5. DISTINCTNESS: do any two items attack the same underlying problem? If so, replace one.
6. AUDIENCE: is it consistent? These are small business owners in Ireland. Flag drift into \
"ecommerce" or enterprise assumptions unless the topic calls for it.
7. LENGTH: the FIRST field of each item must be 62 characters or fewer; the second field 90 or \
fewer. Count them.

Then rewrite. Return the full set of items, keeping any that pass untouched and replacing any that \
fail, using EXACTLY the same field names you were given and the same number of items.

Output ONLY valid JSON, nothing else:
{
  "issues": ["short description of each problem you found, or empty list if none"],
  "items": [{"<field1>": "string", "<field2>": "string"}]
}"""


def critique_and_revise(data: dict, fmt_name: str = "swap") -> dict:
    """Second pass: a skeptical media buyer reviews the draft and rewrites
    weak or wrong lines. Best-effort - any failure leaves the draft untouched,
    because a slightly weaker post beats a failed run."""
    spec = FORMATS.get(fmt_name, FORMATS["swap"])
    body_key = spec["body_key"]
    fields = spec["item_fields"]
    try:
        payload = {
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": CRITIC_PROMPT},
                {"role": "user", "content": json.dumps({
                    "format": fmt_name,
                    "format_brief": spec["brief"],
                    "topic": data.get("topic", ""),
                    "subtitle": data.get("subtitle", ""),
                    "item_fields": list(fields),
                    "items": data[body_key],
                }, ensure_ascii=False)},
            ],
            "temperature": 0.4,   # lower than drafting: this is judgement, not ideation
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        }
        resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = json.loads(resp.json()["choices"][0]["message"]["content"])

        for issue in result.get("issues", []):
            print(f"  critic: {issue}")

        revised = []
        for p in result.get("items", result.get("pairs", [])):
            if not isinstance(p, dict):
                continue
            vals = {f: str(p.get(f, "")).strip() for f in fields}
            if not all(vals.values()):
                continue
            if any(len(vals[f]) > (MAX_LINE_CHARS if i == 0 else MAX_DETAIL_CHARS)
                   for i, f in enumerate(fields)):
                continue
            revised.append(vals)

        need = min(MIN_USABLE_PAIRS, spec["count"])
        if len(revised) >= need:
            print(f"  critic revision accepted ({len(revised)} items)")
            data[body_key] = revised[:spec["count"]]
        else:
            print(f"  critic revision rejected ({len(revised)} usable items) - keeping draft")
    except Exception as e:
        print(f"  critic pass failed, keeping draft (non-fatal): {e}")
    return data


def build_caption(data: dict) -> str:
    """Assembles the actual LinkedIn post text (the 'commentary' field)."""
    parts = [
        data["hook_line"],
        data["intro"],
        data.get("closing", ""),
        data.get("cta_save", ""),
        data.get("cta_question", ""),
        " ".join(data.get("hashtags", [])),
    ]
    return "\n\n".join(p for p in parts if p)


if __name__ == "__main__":
    post = generate_post()
    print(json.dumps(post, indent=2, ensure_ascii=False))
    print("\n--- CAPTION PREVIEW ---\n")
    print(build_caption(post))
