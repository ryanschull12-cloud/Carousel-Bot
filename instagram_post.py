"""
Publishes carousels marked post_to_instagram=true in today's manifest
to Instagram, using images already committed and pushed to the repo
(so they're reachable at a public raw.githubusercontent.com URL).

Runs up to THREE times a day at different scheduled times, fully
automatic — nothing in this script can hold a post back. See
.github/workflows/daily.yml for the 7:30am GMT slot (right after
generation), posts_later.yml for the 1pm GMT slot, and evening-post.yml
for the 7pm GMT slot — the latter two just re-read that same morning's
already-committed manifest. As of 2026-07-27 these are fixed GMT times
(one cron trigger each), not chasing Irish local clock time across
BST/GMT — see each workflow file for why.

WHICH CAROUSEL EACH RUN POSTS: runner.py picks the 3 auto-post winners
by virality score, not by fixed position. Each workflow passes
--target-count (1, 2, or 3) so that, by the end of its run, exactly that
many of today's winners have been posted in total. This is what keeps
the three posts genuinely spread across the day: GitHub fires TWO cron
triggers per workflow every day (one for BST, one for GMT) to cover
daylight saving, and without a target count each firing would just post
"the next unposted winner" — meaning a single workflow's two triggers,
half an hour to an hour apart, could each post a DIFFERENT carousel back
to back, collapsing what should be a morning/midday/evening spread into
a burst. With --target-count, the second firing sees the target already
met and does nothing. --only-index is kept as a manual override for
testing a specific carousel, bypassing target-count logic entirely.

PERFORMANCE LOGGING: every carousel that actually gets published gets
appended to posted_log.json with its media_id, date, niche, angle,
format, and hook. fetch_performance.py reads this file a few days later to
pull real Instagram engagement numbers and tie them back to what was
actually written, and the weekly self-review email (performance_report.py)
reads it too. This is the "review itself" half of the pipeline — it's all
retrospective (informs what gets written next, and what you see in the
weekly report), never a gate on whether something posts.

PUBLISH RETRY (added 2026-08-04): carousel 1 failed today with Instagram
Graph API error_subcode 2207027 ("Media ID is not available", "please
wait for a moment") immediately after wait_until_ready() reported the
container as FINISHED. See publish()'s retry loop below -- this is a
known Graph API timing quirk, not a real failure, and a short retry
clears it.

MANIFEST SELECTION FIX (added 2026-08-08): this used to pick
sorted(glob.glob("posts/*/manifest.json"))[-1] -- the alphabetically
LAST manifest on disk. That was fine until the "Batch Generate Week"
workflow started pre-generating several days of manifests in advance:
once posts/2026-08-09 .. posts/2026-08-12 existed, [-1] silently grabbed
the FUTURE-most manifest instead of today's, which then always failed
the batch_date-vs-today check below and made every scheduled post
no-op (with just a misleading "today's generation didn't run" email) --
that's why Instagram stopped posting even though content generation was
working fine. Now the manifest path is built directly from today's date
instead of globbed.
"""

import argparse
import os
import json
import time
import glob
import datetime
import smtplib
import requests
from email.message import EmailMessage

IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ACCOUNT_ID = os.environ["IG_BUSINESS_ACCOUNT_ID"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]  # e.g. "ryanschull12-cloud/Carousel-Bot"
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

GRAPH = "https://graph.instagram.com/v21.0"
POSTED_LOG_PATH = "posted_log.json"


def check_response(resp, context):
    """Raise a detailed error including Instagram's actual response body,
    instead of the generic message requests.raise_for_status() gives."""
    if not resp.ok:
        raise RuntimeError(f"{context} failed ({resp.status_code}): {resp.text}")


SECONDS_BETWEEN_POSTS = 90


def public_url(relative_path):
    # Uses the "main" branch HEAD, which is current since we push before
    # this script runs.
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/{relative_path}"


def create_child_container(image_url):
    resp = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media", data={
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": IG_ACCESS_TOKEN,
    }, timeout=60)
    check_response(resp, f"create_child_container({image_url})")
    return resp.json()["id"]


def create_carousel_container(child_ids, caption):
    resp = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media", data={
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }, timeout=60)
    check_response(resp, "create_carousel_container")
    return resp.json()["id"]


