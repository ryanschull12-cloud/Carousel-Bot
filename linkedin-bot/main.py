"""
main.py

Orchestrates one full run of the LinkedIn bot:
  1. Generate the post content (Mistral)
  2. Build the graphic (Pollinations illustration + Pillow overlay)
  3. Post to LinkedIn (Community Management API)
  4. Email Ryan the result (best-effort - won't fail the run if email breaks)

Designed to be run once per scheduled GitHub Actions trigger.
"""

import json
import os
import smtplib
import traceback
from email.message import EmailMessage

from generate_copy import generate_post, build_caption
from generate_image import build_image
from post_linkedin import publish

OUTPUT_IMAGE = "linkedin_post.png"

LINKEDIN_SECRETS = ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET",
                    "LINKEDIN_REFRESH_TOKEN", "LINKEDIN_ORG_URN")


def is_dry_run() -> bool:
    """Dry run if DRY_RUN=1 is set, or if any LinkedIn secret is missing."""
    if os.environ.get("DRY_RUN") == "1":
        return True
    return not all(os.environ.get(k) for k in LINKEDIN_SECRETS)


def send_email(subject: str, body: str, image_path: str | None = None) -> None:
    """Best-effort email notification. Skips silently if SMTP secrets aren't set."""
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("EMAIL_TO", user)
    if not (host and user and password and to_addr):
        print("SMTP not configured - skipping email notification.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="image", subtype="png", filename="linkedin_post.png")

    port = int(os.environ.get("SMTP_PORT", "465"))
    try:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, password)
            server.send_message(msg)
        print("Notification email sent.")
    except Exception:
        print("Email notification failed (non-fatal):")
        traceback.print_exc()


def main() -> None:
    print("Generating post content...")
    data = generate_post()
    caption = build_caption(data)
    print(f"Topic: {data['topic']}")

    print("Building graphic...")
    image = build_image(data)
    image.save(OUTPUT_IMAGE, "PNG")

    with open("linkedin_post_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if is_dry_run():
        print("DRY RUN - LinkedIn secrets missing or DRY_RUN=1. Skipping publish.")
        send_email(
            subject=f"[LinkedIn Bot] DRY RUN: {data['topic']}",
            body=f"Dry run - nothing was posted.\n\n--- Caption ---\n{caption}",
            image_path=OUTPUT_IMAGE,
        )
        return

    try:
        print("Publishing to LinkedIn...")
        post_urn = publish(OUTPUT_IMAGE, caption, alt_text=data["subtitle"])
        print(f"Published: {post_urn}")
        send_email(
            subject=f"[LinkedIn Bot] Posted: {data['topic']}",
            body=f"Published successfully.\nPost URN: {post_urn}\n\n--- Caption ---\n{caption}",
            image_path=OUTPUT_IMAGE,
        )
    except Exception as e:
        print("Publishing to LinkedIn FAILED:")
        traceback.print_exc()
        send_email(
            subject=f"[LinkedIn Bot] FAILED: {data['topic']}",
            body=f"Publishing failed: {e}\n\n--- Caption that was generated ---\n{caption}",
            image_path=OUTPUT_IMAGE,
        )
        raise


if __name__ == "__main__":
    main()
