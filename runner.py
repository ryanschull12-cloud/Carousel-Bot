"""
Daily runner: calls the free Mistral API for 3 carousel scripts, renders
them into images using carousel_engine.py, and emails them to you.

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
        "Save them to your camera roll and post."
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
    all_images = []
    for i, carousel in enumerate(batch["carousels"], start=1):
        out_dir = f"/tmp/carousel_{i}"
        images = render_carousel(carousel, batch_date, out_dir, carousel_index=i - 1)
        all_images.extend(images)
    send_email(all_images, batch_date)
    print(f"Sent {len(all_images)} images across {len(batch['carousels'])} carousels.")


if __name__ == "__main__":
    main()