def wait_until_ready(container_id, timeout=120):
    # Returning a bare False on ERROR threw away Instagram's actual
    # explanation, so every container failure surfaced as the same
    # useless "never reached FINISHED" line. Raise with the real body.
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{GRAPH}/{container_id}", params={
            "fields": "status_code,status",
            "access_token": IG_ACCESS_TOKEN,
        }, timeout=30)
        check_response(resp, f"wait_until_ready({container_id})")
        payload = resp.json()
        status = payload.get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise RuntimeError(
                f"Container {container_id} reported ERROR: {payload.get('status')}")
        time.sleep(5)
    raise RuntimeError(
        f"Container {container_id} still not FINISHED after {timeout}s "
        "(Instagram never finished processing the media)")


# Added 2026-08-04: today's carousel 1 failed with error_subcode 2207027
# ("Media ID is not available" / "please wait for a moment") even though
# wait_until_ready() had just reported the container as FINISHED. This is
# a known Instagram Graph API race -- FINISHED doesn't always mean the
# publish endpoint is ready yet -- and Meta marks it is_transient: false
# despite the message telling you to retry shortly. Retrying a few times
# with a short delay clears it reliably instead of failing the whole post
# (and emailing a failure alert) on the first hit.
PUBLISH_NOT_READY_SUBCODE = 2207027
PUBLISH_RETRY_ATTEMPTS = 4
PUBLISH_RETRY_DELAY_SECONDS = 15


def publish(container_id):
    last_resp = None
    for attempt in range(1, PUBLISH_RETRY_ATTEMPTS + 1):
        resp = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media_publish", data={
            "creation_id": container_id,
            "access_token": IG_ACCESS_TOKEN,
        }, timeout=60)
        if resp.ok:
            return resp.json()
        last_resp = resp
        try:
            error_subcode = resp.json().get("error", {}).get("error_subcode")
        except ValueError:
            error_subcode = None
        if error_subcode == PUBLISH_NOT_READY_SUBCODE and attempt < PUBLISH_RETRY_ATTEMPTS:
            print(
                f"publish({container_id}) attempt {attempt}/{PUBLISH_RETRY_ATTEMPTS}: "
                f"Instagram says the media isn't ready yet, retrying in "
                f"{PUBLISH_RETRY_DELAY_SECONDS}s..."
            )
            time.sleep(PUBLISH_RETRY_DELAY_SECONDS)
            continue
        break
    check_response(last_resp, f"publish({container_id})")
    return last_resp.json()


