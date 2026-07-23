"""
Publishes carousels marked post_to_instagram=true in today's manifest
to Instagram, using images already committed and pushed to the repo
(so they're reachable at a public raw.githubusercontent.com URL).

Now runs up to THREE times a day at different scheduled times, fully
automatic — nothing in this script can hold a post back. See
.github/workflows/daily.yml for the ~8:30am slot, which posts carousel 1
right after generation, and .github/workflows/posts_later.yml for the
~1pm/~6pm slots, which post carousels 2 and 3 from that same morning's
already-committed manifest. Each run is invoked with --only-index N so
this script only ever handles one carousel per run.

PERFORMANCE LOGGING (new): every carousel that actually gets published now
gets appended to posted_log.json with its media_id, date, niche, angle,
format, and hook. fetch_performance.py reads this file a few days later to
pull real Instagram engagement numbers and tie them back to what was
actually written, and the weekly self-review email (performance_report.py)
reads it too. This is the "review itself" half of the pipeline — it's all
retrospective (informs what gets written next, and what you see in the
weekly report), never a gate on whether something posts.
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
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{GRAPH}/{container_id}", params={
            "fields": "status_code",
            "access_token": IG_ACCESS_TOKEN,
        }, timeout=30)
        check_response(resp, f"wait_until_ready({container_id})")
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            return False
        time.sleep(5)
    return False


def publish(container_id):
    resp = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media_publish", data={
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN,
    }, timeout=60)
    check_response(resp, f"publish({container_id})")
    return resp.json()


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

    if not wait_until_ready(container_id):
        raise RuntimeError(f"Container {container_id} never reached FINISHED status")

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
    parser.add_argument("--only-index", type=int, help="Only post the carousel with this index (e.g. 1, 2, or 3)")
    args = parser.parse_args()

    # Defense in depth: the workflows already skip this whole script when
    # the IG_POSTING_PAUSED repo variable is "true", but this check means a
    # manual run (or a workflow edited without noticing the guard) still
    # can't post while you're paused for Meta verification.
    if os.environ.get("IG_POSTING_PAUSED", "false").lower() == "true":
        print("IG_POSTING_PAUSED is set to true — skipping Instagram posting entirely.")
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

    print(f"Posting {len(to_post)} carousel(s) to Instagram...")

    posted_log = load_posted_log()
    batch_date = manifest.get("batch_date", "")

    for i, carousel in enumerate(to_post):
        try:
            post_carousel(carousel, posted_log, batch_date)
        except Exception as e:
            print(f"FAILED to post carousel {carousel['index']}: {e}")
            send_failure_alert(carousel["index"], str(e))
        if i < len(to_post) - 1:
            time.sleep(SECONDS_BETWEEN_POSTS)

    # Save whatever succeeded even if a later carousel in the loop failed.
    save_posted_log(posted_log)


if __name__ == "__main__":
    main()
