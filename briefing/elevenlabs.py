"""Turn validated briefing text into speech with the ElevenLabs HTTP API.

Uses a public premade voice. Does not clone a voice.
"""

from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
# Premade ElevenLabs voice "Rachel". Not a cloned voice.
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
MODEL_ID = "eleven_multilingual_v2"


class ElevenLabsError(Exception):
    """Speech could not be generated."""


def _elevenlabs_message(raw: str) -> str:
    import json

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return " ".join(raw.split())[:240]
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        text = detail.get("message") or detail.get("status") or ""
        return str(text)[:240]
    if isinstance(detail, str):
        return detail[:240]
    if isinstance(payload, dict) and payload.get("message"):
        return str(payload["message"])[:240]
    return ""


def generate_voice_briefing(text: str, *, api_key: str | None = None, opener=None) -> Path:
    key = (api_key if api_key is not None else os.environ.get("ELEVENLABS_API_KEY", "")).strip()
    if not key:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not set.")
    if not text.strip():
        raise ElevenLabsError("Dispatch text is empty.")
    body = (
        '{"text": ' + _json_string(text) + ', "model_id": "' + MODEL_ID + '"}'
    ).encode()
    request = urllib.request.Request(
        f"{API_URL}/{VOICE_ID}",
        data=body,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=60) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
            if key:
                raw = raw.replace(key, "[redacted]")
            message = _elevenlabs_message(raw)
            if message:
                detail = f" {message}"
        except Exception:
            detail = ""
        raise ElevenLabsError(f"ElevenLabs request failed with HTTP {exc.code}.{detail}") from exc
    except urllib.error.URLError as exc:
        raise ElevenLabsError("ElevenLabs request could not reach the API.") from exc
    if not audio:
        raise ElevenLabsError("ElevenLabs returned empty audio.")
    handle = tempfile.NamedTemporaryFile(prefix="notifyc-briefing-", suffix=".mp3", delete=False)
    try:
        handle.write(audio)
    finally:
        handle.close()
    return Path(handle.name)


def _json_string(text: str) -> str:
    import json

    return json.dumps(text)
