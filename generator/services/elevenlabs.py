"""Thin client for the ElevenLabs voice-cloning + text-to-speech API.

Docs: https://elevenlabs.io/docs/api-reference
"""

import json

import requests
from django.conf import settings

BASE_URL = "https://api.elevenlabs.io/v1"
TIMEOUT = 120


class ElevenLabsError(RuntimeError):
    pass


def _headers(accept=None):
    if not settings.ELEVENLABS_API_KEY:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")
    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    if accept:
        headers["Accept"] = accept
    return headers


def clone_voice(name, sample_bytes, filename="sample.mp3", language="", accent=""):
    """Create an instant voice clone from audio sample bytes. Returns voice_id."""
    files = [("files", (filename, sample_bytes, "application/octet-stream"))]
    data = {"name": name}
    labels = {}
    if language:
        labels["language"] = language
    if accent:
        labels["accent"] = accent
    if labels:
        data["labels"] = json.dumps(labels)
    resp = requests.post(
        f"{BASE_URL}/voices/add",
        headers=_headers(),
        data=data,
        files=files,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise ElevenLabsError(f"voice clone failed ({resp.status_code}): {resp.text}")
    voice_id = resp.json().get("voice_id")
    if not voice_id:
        raise ElevenLabsError(f"voice clone returned no voice_id: {resp.text}")
    return voice_id


def list_voices(cloned_only=True):
    """List voices in the account.

    By default returns only the user's own cloned voices (category "cloned"),
    not the ElevenLabs premade library. Returns
    [{voice_id, name, category, preview_url}].
    """
    resp = requests.get(
        f"{BASE_URL}/voices",
        headers=_headers(accept="application/json"),
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise ElevenLabsError(f"list voices failed ({resp.status_code}): {resp.text}")
    voices = resp.json().get("voices", [])
    if cloned_only:
        voices = [v for v in voices if v.get("category") == "cloned"]
    return [
        {
            "voice_id": v.get("voice_id", ""),
            "name": v.get("name", ""),
            "category": v.get("category", ""),
            "preview_url": v.get("preview_url", ""),
        }
        for v in voices
    ]


def tts(voice_id, text):
    """Synthesize text into speech using the given voice. Returns audio bytes."""
    payload = {
        "text": text,
        "model_id": settings.ELEVEN_MODEL_ID,
    }
    resp = requests.post(
        f"{BASE_URL}/text-to-speech/{voice_id}",
        headers=_headers(accept="audio/mpeg"),
        params={"output_format": settings.ELEVEN_OUTPUT_FORMAT},
        json=payload,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise ElevenLabsError(f"tts failed ({resp.status_code}): {resp.text}")
    return resp.content


def delete_voice(voice_id):
    """Best-effort cleanup of a cloned voice. Never raises."""
    try:
        requests.delete(
            f"{BASE_URL}/voices/{voice_id}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        pass
