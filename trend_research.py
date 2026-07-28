"""
Weekly content-trend research.

Searches the public web (via Tavily) for what's currently working in
short-form social content -- Instagram Reels/carousels, TikTok -- and asks
Mistral to distill it into a compact, copyright-safe briefing of
STRUCTURAL patterns (hook shapes, format ideas, pacing, design trends),
never specific copy. Writes trend_briefing.json, which runner.py reads
(see load_trend_briefing() there) and weaves into the content brain's
generation calls alongside the existing performance/history briefings.

Why this doesn't scrape Instagram or TikTok directly: there is no free,
ToS-compliant way to pull individual posts/reels off either platform --
official APIs don't expose competitor/discovery data, and third-party
scraping is both against this project's "free APIs only" constraint and
against those platforms' terms of service. Tavily is a web search API, not
a social scraper -- what it CAN do, legally and for free, is search
marketing publications, blogs, and reporting that discuss what's working
on those platforms. That's a real, useful signal, just one step removed
from the raw platform data.

Runs weekly, not daily: content-format trends don't meaningfully shift day
to day, and running this weekly keeps Tavily usage a small fraction of its
free-tier monthly quota (a handful of searches/week vs. the daily
Google/Meta Ads news pull runner.py already does).

Runs inside GitHub Actions on a schedule -- see
.github/workflows/trend_research.yml. Fails open like every other
optional-context step in this repo: if Tavily or Mistral are unavailable,
or the research comes back too thin to be useful, trend_briefing.json is
just left as whatever it already was, and next week's run tries again.
Never touches posts/, history.json, or anything else in the pipeline.
"""

import os
import json
import datetime
import requests

TAVILY_URL = "https://api.tavily.com/search"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
TREND_PATH = "trend_briefing.json"

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

# Kept to a handful of broad, non-platform-scraping queries -- searching
# what marketing writers/analysts are saying about short-form content
# right now, not trying to enumerate individual posts.
QUERIES = [
    "Instagram carousel post trends what's working",
    "TikTok Instagram Reels hook formats going viral marketing",
    "short form video content design trends social media",
]


def search_tavily(query):
    """One Tavily search, title+snippet only. Never raises -- a single
    failed query just means less signal for this week's briefing, not a
    failed run."""
    try:
        resp = requests.post(
            TAVILY_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TAVILY_API_KEY}",
            },
            json={
                "query": query,
                "topic": "general",
                "search_depth": "basic",
                "time_range": "month",
                "max_results": 4,
                "include_answer": True,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Tavily search failed for '{query}' (non-fatal): {e}")
        return None

    bits = []
    if data.get("answer"):
        bits.append(data["answer"])
    for r in data.get("results", [])[:4]:
        title = r.get("title")
        # Truncated hard -- this is raw source material headed into a
        # summarization prompt whose entire job is to NOT pass specific
        # wording through, so there's no reason to hand it more text than
        # needed to identify the pattern being discussed.
        snippet = (r.get("content") or "")[:300]
        if title:
            bits.append(f"{title}: {snippet}")
    return "\n".join(bits) if bits else None


def summarize_with_mistral(raw_research):
    with open("trend_research_system_prompt.txt") as f:
        system_prompt = f.read()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
    }
    body = {
        "model": "mistral-large-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Raw research snippets from this week's search:\n\n" + raw_research},
        ],
        "temperature": 0.4,
    }
    resp = requests.post(MISTRAL_URL, headers=headers, json=body, timeout=90)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def main():
    if not TAVILY_API_KEY:
        print("TAVILY_API_KEY not set -- skipping trend research (optional feature, never blocks the rest of the pipeline).")
        return
    if not MISTRAL_API_KEY:
        print("MISTRAL_API_KEY not set -- skipping trend research.")
        return

    raw_chunks = []
    for q in QUERIES:
        result = search_tavily(q)
        if result:
            raw_chunks.append(f"=== {q} ===\n{result}")

    if not raw_chunks:
        print("No usable research returned this week -- leaving existing trend_briefing.json untouched.")
        return

    # Keep the summarization call itself cheap and fast regardless of how
    # much raw text came back.
    raw_research = "\n\n".join(raw_chunks)[:6000]

    try:
        briefing = summarize_with_mistral(raw_research)
    except Exception as e:
        print(f"Mistral summarization failed (non-fatal): {e}")
        return

    if not briefing:
        print("Empty briefing returned -- leaving existing trend_briefing.json untouched.")
        return

    data = {"updated": datetime.date.today().isoformat(), "briefing": briefing}
    with open(TREND_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {TREND_PATH} ({len(briefing)} chars).")
    print("---")
    print(briefing)


if __name__ == "__main__":
    main()
