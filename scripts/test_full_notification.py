#!/usr/bin/env python3
"""One surfaced event: Grok briefing, ElevenLabs speech, Photon audio, text, video.

    python3 scripts/test_full_notification.py --camera CAM-001
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from briefing.dispatch import briefing_is_sendable, concise_dispatch, evidence_clip  # noqa: E402
from briefing.elevenlabs import ElevenLabsError, generate_voice_briefing  # noqa: E402
from briefing.service import create_briefing  # noqa: E402
from cv.analyze_motion import OUTPUT_PATH as MOTION_PATH  # noqa: E402
from cv.detect_collisions import TRACKS_PATH, analyze_camera, box_index, load_json  # noqa: E402
from cv.notifyc_event import event_from_cv, events_to_send  # noqa: E402

DELIVER = REPO / "deepspace" / "src" / "integrations" / "photon" / "deliver-notification.ts"
DEV_VARS = REPO / "deepspace" / ".dev.vars"
CAMERAS = [f"CAM-{index:03d}" for index in range(1, 11)]


def load_dev_vars() -> None:
    import os

    if not DEV_VARS.is_file():
        return
    for line in DEV_VARS.read_text().splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, value = trimmed.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def surfaced_event(camera_id: str) -> dict | None:
    tracks = load_json(TRACKS_PATH)
    motion = load_json(MOTION_PATH)
    if camera_id not in tracks or camera_id not in motion.get("cameras", {}):
        raise SystemExit(f"Missing stored CV results for {camera_id}.")
    found = events_to_send(analyze_camera(camera_id, motion["cameras"][camera_id], box_index(tracks)))
    if not found:
        return None
    return event_from_cv(found[0])


def deliver_once(payload: dict) -> dict:
    completed = subprocess.run(
        ["node", "--experimental-strip-types", str(DELIVER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO / "deepspace"),
        check=False,
    )
    lines = (completed.stdout or "").strip().splitlines()
    if not lines:
        error = (completed.stderr or "Photon produced no result.").strip()
        return {"ok": False, "error": error, "result": {}}
    for line in reversed(lines):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and ("result" in parsed or "ok" in parsed or "error" in parsed):
            return parsed
    error = (completed.stderr or lines[-1]).strip()
    return {"ok": False, "error": error, "result": {}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grok briefing, speech, and Photon delivery for one camera.")
    parser.add_argument("--camera", required=True, choices=CAMERAS)
    args = parser.parse_args(argv)
    print("========================================")
    print("NOTIFYC FULL NOTIFICATION TEST")
    print("========================================")
    print(f"Camera: {args.camera}")
    event = surfaced_event(args.camera)
    if event is None:
        print("\nCV:\nIncident surfaced: NO")
        print("No incident surfaced.")
        print("No notification generated.")
        print("========================================\nEND\n========================================")
        return 0

    print("\nCV:\nIncident surfaced: YES")
    load_dev_vars()
    import os
    os.environ.setdefault("XAI_TIMEOUT_SECONDS", "90")
    briefing = create_briefing(event)
    source = briefing.get("source")
    print("\nGrok:")
    if source == "grok":
        print("Live call: SUCCESS")
        print("Source: grok")
        print("Validation: PASSED")
    elif source == "fallback":
        print("Live call: FAILED")
        print("Source: fallback")
        print("FALLBACK USED")
    else:
        print("Validation: FAILED")
        print("No notification generated.")
        return 1
    if not briefing_is_sendable(briefing):
        print("Validation: FAILED")
        print("No notification generated.")
        return 1

    priority = event.get("priority") if isinstance(event.get("priority"), str) else ""
    responder = event.get("assignedResponderId") or event.get("responder") or ""
    dispatch = concise_dispatch(str(event.get("cameraId")), str(briefing.get("summary")), priority, str(responder or ""))
    print("\nDispatch:")
    print(f'"{dispatch}"')

    audio_path = None
    audio_status = "FAILED"
    print("\nElevenLabs:")
    try:
        audio_path = generate_voice_briefing(dispatch)
        audio_status = "SUCCESS"
        print("TTS: SUCCESS")
        print(f"Audio generated: {audio_path}")
        print(f"Audio size: {audio_path.stat().st_size}")
    except ElevenLabsError as exc:
        print("TTS: FAILED")
        print(exc)
        print("Continuing with text/video delivery.")

    video = evidence_clip(str(event.get("cameraId")), REPO)
    print("\nPhoton:")
    if not video:
        print("Evidence video: missing for this camera")
    delivery = deliver_once(
        {
            "text": dispatch,
            "audioPath": str(audio_path) if audio_path else "",
            "videoPath": video or "",
        }
    )
    result = delivery.get("result") or {}
    errors = delivery.get("errors") or {}
    print("\nDelivery:")
    audio_delivery = result.get("audio", "FAILED")
    if audio_status == "FAILED":
        audio_delivery = "FAILED"
    print(f"Audio: {audio_delivery}")
    print(f"Text: {result.get('text', 'FAILED')}")
    print(f"Video: {result.get('video', 'FAILED')}")
    for name, message in errors.items():
        print(f"{name} error: {message}")
    if delivery.get("error"):
        print(f"Photon error: {delivery.get('error')}")
    print("========================================\nEND\n========================================")
    failed = audio_status == "FAILED" or any(result.get(part) == "FAILED" for part in ("text", "video")) or not result
    return 1 if failed or not result else 0


if __name__ == "__main__":
    raise SystemExit(main())
