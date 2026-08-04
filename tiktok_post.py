"""
Publishes carousels marked post_to_instagram=true in today's manifest
to TikTok as photo-mode Direct Posts, using images already committed and
pushed to the repo (so they're reachable at a public raw.githubusercontent.com
URL) -- the same images used for the Instagram post.

Reuses the post_to_instagram flag rather than a separate post_to_tiktok
flag, since right now the same winning carousels go to both platforms.
If that ever needs to diverge, add a post_to_tiktok flag to the manifest
and switch the filter below.

Auth: TikTok user access tokens expire after 24h, so this script always
starts by exchanging the long-lived TIKTOK_REFRESH_TOKEN (valid ~1 year)
for a fresh access token -- no manual re-connect needed as long as the
refresh token stays valid. If TikTok ever invalidates it, admin.html's
"Connect TikTok Account" flow generates a new one.

privacy_level: while the app is unaudited, TikTok forces all API posts
to SELF_ONLY (private/"Only me") -- see TIKTOK_PRIVACY_LEVEL below. Once
the Content Posting API audit is approved, set TIKTOK_PRIVACY_LEVEL to
PUBLIC_TO_EVERYONE (as a repo variable) and posts go fully public with
no code change.

SCHEDULING/DEDUPE (added 2026-08-04): this script used to be triggered by
a workflow that checked "is Irish local time == 9am right now?" with only
two cron shots (8:00 and 9:00 UTC) to cover BST/GMT. Checking the last 10
scheduled runs showed every one of them firing hours late (11:45, 16:13,
16:27 UTC, etc.) -- GitHub's scheduled-workflow queue for this repo is
best-effort with no guaranteed delivery time (see daily.yml's 2026-07-27
comment for the same discovery on the Instagram side), so by the time the
run actually started, the hour==9 check was always false and the whole
post step was skipped. Every single day. The workflow now fires every 15
minutes across a wide window instead of one exact shot, and this script
tracks what it's already posted today in tiktok_posted_log.json (mirroring
instagram_post.py's posted_log.json) so the extra ticks are near-instant
no-ops instead of duplicate posts.

3x/DAY CADENCE (added 2026-08-04): TikTok now posts on the same schedule
as Instagram -- the same up-to-3 winning carousels, once each, spread
across tiktok-post.yml (morning, --target-count 1),
tiktok-post-midday.yml (--target-count 2), and tiktok-post-evening.yml
(--target-count 3). See instagram_post.py's docstring for why
--target-count (not a fixed carousel index) is what keeps a slot's
several 15-minute ticks from posting more than once.
"""

import argparse
import os
import sys
import json
import time
import glob
import datetime
import smtplib
import requests
from email.message import EmailMessage

TIKTOK_CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
TIKTOK_CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
TIKTOK_REFRESH_TOKEN = os.environ["TIKTOK_REFRESH_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]  # e.g. "ryanschull12-cloud/Carousel-Bot"
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

# Defaults to SELF_ONLY because that's the only option TikTok allows for
# an unaudited app -- see the module docstring. Override via repo variable
# once the app is approved. Using "or" rather than dict.get's default
# because GitHub Actions passes unset repo variables through as an empty
# string (not an absent key), which would otherwise silently defeat the
# default and fall through to get_privacy_level()'s options[0] fallback.
TIKTOK_PRIVACY_LEVEL = os.environ.get("TIKTOK_PRIVACY_LEVEL") or "SELF_ONLY"

API = "https://open.tiktokapis.com/v2"
POSTED_LOG_PATH = "tiktok_posted_log.json"

# TikTok's photo-mode title cap is 90 UTF-16 code units; description caps
# at 4000. Truncating defensively so a long AI-generated hook/caption
# never causes an invalid_param error instead of just being clipped.
TITLE_MAX = 90
DESCRIPTION_MAX = 4000

MINUTES_BETWEEN_POSTS = 2
STATUS_POLL_TIMEOUT_SECONDS = 120
STATUS_POLL_INTERVAL_SECONDS = 5


def check_response(resp, context):
    """Raise a detailed error including TikTok's actual response body,
    instead of the generic message requests.raise_for_status() gives."""
    if not resp.ok:
        raise RuntimeError(f"{context} failed ({resp.status_code}): {resp.text}")


def public_url(relative_path):
    # Uses the "main" branch HEAD, which is current since the images are
    # committed and pushed by the daily workflow before this script runs.
    rel = relative_path.replace(os.sep, "/")
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/{rel}"


def refresh_access_token():
    resp = requests.post(f"{API}/oauth/token/", data={
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": TIKTOK_REFRESH_TOKEN,
    }, timeout=30)
    check_response(resp, "refresh_access_token")
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"refresh_access_token: no access_token in response: {data}")
    return data["access_token"]


