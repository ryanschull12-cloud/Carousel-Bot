"""
smoke_test_fixtures.py -- the copy the smoke test renders.

WHY REAL COPY (2026-08-09): the old fixtures said "Sample body slide 2 for the
checklist smoke test, long enough to wrap." Every line was the same length, the
same shape, and contained no currency symbols, no curly quotes, no em dashes and
no numbers -- so the fitter never had to shrink, the highlight keyword never had
to sit under a descender, and nothing was ever tested at the length the content
brain actually produces. The test was rendering a document that would never exist.

These fixtures are written to the same rules as the content brain: hooks under
10 words, body slides under 12 words, specific numbers, one niche each. Then a
set of deliberately hostile cases, because the fitter's failure modes live at the
extremes and the content brain will eventually hit them.
"""

# --- realistic: one per niche, written to the content rules --------------------
GOOGLE = {
    "niche": "Google Ads",
    "angle": "mistake/myth-busting",
    "format": "myth-buster",
    "hook_slide": "Broad match is spending 30% of your budget",
    "hook_pop_phrase": "30%",
    "bridge_slide": "The setting most clinics miss costs €400 a week",
    "bridge_pop_phrase": "€400",
    "body_slides": [
        {"text": "Search terms report. Last 30 days. Read it.", "keyword": "Search terms"},
        {"text": "Add 'free', 'cheap', 'jobs' as negatives today", "keyword": "negatives"},
        {"text": "Most accounts run zero negative keywords at all", "keyword": "zero"},
        {"text": "Phrase match cuts wasted spend by roughly 30%", "keyword": "30%"},
        {"text": "Good cost-per-lead is lower than you think — €18", "keyword": "€18"},
        {"text": "Check weekly. Not just when the leads stop.", "keyword": "weekly"},
    ],
    "recap_slide": [
        "Pull the search terms report",
        "Add three negatives now",
        "Switch broad to phrase",
        "Benchmark against €18 a lead",
        "Review every Monday",
        "Kill anything over €40",
    ],
    "cta_slide": "Most accounts leak for months before anyone checks.",
    "cta_word": "AUDIT",
    "cta_promise": "my 7-point wasted-spend checklist",
    "cta_save_line": "Save this for your next account audit",
    "cta_support": "Free this week",
    "caption": "Broad match is the default and the default is a trap. #googleads #ppc #smallbusiness",
    "reel_beats": {
        # Rewritten 2026-08-09 to the CURRENT contract: a plain-language hook with
        # no jargon and a stake the reader feels, then four body lines of 65-95
        # characters that form one argument -- what happens, why, what it costs,
        # what to do. The previous version was written to the old contract (named
        # platform, sub-34-character fragments) and would now fail its own checks,
        # which is the point of updating it: the fixture has to be copy the content
        # brain is actually allowed to produce, or the renderer is tested on
        # nothing real.
        "hook": "You are paying Google for customers who were never going to call",
        "body": [
            "Google matches your ads to searches you never chose, and bills you the same either way.",
            "It guesses at what you meant by a keyword, so it buys traffic close to it but not it.",
            "About a third of the average budget goes to those near-misses every single month.",
            "Open the search terms report, sort by cost, and block every search that never converted.",
        ],
        "cta_line": "the 7-point checklist",
    },
}

META = {
    "niche": "Meta/Instagram Ads",
    "angle": "numbers/proof",
    "format": "before-after",
    "hook_slide": "Your Meta ads died on day 4. Here's why.",
    "hook_pop_phrase": "day 4",
    "bridge_slide": "Nothing was wrong with the ad. You restarted learning.",
    "bridge_pop_phrase": "learning",
    "body_slides": [
        {"text": "Every edit resets the learning phase. Every one.",
         "keyword": "resets", "before": "€45/lead", "after": "€15/lead"},
        {"text": "50 conversions per week before it stabilises", "keyword": "50"},
        {"text": "Budget changes over 20% count as an edit", "keyword": "20%"},
        {"text": "Stop touching it for seven full days", "keyword": "seven"},
        {"text": "Consolidate ad sets. Three beats eleven.", "keyword": "Three"},
        {"text": "Judge on 14 days, never on 48 hours", "keyword": "14 days"},
    ],
    "recap_slide": [
        "Leave it alone for 7 days",
        "Keep budget moves under 20%",
        "Merge ad sets down to three",
        "Target 50 conversions weekly",
        "Judge results at day 14",
        "Never optimise on a Monday panic",
    ],
    "cta_slide": "Learning phase resets are the most expensive habit in Meta ads.",
    "cta_word": "RESET",
    "cta_promise": "the exact 14-day testing template",
    "cta_save_line": "Save this before you touch that campaign",
    "cta_support": "Two slots left",
    "caption": "You didn't have a bad ad. You had an itchy trigger finger. #metaads #facebookads #dtc",
    "reel_beats": {
        "hook": "Every edit you make throws away what your ads just learned",
        "body": [
            "Facebook spends the first week of any campaign working out who actually buys from you.",
            "Changing the budget or the creative wipes that progress and starts the week again.",
            "Restless accounts stay in that expensive learning window permanently, and never leave.",
            "Leave a new campaign untouched for seven days, then judge it on day fourteen.",
        ],
        "cta_line": "the 14-day template",
        "proof": {"before": "€45", "after": "€15", "label": "cost per lead, 14 days"},
    },
}

