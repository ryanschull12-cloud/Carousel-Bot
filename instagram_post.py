"""
Publishes carousels marked post_to_instagram=true in today's manifest
to Instagram, using images already committed and pushed to the repo
(so they're reachable at a public raw.githubusercontent.com URL).

Must run AFTER the images have been committed and pushed — see
.github/workflows/daily.yml for the ordering.
"""

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
    resp.raise_for_status()
    return resp.json()["id"]


def create_carousel_container(child_ids, caption):
    resp = requests.post(f"{GRAPH}/{IG_BUSINESS_ACCOUNT_ID}/media", data={
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }, timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]


def wait_until_ready(container_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{GRAPH}/{container_id}", params={
            "fields": "status_code",
            "access_token": IG_ACCESS_TOKEN,
        }, timeout=30)
        resp.raise_for_status()
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
    resp.raise_for_status()
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


def post_carousel(carousel):
    child_ids = []
    for path in carousel["image_paths"]:
        rel = path.replace(os.sep, "/")
        url = public_url(rel)
        child_ids.append(create_child_container(url))

    container_id = create_carousel_container(child_ids, carousel.get("caption", ""))

    if not wait_until_ready(container_id):
        raise RuntimeError(f"Container {container_id} never reached FINISHED status")

    result = publish(container_id)
    print(f"Posted carousel {carousel['index']} -> media id {result.get('id')}")


def main():
    if len(sys.argv) > 1:
        manifest_path = sys.argv[1]
    else:
        matches = sorted(glob.glob("posts/*/manifest.json"))
        if not matches:
            print("No manifest found, nothing to post.")
            return
        manifest_path = matches[-1]

    with open(manifest_path) as f:
        manifest = json.load(f)

    to_post = [c for c in manifest["carousels"] if c.get("post_to_instagram")]
    print(f"Posting {len(to_post)} carousel(s) to Instagram...")

    for i, carousel in enumerate(to_post):
        try:
            post_carousel(carousel)
        except Exception as e:
            print(f"FAILED to post carousel {carousel['index']}: {e}")
            send_failure_alert(carousel["index"], str(e))
        if i < len(to_post) - 1:
            time.sleep(SECONDS_BETWEEN_POSTS)


if __name__ == "__main__":
    main()
