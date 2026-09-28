"""Automatic P1 notification for the demo.

CAM-001 is always first because the tracked car flips. This builds the
briefing, speaks it with ElevenLabs, and sends audio plus text through the
already open Photon conversation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from briefing.dispatch import briefing_is_sendable, concise_dispatch  # noqa: E402
from briefing.elevenlabs import ElevenLabsError, generate_voice_briefing  # noqa: E402
from briefing.service import create_briefing  # noqa: E402

DELIVER = REPO / "deepspace" / "src" / "integrations" / "photon" / "deliver-notification.ts"
VIDEO = REPO / "frontend" / "public" / "cv" / "CAM-001.mp4"


def load_dev_vars() -> None:
    import os

    path = REPO / "deepspace" / ".dev.vars"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, value = trimmed.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def p1_event() -> dict:
    return {
        "schemaVersion": 1,
        "eventId": "evt-cv-cam-001",
        "cameraId": "CAM-001",
        "eventTimestamp": 2.836,
        "detectionType": "possible_vehicle_collision",
        "priority": "high",
        "involvedTracks": ["20", "1"],
        "observableMetrics": {
            "collisionEvidenceScore": 84,
            "vehicle_rollover": True,
            "abrupt_geometry_change": True,
        },
        "evidence": {
            "status": "reference",
            "clipRef": str(VIDEO),
            "windowStart": 2.4,
            "windowEnd": 2.836,
        },
        "detectionMode": "computer-vision",
        "provenance": {
            "pipeline": "cv/detect_collisions.py",
            "label": "Frame 85 tracked car flips over at Times Square",
        },
        "locationName": "Times Square",
        "assignedResponderId": "UNIT-12",
    }


def deliver(payload: dict) -> dict:
    completed = subprocess.run(
        ["node", "--experimental-strip-types", str(DELIVER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO / "deepspace"),
        check=False,
    )
    for line in reversed((completed.stdout or "").splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"ok": False, "error": (completed.stderr or completed.stdout or "Photon returned no result.").strip()}


def main() -> int:
    load_dev_vars()
    event = p1_event()
    briefing = create_briefing(event)
    if not briefing_is_sendable(briefing):
        print(json.dumps({"ok": False, "detail": "Briefing was not sendable."}))
        return 1
    summary = str(briefing.get("summary") or "A tracked car flips over and needs attention first.")
    text = concise_dispatch("CAM-001", summary, "P1 — High", "UNIT-12")
    audio = ""
    try:
        audio = str(generate_voice_briefing(text))
    except ElevenLabsError as exc:
        print(json.dumps({"ok": False, "detail": str(exc)}))
        return 1
    result = deliver({"text": text, "audioPath": audio, "videoPath": str(VIDEO) if VIDEO.is_file() else ""})
    sent = result.get("ok") is True and (result.get("result") or {}).get("text") == "SENT"
    print(json.dumps({
        "ok": sent,
        "detail": "P1 voice briefing sent." if sent else result.get("error") or "Photon did not send the P1 briefing.",
        "audio": bool(audio),
        "source": briefing.get("source"),
    }))
    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