def get_privacy_level(access_token):
    """Query which privacy_level options TikTok will actually accept right
    now, and use TIKTOK_PRIVACY_LEVEL if it's one of them -- falling back
    to whatever TikTok does allow (e.g. SELF_ONLY while unaudited) rather
    than blindly sending a value the API will reject."""
    resp = requests.post(f"{API}/post/publish/creator_info/query/", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }, timeout=30)
    check_response(resp, "creator_info/query")
    data = resp.json()
    options = data.get("data", {}).get("privacy_level_options", [])
    if TIKTOK_PRIVACY_LEVEL in options:
        return TIKTOK_PRIVACY_LEVEL
    if "SELF_ONLY" in options:
        # SELF_ONLY is the one privacy_level unaudited apps are always
        # allowed to post as, so prefer it over an arbitrary options[0]
        # (which could be e.g. FOLLOWER_OF_CREATOR and get rejected with
        # unaudited_client_can_only_post_to_private_accounts).
        print(
            f"Requested privacy_level '{TIKTOK_PRIVACY_LEVEL}' isn't in the "
            f"options TikTok returned ({options}) -- using 'SELF_ONLY' instead."
        )
        return "SELF_ONLY"
    if options:
        print(
            f"Requested privacy_level '{TIKTOK_PRIVACY_LEVEL}' isn't in the "
            f"options TikTok returned ({options}) -- using '{options[0]}' instead."
        )
        return options[0]
    # No options returned at all -- fall back to the configured value and
    # let the actual post call surface a clear error if it's wrong.
    return TIKTOK_PRIVACY_LEVEL


def init_post(access_token, photo_urls, title, description, privacy_level):
    resp = requests.post(f"{API}/post/publish/content/init/", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }, json={
        "post_info": {
            "title": title[:TITLE_MAX],
            "description": description[:DESCRIPTION_MAX],
            "privacy_level": privacy_level,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": photo_urls,
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }, timeout=60)
    check_response(resp, "post/publish/content/init")
    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"content/init returned an error: {data}")
    return data["data"]["publish_id"]


def wait_until_complete(access_token, publish_id, timeout=STATUS_POLL_TIMEOUT_SECONDS):
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.post(f"{API}/post/publish/status/fetch/", headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }, json={"publish_id": publish_id}, timeout=30)
        check_response(resp, f"status/fetch({publish_id})")
        data = resp.json()
        status = data.get("data", {}).get("status")
        if status == "PUBLISH_COMPLETE":
            return True
        if status == "FAILED":
            fail_reason = data.get("data", {}).get("fail_reason", "unknown")
            raise RuntimeError(f"TikTok publish failed: {fail_reason}")
        time.sleep(STATUS_POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"publish_id {publish_id} never reached PUBLISH_COMPLETE within {timeout}s")


def send_failure_alert(carousel_index, error_text):
    msg = EmailMessage()
    msg["Subject"] = f"TikTok auto-post FAILED — carousel {carousel_index}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"Carousel {carousel_index} failed to post to TikTok today.\n\n"
        f"Error:\n{error_text}\n\n"
        "The images are still in your email attachment from today's batch "
        "if you want to post it manually instead."
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def send_stale_manifest_alert(found_date, expected_date):
    """Mirrors instagram_post.py's guard of the same name. This script
    didn't have one at all until 2026-07-27's audit -- normally the
    tiktok-post.yml scheduling gate keeps a scheduled run from firing
    before that day's manifest exists, but a manual workflow_dispatch (or
    a future change to that gate) bypasses it entirely, and this script
    would then silently repost YESTERDAY's carousel 1 with no warning."""
    msg = EmailMessage()
    msg["Subject"] = "TikTok auto-post SKIPPED — today's carousels weren't found"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"A TikTok post was skipped because the newest carousel batch on file is "
        f"dated {found_date!r}, not today ({expected_date}).\n\n"
        "This almost always means today's morning generation run hasn't completed "
        "yet, or failed — check the Actions tab for a failed 'Daily Carousels' run. "
        "Nothing was re-posted from a previous day."
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def load_posted_log():
    if not os.path.exists(POSTED_LOG_PATH):
        return {"posts": []}
    try:
        with open(POSTED_LOG_PATH) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {POSTED_LOG_PATH}, starting fresh ({e})")
        return {"posts": []}