EMAIL = {
    "niche": "Email Marketing",
    "angle": "behind-the-curtain",
    "format": "steal-this",
    "hook_slide": "Stop sending your best email at 9am",
    "hook_pop_phrase": "9am",
    "bridge_slide": "The abandoned cart flow nobody sets up properly",
    "bridge_pop_phrase": "abandoned cart",
    "body_slides": [
        {"text": "Email one goes out at 60 minutes. Not 24 hours.", "keyword": "60 minutes"},
        {"text": "No discount in email one. Ever.", "keyword": "No discount"},
        {"text": "Email two at 24 hours: handle the objection", "keyword": "objection"},
        {"text": "Email three at 72 hours: 10% and a deadline", "keyword": "10%"},
        {"text": "Three emails recover about 12% of carts", "keyword": "12%"},
        {"text": "Most shops send one, then give up", "keyword": "one"},
    ],
    "recap_slide": [
        "Send email one at 60 minutes",
        "Hold the discount back",
        "Answer the objection at 24 hours",
        "Add urgency at 72 hours",
        "Expect around 12% recovered",
        "Turn it on once, earns forever",
    ],
    "cta_slide": "This flow runs itself once it's built.",
    "cta_word": "FLOW",
    "cta_promise": "all three emails, written",
    "cta_save_line": "Save this for your next flow build",
    "cta_support": "Takes an hour to set up",
    "caption": "Three emails. Built once. Recovers 12% of carts forever. #emailmarketing #ecommerce #klaviyo",
    "reel_beats": {
        "hook": "Your abandoned cart email arrives a day after they stopped caring",
        "body": [
            "Most shops send the first cart reminder the next morning, on a default nobody changed.",
            "By then the customer has either bought elsewhere or forgotten the basket entirely.",
            "That delay quietly costs about one in eight carts that were still winnable at the time.",
            "Send the first reminder one hour after they leave, before the intent has cooled off.",
        ],
        "cta_line": "all three emails written",
    },
}

REALISTIC = [GOOGLE, META, EMAIL]


# --- hostile: where the fitter actually breaks ---------------------------------
def _clone(base, **over):
    d = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}
    d.update(over)
    return d


LONGEST = _clone(
    GOOGLE,
    format="checklist",
    hook_slide="Your Google Ads account is quietly burning roughly forty percent "
               "of every euro you put into it this month",
    hook_pop_phrase="forty percent of every euro",
    bridge_slide="The one campaign setting nearly every small business owner leaves "
                 "switched on by accident when they build their first search campaign",
    bridge_pop_phrase="nearly every small business owner",
    body_slides=[
        {"text": "Open the search terms report and sort by total cost descending, "
                 "then read every single line before you touch anything else",
         "keyword": "search terms report"},
        {"text": "Add negative keywords at the campaign level, not the ad group level, "
                 "or you will be doing this again next month",
         "keyword": "campaign level"},
    ] + GOOGLE["body_slides"][2:],
)

SHORTEST = _clone(
    META,
    format="comparison",
    hook_slide="Stop.",
    hook_pop_phrase="Stop.",
    bridge_slide="Why?",
    bridge_pop_phrase="Why?",
    body_slides=[{"text": "Pause it.", "keyword": "Pause",
                  "compare_a": "Manual bidding", "compare_b": "Automated bidding"}]
    + META["body_slides"][1:],
)

UNBREAKABLE = _clone(
    EMAIL,
    format="steal-this",
    hook_slide="Check your deliverability@authentication-record settings",
    hook_pop_phrase="deliverability@authentication-record",
    body_slides=[{"text": "Set DMARC to p=quarantine;rua=mailto:you@yourdomain.example.com",
                  "keyword": "p=quarantine"}] + EMAIL["body_slides"][1:],
)

MISSING_FIELDS = {
    # No bridge_slide, no recap_slide, no pop phrases, no reel_beats -- exercises
    # every fallback branch in render_carousel and beats_from_carousel at once.
    "niche": "Google Ads",
    "angle": "contrarian",
    "format": "step-by-step",
    "hook_slide": "You do not need a bigger budget",
    "body_slides": [
        {"text": "You need a smaller keyword list", "keyword": "smaller"},
        {"text": "Cut anything with zero conversions in 90 days", "keyword": "zero"},
        {"text": "Put the saved spend into what already works", "keyword": "already works"},
        {"text": "Most accounts improve without spending more", "keyword": "improve"},
    ],
    "cta_word": "CUT",
    "cta_promise": "the pruning checklist",
    "caption": "Smaller, not bigger. #googleads",
}

HOSTILE = [
    ("longest-copy", LONGEST),
    ("shortest-copy", SHORTEST),
    ("unbreakable-strings", UNBREAKABLE),
    ("missing-fields", MISSING_FIELDS),
]

# Format coverage still matters -- each one lights up a different render branch.
FORMATS = ["checklist", "steal-this", "myth-buster", "comparison", "before-after"]


def format_cases():
    """One realistic carousel per format, rotating niche so no two consecutive
    cases share a palette."""
    out = []
    for i, fmt in enumerate(FORMATS):
        base = REALISTIC[i % len(REALISTIC)]
        c = _clone(base, format=fmt)
        b0 = dict(c["body_slides"][0])
        if fmt == "before-after":
            b0["before"], b0["after"] = "€45/lead", "€15/lead"
        if fmt == "comparison":
            b0["compare_a"], b0["compare_b"] = "Broad match", "Phrase match"
        c["body_slides"] = [b0] + list(c["body_slides"][1:])
        out.append((fmt, c))
    return out
