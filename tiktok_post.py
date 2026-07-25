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
"""

import argparse
import os
import sys
import json
import time
import glob
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


def post_carousel(access_token, privacy_level, carousel):
    photo_urls = [public_url(p) for p in carousel["image_paths"]]
    title = carousel.get("hook") or carousel.get("caption", "")
    description = carousel.get("caption", "")

    publish_id = init_post(access_token, photo_urls, title, description, privacy_level)
    wait_until_complete(access_token, publish_id)
    print(f"Posted carousel {carousel['index']} to TikTok -> publish_id {publish_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="Path to a specific manifest.json (defaults to today's/most recent)")
    parser.add_argument("--only-index", type=int, help="Only post the carousel with this index (e.g. 1 or 2)")
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

    to_post = [c for c in manifest["carousels"] if c.get("post_to_instagram")]
    if args.only_index is not None:
        to_post = [c for c in to_post if c["index"] == args.only_index]

    if not to_post:
        print("No carousels matched — nothing to post to TikTok.")
        return

    access_token = refresh_access_token()
    privacy_level = get_privacy_level(access_token)
    print(f"Posting {len(to_post)} carousel(s) to TikTok (privacy_level={privacy_level})...")

    for i, carousel in enumerate(to_post):
        try:
            post_carousel(access_token, privacy_level, carousel)
        except Exception as e:
            print(f"FAILED to post carousel {carousel['index']}: {e}")
            send_failure_alert(carousel["index"], str(e))
        if i < len(to_post) - 1:
            time.sleep(MINUTES_BETWEEN_POSTS * 60)


if __name__ == "__main__":
    main()
