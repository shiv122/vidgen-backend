"""Thin client for the D-ID Talks API (image + audio -> talking-head video).

Docs: https://docs.d-id.com/reference/talks-overview

The D-ID API key (from the Studio) is already in base64 `user:pass` form, so it
is used directly as the `Basic` credential. Image and audio are passed as public
URLs (served from DigitalOcean Spaces), so no per-request file upload is needed.
"""

import requests
from django.conf import settings

BASE_URL = "https://api.d-id.com"
TIMEOUT = 60


class DIDError(RuntimeError):
    pass


def _headers(content_type=None):
    if not settings.DID_API_KEY:
        raise DIDError("DID_API_KEY is not configured")
    headers = {
        "Authorization": f"Basic {settings.DID_API_KEY}",
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def create_talk(source_url, audio_url, resolution):
    """Kick off a talking-head video render. Returns the talk id."""
    payload = {
        "source_url": source_url,
        "script": {"type": "audio", "audio_url": audio_url},
        "config": {
            "result_format": "mp4",
            # Longest output dimension in px (e.g. 480 for 480p).
            "output_resolution": resolution,
        },
    }
    resp = requests.post(
        f"{BASE_URL}/talks",
        headers=_headers(content_type="application/json"),
        json=payload,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise DIDError(f"create talk failed ({resp.status_code}): {resp.text}")
    talk_id = resp.json().get("id")
    if not talk_id:
        raise DIDError(f"create talk returned no id: {resp.text}")
    return talk_id


def get_talk(talk_id):
    """Fetch a talk's current state. Returns {status, result_url, error}."""
    resp = requests.get(
        f"{BASE_URL}/talks/{talk_id}",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise DIDError(f"get talk failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    return {
        "status": data.get("status"),
        "result_url": data.get("result_url", ""),
        "error": data.get("error") or data.get("result", {}).get("error"),
    }
