"""
Daily runner: calls the free Gemini API for 3 carousel scripts, renders
them into images using carousel_engine.py, and emails them to you.

Runs inside GitHub Actions on a schedule — see .github/workflows/daily.yml
"""

import os
import json
import smtplib
import requests
from email.message import EmailMessage
from carousel_engine import render_carousel

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

with open("content_brain_system_prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read()


def call_gemini():
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": "Generate today's batch."}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    resp = requests.post(GEMINI_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


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
    batch = call_gemini()
    batch_date = batch.get("batch_date", "today")
    all_images = []
    for i, carousel in enumerate(batch["carousels"], start=1):
        out_dir = f"/tmp/carousel_{i}"
        images = render_carousel(carousel, batch_date, out_dir)
        all_images.extend(images)
    send_email(all_images, batch_date)
    print(f"Sent {len(all_images)} images across {len(batch['carousels'])} carousels.")


if __name__ == "__main__":
    main()