def save_posted_log(log):
    with open(POSTED_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def post_carousel(access_token, privacy_level, carousel, posted_log, batch_date):
    photo_urls = [public_url(p) for p in carousel["image_paths"]]
    title = carousel.get("hook") or carousel.get("caption", "")
    description = carousel.get("caption", "")

    publish_id = init_post(access_token, photo_urls, title, description, privacy_level)
    wait_until_complete(access_token, publish_id)
    print(f"Posted carousel {carousel['index']} to TikTok -> publish_id {publish_id}")

    posted_log["posts"].append({
        "publish_id": publish_id,
        "date": batch_date,
        "index": carousel["index"],
        "privacy_level": privacy_level,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="Path to a specific manifest.json (defaults to today's/most recent)")
    parser.add_argument(
        "--only-index", type=int, default=None,
        help="Manual override: force-post this specific carousel index, ignoring "
             "the normal target-count selection. Mainly for manual testing.",
    )
    parser.add_argument(
        "--target-count", type=int, default=None,
        help="Mirrors instagram_post.py: by the end of this run, this many of "
             "today's winning carousels should be posted to TikTok IN TOTAL. "
             "tiktok-post.yml (morning) passes 1, tiktok-post-midday.yml passes 2, "
             "tiktok-post-evening.yml passes 3 -- same 3 carousels that go to "
             "Instagram, same cadence, tracked separately in "
             "tiktok_posted_log.json so a slow/duplicate cron tick is a no-op.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="With --only-index, post even if tiktok_posted_log.json already shows "
             "that index as posted today. Mainly for manual testing/re-posting.",
    )
    args = parser.parse_args()

    # Defense in depth, mirroring instagram_post.py's IG_POSTING_PAUSED
    # check: the workflow already skips this whole script when
    # TIKTOK_POSTING_PAUSED is "true", but this means a manual run can't
    # post while posting is paused either.
    if os.environ.get("TIKTOK_POSTING_PAUSED", "false").lower() == "true":
        print("TIKTOK_POSTING_PAUSED is set to true — skipping TikTok posting entirely.")
        return

    if args.manifest:
        manifest_path = args.manifest
    else:
        matches = sorted(glob.glob("posts/*/manifest.json"))
        if not matches:
            print("No manifest found, nothing to post.")
            return
        manifest_path = matches[-1]

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Added 2026-07-27, mirroring instagram_post.py's existing guard: the
    # scheduled workflow's window normally keeps this from firing before
    # today's manifest exists, but a manual workflow_dispatch bypasses
    # that gate entirely. Without this check a manual run on a day
    # generation is still running/broken would silently repost yesterday's
    # carousel 1 with no warning.
    if not args.manifest:
        today_str = datetime.date.today().isoformat()
        if manifest.get("batch_date") != today_str:
            print(
                f"Newest manifest on disk is dated {manifest.get('batch_date')!r}, "
                f"not today ({today_str}) — today's generation likely hasn't finished. "
                "Skipping rather than reposting stale content."
            )
            send_stale_manifest_alert(manifest.get("batch_date"), today_str)
            return

    posted_log = load_posted_log()
    batch_date = manifest.get("batch_date", "")
    already_posted_indices = {
        p["index"] for p in posted_log.get("posts", []) if p.get("date") == batch_date
    }

    winners = [c for c in manifest["carousels"] if c.get("post_to_instagram")]
    winners.sort(key=lambda c: c["index"])

    if args.only_index is not None:
        to_post = [c for c in manifest["carousels"] if c["index"] == args.only_index]
        if not args.force and to_post and to_post[0]["index"] in already_posted_indices:
            print(
                f"Carousel {args.only_index} is already logged as posted to TikTok "
                f"today ({batch_date}) — nothing to do."
            )
            return
    elif args.target_count is not None:
        # Added 2026-08-04, mirroring instagram_post.py's --target-count:
        # by the end of this run, this many of today's winners should be
        # posted to TikTok in total. Makes every extra 15-minute tick (and
        # a same-slot manual re-run) a no-op once the target's met, instead
        # of reposting or posting the wrong carousel for this slot.
        already_posted_count = len(already_posted_indices)
        need = max(0, args.target_count - already_posted_count)
        remaining = [c for c in winners if c["index"] not in already_posted_indices]
        to_post = remaining[:need]
    else:
        remaining = [c for c in winners if c["index"] not in already_posted_indices]
        to_post = remaining[:1]

    if not to_post:
        print("Nothing new to post to TikTok right now — either today's winning "
              "carousels are already posted, or none are marked post_to_instagram yet.")
        return

    access_token = refresh_access_token()
    privacy_level = get_privacy_level(access_token)
    print(f"Posting {len(to_post)} carousel(s) to TikTok (privacy_level={privacy_level})...")

    for i, carousel in enumerate(to_post):
        try:
            post_carousel(access_token, privacy_level, carousel, posted_log, batch_date)
        except Exception as e:
            print(f"FAILED to post carousel {carousel['index']}: {e}")
            send_failure_alert(carousel["index"], str(e))
        if i < len(to_post) - 1:
            time.sleep(MINUTES_BETWEEN_POSTS * 60)

    # Save whatever succeeded even if a later carousel in the loop failed.
    save_posted_log(posted_log)


if __name__ == "__main__":
    main()