def send_failure_alert(carousel_index, error_text):
    msg = EmailMessage()
    msg["Subject"] = f"Instagram auto-post FAILED — carousel {carousel_index}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"Carousel {carousel_index} failed to post to Instagram today.\n\n"
        f"Error:\n{error_text}\n\n"
        "The images are still in your email attachment from today's batch "
        "if you want to post it manually instead."
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def send_stale_manifest_alert(found_date, expected_date):
    msg = EmailMessage()
    msg["Subject"] = "Instagram auto-post SKIPPED — today's carousels weren't found"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    if found_date:
        detail = (
            f"A scheduled Instagram post was skipped because today's manifest is "
            f"dated {found_date!r}, not today ({expected_date})."
        )
    else:
        detail = (
            f"A scheduled Instagram post was skipped because no manifest exists yet "
            f"for today ({expected_date})."
        )
    msg.set_content(
        f"{detail}\n\n"
        "This almost always means today's morning generation run didn't complete — "
        "check the Actions tab for a failed 'Daily Carousels' run. Nothing was "
        "re-posted from a previous day."
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


def post_carousel(carousel, posted_log, batch_date):
    child_ids = []
    for path in carousel["image_paths"]:
        rel = path.replace(os.sep, "/")
        url = public_url(rel)
        child_ids.append(create_child_container(url))

    container_id = create_carousel_container(child_ids, carousel.get("caption", ""))

    wait_until_ready(container_id)

    result = publish(container_id)
    media_id = result.get("id")
    print(f"Posted carousel {carousel['index']} -> media id {media_id}")

    posted_log["posts"].append({
        "media_id": media_id,
        "date": batch_date,
        "index": carousel["index"],
        "niche": carousel.get("niche", ""),
        "angle": carousel.get("angle", ""),
        "format": carousel.get("format", ""),
        "hook": carousel.get("hook", ""),
        "scored": False,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="Path to a specific manifest.json (defaults to today's/most recent)")
    parser.add_argument(
        "--only-index", type=int,
        help="Manual override: force-post this specific carousel index (e.g. 1, 2, or 3), "
             "ignoring the normal target-count selection. Mainly for manual testing.",
    )
    parser.add_argument(
        "--target-count", type=int, default=None,
        help="This workflow's slot target: by the end of this run, this many of "
             "today's winning carousels should be posted IN TOTAL. daily.yml passes "
             "1, posts_later.yml passes 2, evening-post.yml passes 3. Each slot is "
             "now a single fixed-GMT cron trigger (7:30am/1pm/7pm), not a dual "
             "BST/GMT pair, but --target-count is kept regardless: it's still what "
             "makes a manual re-run or a GitHub-side retry of the same slot safe --"
             "the second firing sees the target already met and does nothing, "
             "rather than posting a second, different carousel.",
    )
    args = parser.parse_args()

    if os.environ.get("IG_POSTING_PAUSED", "false").lower() == "true":
        print("IG_POSTING_PAUSED is set to true — skipping Instagram posting entirely.")
        return

    if args.manifest:
        manifest_path = args.manifest
    else:
        # Pick TODAY's manifest by path, not "the alphabetically-last
        # manifest on disk" (glob.glob(...)[-1]). Once Batch Generate Week
        # started pre-generating several days of manifests in advance, the
        # old glob-based pick silently grabbed the FUTURE-most manifest
        # (e.g. posts/2026-08-12) instead of today's, which then always
        # failed the batch_date-vs-today check below and caused every
        # scheduled post to silently no-op. Building the path directly
        # from today's date removes that failure mode entirely.
        today_str = datetime.date.today().isoformat()
        manifest_path = f"posts/{today_str}/manifest.json"
        if not os.path.exists(manifest_path):
            print(
                f"No manifest found for today ({today_str}) — today's generation "
                "likely hasn't run yet. Skipping rather than posting a different day's content."
            )
            send_stale_manifest_alert(None, today_str)
            return

    with open(manifest_path) as f:
        manifest = json.load(f)

    if not args.manifest:
        today_str = datetime.date.today().isoformat()
        if manifest.get("batch_date") != today_str:
            print(
                f"Manifest at {manifest_path!r} is dated {manifest.get('batch_date')!r}, "
                f"not today ({today_str}) — today's generation likely didn't run. "
                "Skipping rather than re-posting stale content."
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
    elif args.target_count is not None:
        already_posted_count = len(already_posted_indices)
        need = max(0, args.target_count - already_posted_count)
        remaining = [c for c in winners if c["index"] not in already_posted_indices]
        to_post = remaining[:need]
    else:
        remaining = [c for c in winners if c["index"] not in already_posted_indices]
        to_post = remaining[:1]

    if not to_post:
        print("Nothing new to post right now — either today's winning carousels are "
              "already posted, or none are marked post_to_instagram yet.")
        return

    print(f"Posting {len(to_post)} carousel(s) to Instagram...")

    failures = []
    for i, carousel in enumerate(to_post):
        try:
            post_carousel(carousel, posted_log, batch_date)
            # Flush immediately. This used to happen once, after the whole
            # loop -- so a crash or a step timeout mid-loop lost the record
            # of posts that HAD succeeded, and the next */15 tick reposted
            # them. Writing per-post closes that window.
            save_posted_log(posted_log)
        except Exception as e:
            print(f"FAILED to post carousel {carousel['index']}: {e}")
            failures.append((carousel["index"], str(e)))
            try:
                send_failure_alert(carousel["index"], str(e))
            except Exception as mail_err:
                print(f"Could not send failure alert email: {mail_err}")
        if i < len(to_post) - 1:
            time.sleep(SECONDS_BETWEEN_POSTS)

    save_posted_log(posted_log)

    # Exit non-zero so the Actions run goes red. Swallowing the exception
    # meant a day where nothing posted looked identical to a day that
    # worked.
    if failures:
        raise SystemExit(f"{len(failures)} carousel(s) failed to post: {failures}")


if __name__ == "__main__":
    main()
