"""
Renders today's top carousel as a Reel and publishes it to Instagram.

WHY REELS (2026-08-08): 17 days of carousel data showed reach pinned at 2-3 per post,
never once above 3, with likes exceeding reach every day -- i.e. no distribution beyond
a couple of known accounts. Carousels reach followers plus hashtag search; with almost
no followers that is almost nobody. Reels are the only format Instagram pushes into cold
Explore/Reels feeds, so this is the change that actually opens a distribution path.

SAME API, NO NEW APPROVAL. This uses the identical host, token and permission the
carousel poster already uses -- graph.instagram.com with instagram_business_content_publish.
Reels needed no App Review, no new permission and no Facebook Page. The only request
difference is media_type=REELS and video_url instead of image_url.

HOSTING -- READ BEFORE CHANGING THE URL. Meta cURLs whatever URL it is handed. Videos
CANNOT be served from raw.githubusercontent.com: that host returns .mp4 as
application/octet-stream with X-Content-Type-Options: nosniff (verified 2026-08-08),
which is a known Meta ingest failure. It serves .jpg as image/jpeg, which is why the
carousel poster gets away with it. GitHub Pages serves .mp4 as video/mp4, so reels are
written to docs/reels/ and published from the Pages URL. Release assets are worse still
(302 to an attachment disposition). Do not "simplify" this back to raw.

PAGES IS ASYNC. The Pages build runs after the push, so the URL 404s for a bit. This
polls the URL until it returns 200 rather than sleeping a fixed interval -- a fixed sleep
was the obvious version and it is a coin flip on a slow build.

TRIAL REELS. Meta's trial_params shows a reel ONLY to non-followers. For an account with
essentially no followers that is a feature, not a limitation: the post cannot coast on an
existing audience, so it either gets cold distribution or nothing. Enabled with --trial.
"""

import argparse, os, json, time, datetime, smtplib, subprocess, sys
import requests
from email.message import EmailMessage

import reel_engine

