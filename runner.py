"""
Daily runner: calls the free Mistral API for 5 carousel scripts, renders
them into images using carousel_engine.py, saves them into the repo
(so they get public URLs for Instagram posting), writes a manifest for
the Instagram posting step, and emails all 5 carousels to you.

Runs inside GitHub Actions on a schedule — see .github/workflows/daily.yml
"""

import os
import json
import time
import smtplib
import requests
from email.message import EmailMessage
from carousel_engine import render_carousel

MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

# How many of the day's carousels get auto-posted to Instagram.
# The rest are still generated and emailed, just not auto-posted.
AUTO_POST_COUNT = 2

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

with open("content_brain_system_prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read()


def call_mistral():
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
    }
    body = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Generate today's batch."},
        ],
        "response_format": {"type": "json_object"},
    }
    last_error = None
    for attempt in range(5):
        resp = requests.post(MISTRAL_URL, headers=headers, json=body, timeout=60)
        if resp.status_code in (503, 429, 500):
            last_error = resp
            wait = min(60, 2 ** attempt) + 1
            print(f"Mistral returned {resp.status_code}, retrying in {wait}s (attempt {attempt + 1}/5)...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)
    last_error.raise_for_status()


def send_email(image_paths, batch_date):
    msg = EmailMessage()
    msg["Subject"] = f"Your carousels for {batch_date}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"Today's batch of {len(image_paths)} slide images is attached.\n"
        f"The first {AUTO_POST_COUNT} carousels are also being auto-posted to Instagram.\n"
        "Save the rest to your camera roll for TikTok / manual posting."
    )
    for path in image_paths:
        with open(path, "rb") as f:
            msg.add_attachment(
                f.read(), maintype="image", subtype="png",
                filename=os.path.basename(os.path.dirname(path)) + "_" + os.path.basename(path),
            )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def main():
    batch = call_mistral()
    batch_date = batch.get("batch_date", "today")

    # Images go into ./posts/{date}/carousel_{n}/ — inside the repo working
    # directory (not /tmp) so they can be committed and get public raw URLs
    # for the Instagram posting step.
    base_dir = os.path.join("posts", batch_date)
    all_images = []
    manifest = {"batch_date": batch_date, "carousels": []}

    for i, carousel in enumerate(batch["carousels"], start=1):
        out_dir = os.path.join(base_dir, f"carousel_{i}")
        images = render_carousel(carousel, batch_date, out_dir, carousel_index=i - 1)
        all_images.extend(images)
        manifest["carousels"].append({
            "index": i,
            "caption": carousel.get("caption", ""),
            "niche": carousel.get("niche", ""),
            "image_paths": images,
            "post_to_instagram": i <= AUTO_POST_COUNT,
        })

    with open(os.path.join(base_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    send_email(all_images, batch_date)
    print(f"Generated {len(all_images)} images across {len(batch['carousels'])} carousels.")
    print(f"Manifest written to {base_dir}/manifest.json")


if __name__ == "__main__":
    main()
