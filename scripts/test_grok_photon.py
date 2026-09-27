#!/usr/bin/env python3
"""Send one grounded briefing for a surfaced CV event through Photon.

Does not decide that a collision occurred. Does not change priority or routing.

    python3 scripts/test_grok_photon.py --camera CAM-001
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

from briefing.service import create_briefing  # noqa: E402
from cv.analyze_motion import OUTPUT_PATH as MOTION_PATH  # noqa: E402
from cv.detect_collisions import TRACKS_PATH, analyze_camera, box_index, load_json  # noqa: E402
from cv.notifyc_event import event_from_cv, events_to_send  # noqa: E402

DELIVER = REPO / "deepspace" / "src" / "integrations" / "photon" / "deliver-text.ts"
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
        raise SystemExit(
            f"Missing stored CV results for {camera_id}. "
            "Run the existing tracking and motion steps first."
        )
    analysis = analyze_camera(camera_id, motion["cameras"][camera_id], box_index(tracks))
    found = events_to_send(analysis)
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
    raw = (completed.stdout or "").strip().splitlines()
    if not raw:
        return {"ok": False, "error": (completed.stderr or "Photon delivery produced no result.").strip()}
    try:
        return json.loads(raw[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": raw[-1]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Brief one surfaced CV event with Grok and send it by Photon.")
    parser.add_argument("--camera", required=True, choices=CAMERAS)
    args = parser.parse_args(argv)
    print(f"[NotifYC] Processing {args.camera}")
    event = surfaced_event(args.camera)
    if event is None:
        print("No incident surfaced.")
        print("No Grok call made.")
        print("No Photon message sent.")
        return 0

    print("Incident surfaced.")
    load_dev_vars()
    print("Requesting grounded Grok briefing...")
    briefing = create_briefing(event)
    source = briefing.get("source")
    print(f"Grok source: {source}")
    if source == "fallback":
        print("LIVE GROK CALL FAILED")
        print("FALLBACK USED")
    elif source != "grok":
        print("Briefing validation: FAILED")
        print("No Photon message sent.")
        return 1
    else:
        print("Briefing validation: PASSED")

    payload = {
        "cameraId": event.get("cameraId"),
        "priority": event.get("priority") or "",
        "responder": event.get("assignedResponderId") or event.get("responder") or "",
        "briefing": briefing,
    }
    print("Sending through Photon...")
    result = deliver_once(payload)
    if result.get("text"):
        print("--- message ---")
        print(result["text"])
        print("---")
    if not result.get("ok"):
        print(f"Photon delivery: FAILED")
        print(result.get("error", "Photon did not report a send."))
        return 1
    print("Photon delivery: SENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
