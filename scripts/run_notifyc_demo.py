#!/usr/bin/env python3
"""Run the existing CV pipeline and, only when it surfaces an incident, send it.

Dry-run prints the event and does not contact DeepSpace.
--submit-test sends one labeled TEST / DEMO EVENT through the same local
intake. It does not read a collision result and is not a fallback.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cv.detect_collisions import TRACKS_PATH, analyze_camera, box_index, load_json  # noqa: E402
from cv.analyze_motion import OUTPUT_PATH as MOTION_PATH  # noqa: E402
from cv.notifyc_event import dump_event, event_from_cv, events_to_send, validate_event  # noqa: E402

DEFAULT_BRIDGE = "http://127.0.0.1:8780"
CAMERAS = [f"CAM-{index:03d}" for index in range(1, 11)]


def score_camera(camera_id: str) -> dict:
    tracks = load_json(TRACKS_PATH)
    motion = load_json(MOTION_PATH)
    if camera_id not in tracks or camera_id not in motion.get("cameras", {}):
        raise SystemExit(
            f"Missing stored CV results for {camera_id}. "
            "Run cv/track_objects.py and cv/analyze_motion.py for that clip first. "
            "This runner does not re-detect vehicles."
        )
    return analyze_camera(camera_id, motion["cameras"][camera_id], box_index(tracks))


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() or exc.reason
        try:
            body = json.loads(detail)
        except json.JSONDecodeError:
            body = {"success": False, "error": detail}
        print(f"[Bridge] DeepSpace refused the event ({exc.code}): {body.get('error', detail)}")
        return body
    except urllib.error.URLError as exc:
        print(f"[Bridge] DeepSpace is unavailable at {url}: {exc.reason}")
        print("[Bridge] Start the app with: cd NotifYC && npx deepspace dev start")
        print("[Bridge] If it prints a different URL, set NOTIFYC_BRIDGE_URL.")
        return {"success": False, "error": str(exc.reason)}
    return body


def report_bridge(body: dict) -> int:
    if not body.get("success"):
        print(f"[DeepSpace] Incident was not created: {body.get('error', 'unknown error')}")
        return 1
    data = body.get("data") or {}
    if data.get("duplicate"):
        print(f"[DeepSpace] Already ingested. Incident: {data.get('incidentId')}")
    else:
        print(f"[DeepSpace] Incident created: {data.get('incidentId')}")
    if data.get("routing") == "assigned":
        print(f"[Routing] Assigned simulated responder: {data.get('assignedResponderId')}")
    else:
        print(f"[Routing] No assignment. {data.get('routingDetail', 'Incident remains open.')}")
    print("[NotifYC] Complete")
    return 0


def process_camera(camera_id: str, dry_run: bool, bridge: str) -> int:
    print(f"[NotifYC] Processing {camera_id}")
    analysis = score_camera(camera_id)
    surfaced = events_to_send(analysis)
    if not surfaced:
        print("[CV] No surfaced incident")
        return 0
    status = 0
    for cv_event in surfaced:
        try:
            event = event_from_cv(cv_event)
        except ValueError as exc:
            print(f"[CV] Surfaced row could not be converted: {exc}")
            status = 1
            continue
        errors = validate_event(event)
        if errors:
            print("[Bridge] Event rejected locally:")
            for error in errors:
                print(f"[Bridge] {error}")
            status = 1
            continue
        print("[CV] Possible collision surfaced")
        print(f"[CV] Event ID: {event['eventId']}")
        if dry_run:
            print("[Bridge] Dry run. Not sent.")
            print(dump_event(event))
            continue
        print("[Bridge] Event validated")
        body = post_json(f"{bridge.rstrip('/')}/api/local/cv-events", event)
        status = max(status, report_bridge(body))
    return status


def submit_test(camera_id: str, bridge: str) -> int:
    print(f"[NotifYC] TEST / DEMO EVENT for {camera_id}")
    print("[CV] Not used. This is not a collision detection.")
    body = post_json(f"{bridge.rstrip('/')}/api/local/cv-events/test", {"cameraId": camera_id})
    return report_bridge(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send surfaced NotifYC CV events to the local DeepSpace demo.")
    parser.add_argument("--camera", choices=CAMERAS)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit-test", action="store_true", help="Send one labeled TEST / DEMO EVENT. Does not run CV.")
    parser.add_argument("--bridge", default="")
    args = parser.parse_args()
    bridge = args.bridge or __import__("os").environ.get("NOTIFYC_BRIDGE_URL", DEFAULT_BRIDGE)

    if args.submit_test and (args.all or args.dry_run):
        raise SystemExit("--submit-test cannot be combined with --all or --dry-run.")
    if args.submit_test:
        raise SystemExit(submit_test(args.camera or "CAM-001", bridge))
    cameras = CAMERAS if args.all else [args.camera] if args.camera else []
    if not cameras:
        raise SystemExit("Choose --camera CAM-00N, --all, or --submit-test.")
    status = 0
    for camera_id in cameras:
        status = max(status, process_camera(camera_id, args.dry_run, bridge))
    raise SystemExit(status)


if __name__ == "__main__":
    main()