# Read lazily, NOT with os.environ[...] at import time. The render step deliberately
# does not get the Instagram secrets -- it only draws frames and never calls the API --
# but a hard lookup here crashed --render-only before it rendered anything (run #1,
# KeyError: IG_ACCESS_TOKEN). Missing credentials are now only an error on the publish
# path, where they are actually required.
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_BUSINESS_ACCOUNT_ID = os.environ.get("IG_BUSINESS_ACCOUNT_ID", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

GRAPH = "https://graph.instagram.com/v21.0"
REEL_LOG_PATH = "reel_posted_log.json"


def pages_url(relative_path):
    owner, repo = GITHUB_REPOSITORY.split("/")
    return f"https://{owner}.github.io/{repo}/{relative_path}"


def check(resp, ctx):
    if not resp.ok:
        raise RuntimeError(f"{ctx} failed ({resp.status_code}): {resp.text}")


def wait_for_url(url, timeout=600):
    """Block until GitHub Pages has actually published the file."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.head(url, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                if not ct.startswith("video/"):
                    raise RuntimeError(
                        f"{url} is live but served as {ct!r}, not video/*. Meta will "
                        f"reject this. Check GitHub Pages is serving docs/ correctly.")
                return True
        except requests.RequestException:
            pass
        time.sleep(15)
    raise RuntimeError(f"Pages never published {url} within {timeout}s")


def create_container(video_url, caption, trial=False):
    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": IG_ACCESS_TOKEN,
    }
    if trial:
        data["trial_params"] = json.dumps({"graduation_strategy": "SS_PERFORMANCE"})
    r = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media", data=data, timeout=90)
    check(r, "create_container")
    return r.json()["id"]


def wait_until_ready(container_id, timeout=600):
    """Video containers take far longer than image containers. Meta's guidance is to
    poll once a minute for up to five; this polls every 15s for up to ten because a
    failed evening run means no post that day."""
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{GRAPH}/{container_id}",
                         params={"fields": "status_code,status",
                                 "access_token": IG_ACCESS_TOKEN}, timeout=30)
        check(r, "status poll")
        st = r.json().get("status_code")
        if st == "FINISHED":
            return True
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id} -> {st}: {r.json()}")
        time.sleep(15)
    raise RuntimeError(f"container {container_id} never finished")


def publish(container_id, attempts=5):
    """error_subcode 2207027 ("Media ID is not available") fires immediately after a
    container reports FINISHED -- a known Graph API timing quirk, not a real failure.
    Same retry the carousel poster needed."""
    last = None
    for i in range(attempts):
        r = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media_publish",
                          data={"creation_id": container_id,
                                "access_token": IG_ACCESS_TOKEN}, timeout=90)
        if r.ok:
            return r.json()["id"]
        last = r.text
        if "2207027" in r.text or r.status_code >= 500:
            time.sleep(20 * (i + 1))
            continue
        break
    raise RuntimeError(f"media_publish failed: {last}")


def log_post(entry):
    log = []
    if os.path.exists(REEL_LOG_PATH):
        try:
            log = json.load(open(REEL_LOG_PATH))
        except Exception:
            log = []
    log.append(entry)
    json.dump(log, open(REEL_LOG_PATH, "w"), indent=2)


def email(subject, body):
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD):
        return
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subject, GMAIL_ADDRESS, TO_EMAIL
    m.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            s.send_message(m)
    except Exception as e:
        print(f"email failed (non-fatal): {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true",
                    help="Render the MP4 and exit. The workflow uses this to produce and "
                         "commit the file before Pages can serve it.")
    ap.add_argument("--publish-only", action="store_true",
                    help="Skip rendering; publish the already-committed MP4.")
    ap.add_argument("--trial", action="store_true",
                    help="Publish as a trial reel (non-followers only).")
    ap.add_argument("--index", type=int, default=None,
                    help="Force a specific carousel index instead of the top-scoring one.")
    ap.add_argument("--target-count", type=int, default=1,
                    help="By the end of this slot, exactly this many reels should have "
                         "gone out today. Mirrors instagram_post.py: GitHub fires each "
                         "cron window many times, so a slot that just posted the next "
                         "unposted winner would fire twice in one window and collapse "
                         "the spread. With a target, later ticks see it met and no-op.")
    args = ap.parse_args()

    if not args.render_only:
        missing = [k for k, v in (("IG_ACCESS_TOKEN", IG_ACCESS_TOKEN),
                                  ("IG_BUSINESS_ACCOUNT_ID", IG_BUSINESS_ACCOUNT_ID),
                                  ("GITHUB_REPOSITORY", GITHUB_REPOSITORY)) if not v]
        if missing:
            raise SystemExit(f"Publishing needs these env vars and they are not set: {missing}. "
                             f"Check the env: block on the publish step in reel-post.yml.")

    today = datetime.date.today().isoformat()
    manifest_path = os.path.join("posts", today, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"No manifest at {manifest_path} — generation didn't run today. Nothing to do.")
        return
    manifest = json.load(open(manifest_path))
    if manifest.get("batch_date") != today:
        print(f"Manifest batch_date {manifest.get('batch_date')} != {today}. Skipping.")
        return

    carousels = manifest["carousels"]

    # Which carousels already became reels today. Two reels a day means the second slot
    # must pick a DIFFERENT carousel, so selection is by "next unposted winner" rather
    # than "highest score" -- the latter would re-render the same one twice.
    posted_today = []
    if os.path.exists(REEL_LOG_PATH):
        try:
            posted_today = [e for e in json.load(open(REEL_LOG_PATH)) if e.get("date") == today]
        except Exception:
            posted_today = []
    posted_indices = {e.get("index") for e in posted_today}

    if args.index:
        pick = next(c for c in carousels if c["index"] == args.index)
    else:
        winners = [c for c in carousels if c.get("post_to_instagram")] or carousels
        ranked = sorted(winners,
                        key=lambda c: c["virality_score"] if c.get("virality_score") is not None else -1,
                        reverse=True)
        need = max(0, args.target_count - len(posted_today))
        if need == 0:
            print(f"{len(posted_today)} reel(s) already posted for {today}, target is "
                  f"{args.target_count}. Nothing to do.")
            return
        remaining = [c for c in ranked if c["index"] not in posted_indices]
        if not remaining:
            print(f"All {len(ranked)} winning carousels for {today} have already been "
                  f"posted as reels. Nothing left.")
            return
        pick = remaining[0]

    rel = f"docs/reels/{today}/carousel_{pick['index']}.mp4"
    # url is built later, on the publish path only -- pages_url needs GITHUB_REPOSITORY,
    # which the render step has no reason to depend on.

    if not args.publish_only:
        os.makedirs(os.path.dirname(rel), exist_ok=True)
        path, dur, credit = reel_engine.render_reel(pick, today, pick["index"], rel, "/tmp/reelwork")
        if not path:
            print(f"Carousel {pick['index']} has no reel_beats and no body_slides — "
                  f"nothing to render. Skipping.")
            return
        print(f"Rendered {rel} ({dur:.1f}s, {os.path.getsize(rel)/1048576:.2f} MB)")
        if args.render_only:
            return

    url = pages_url(f"reels/{today}/carousel_{pick['index']}.mp4")
    print(f"Waiting for GitHub Pages to serve {url} ...")
    wait_for_url(url)

    # The music credit has to be recomputed here because --publish-only runs in a
    # separate step from --render-only, and pick_track is deterministic on
    # (batch_date, index) precisely so both steps resolve the same track.
    credit = reel_engine.credit_for(reel_engine.pick_track(today, pick["index"]))
    caption = pick.get("caption", "")
    if credit:
        caption = f"{caption}\n\nMusic: {credit}"
    cid = create_container(url, caption, trial=args.trial)
    print(f"container {cid}")
    wait_until_ready(cid)
    media_id = publish(cid)
    print(f"published reel {media_id}")

    log_post({
        "media_id": media_id, "date": today, "index": pick["index"],
        "niche": pick.get("niche", ""), "angle": pick.get("angle", ""),
        "format": pick.get("format", ""), "hook": pick.get("hook", ""),
        "media_product_type": "REELS", "trial": bool(args.trial), "scored": False,
    })
    email(f"Reel posted {today}", f"{pick.get('hook','')}\n\n{url}\nmedia_id {media_id}")


if __name__ == "__main__":
    main()
