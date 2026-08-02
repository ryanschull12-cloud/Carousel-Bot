"""
post_linkedin.py

Posts a single image + caption to a LinkedIn Company Page using the
Community Management API (Posts API + Images API).

Auth model: refresh-token flow. LinkedIn access tokens expire after 60
days; refresh tokens last 365 days. This script exchanges the refresh
token for a fresh access token on every run, so it never goes stale
between scheduled GitHub Actions runs (as long as the bot runs at least
once a year - which it will, daily).

Required environment variables (set as GitHub Actions secrets):
  LINKEDIN_CLIENT_ID
  LINKEDIN_CLIENT_SECRET
  LINKEDIN_REFRESH_TOKEN
  LINKEDIN_ORG_URN        e.g. "urn:li:organization:12345678"
  LINKEDIN_API_VERSION    optional, format YYYYMM, e.g. "202601"
"""

import os
from datetime import date

import requests

# Read lazily so importing this module never crashes when secrets are
# absent (e.g. a dry run in GitHub Actions before LinkedIn is set up).
CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("LINKEDIN_REFRESH_TOKEN", "")
ORG_URN = os.environ.get("LINKEDIN_ORG_URN", "")

# LinkedIn versions the API by month. Default to the current month if not
# pinned - but pinning via the secret/env var is more predictable long-term.
API_VERSION = os.environ.get("LINKEDIN_API_VERSION") or date.today().strftime("%Y%m")

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
IMAGES_INIT_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
POSTS_URL = "https://api.linkedin.com/rest/posts"


def refresh_access_token() -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": REFRESH_TOKEN,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def upload_image(access_token: str, image_path: str) -> str:
    """Registers + uploads an image, returns the image URN."""
    init_resp = requests.post(
        IMAGES_INIT_URL,
        headers={**_headers(access_token), "Content-Type": "application/json"},
        json={"initializeUploadRequest": {"owner": ORG_URN}},
        timeout=30,
    )
    init_resp.raise_for_status()
    value = init_resp.json()["value"]
    upload_url = value["uploadUrl"]
    image_urn = value["image"]

    with open(image_path, "rb") as f:
        put_resp = requests.put(
            upload_url,
            data=f,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=120,
        )
    put_resp.raise_for_status()
    return image_urn


def create_post(access_token: str, image_urn: str, caption: str, alt_text: str) -> str:
    body = {
        "author": ORG_URN,
        "commentary": caption,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {
            "media": {
                "id": image_urn,
                "altText": alt_text,
            }
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    resp = requests.post(
        POSTS_URL,
        headers={**_headers(access_token), "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    # LinkedIn returns the created post's URN in the x-restli-id response header.
    return resp.headers.get("x-restli-id", "")


def publish(image_path: str, caption: str, alt_text: str) -> str:
    token = refresh_access_token()
    image_urn = upload_image(token, image_path)
    post_urn = create_post(token, image_urn, caption, alt_text)
    return post_urn


if __name__ == "__main__":
    import sys
    img_path, caption_path = sys.argv[1], sys.argv[2]
    with open(caption_path, encoding="utf-8") as f:
        caption_text = f.read()
    urn = publish(img_path, caption_text, alt_text="LinkedIn post graphic")
    print(f"Published: {urn}")
