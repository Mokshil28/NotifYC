"""Canonical event at the boundary between the CV result and DeepSpace.

This module does not score collisions. It only copies a result the existing
state machine has already surfaced.
"""

import hashlib
import json
import math
from pathlib import Path

SCHEMA_VERSION = 1
DETECTION_TYPE = "possible_vehicle_collision"
CAMERAS = {f"CAM-{index:03d}" for index in range(1, 11)}
REPO = Path(__file__).resolve().parent.parent


def event_id(camera_id: str, surfaced_s: float, track_ids: list[str], score: int) -> str:
    raw = f"{camera_id}|{surfaced_s:.3f}|{','.join(sorted(track_ids))}|{score}"
    return "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def observable_metrics(cv_event: dict) -> dict:
    """Copy scalar diagnostics already computed by the collision state machine."""
    score = cv_event.get("collisionEvidenceScore")
    metrics = {"collisionEvidenceScore": int(score) if _finite(score) else 0}
    diagnostics = cv_event.get("candidateDiagnostics")
    if not isinstance(diagnostics, dict):
        return metrics
    for key, value in diagnostics.items():
        if key == "candidate_metrics":
            continue
        if isinstance(value, bool) or value is None or _finite(value):
            metrics[key] = value
    return metrics


def evidence_for(camera_id: str, window_start: float, window_end: float) -> dict:
    clip_name = camera_id.replace("CAM-", "cam_")
    tracked = REPO / "outputs" / "tracking" / f"{clip_name}_tracked.mp4"
    source = REPO / "data" / "cameras" / f"{clip_name}.mp4"
    chosen = tracked if tracked.is_file() else source if source.is_file() else None
    if chosen is None:
        return {"status": "unavailable", "clipRef": "", "windowStart": window_start, "windowEnd": window_end}
    return {
        "status": "reference",
        "clipRef": str(chosen.relative_to(REPO)),
        "windowStart": window_start,
        "windowEnd": window_end,
    }


def event_from_cv(cv_event: dict) -> dict:
    if not cv_event.get("collisionDetected"):
        raise ValueError("CV did not surface an incident.")
    camera_id = str(cv_event.get("camera_id", ""))
    tracks = [str(track_id) for track_id in cv_event.get("participant_track_ids") or []]
    surfaced = cv_event.get("surfaced_at")
    if not _finite(surfaced):
        raise ValueError("Surfaced event has no timestamp.")
    start = cv_event.get("closest_interaction_time")
    window_start = float(start) if _finite(start) else float(surfaced)
    window_end = float(surfaced)
    if window_end < window_start:
        window_start = window_end
    score = int(cv_event.get("collisionEvidenceScore") or 0)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventId": event_id(camera_id, window_end, tracks, score),
        "cameraId": camera_id,
        "eventTimestamp": window_end,
        "detectionType": DETECTION_TYPE,
        "priority": "normal",
        "involvedTracks": tracks,
        "observableMetrics": observable_metrics(cv_event),
        "evidence": evidence_for(camera_id, window_start, window_end),
        "detectionMode": "computer-vision",
        "provenance": {
            "pipeline": "cv/detect_collisions.py",
            "label": "Surfaced by the existing collision state machine",
        },
    }


def validate_event(event: dict) -> list[str]:
    errors = []
    if event.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"Unsupported schema version. Expected {SCHEMA_VERSION}.")
    event_key = event.get("eventId")
    if not isinstance(event_key, str) or len(event_key) < 12 or not event_key.startswith("evt-"):
        errors.append("eventId is missing or malformed.")
    if event.get("cameraId") not in CAMERAS:
        errors.append("cameraId must be one of CAM-001 through CAM-010.")
    if event.get("detectionType") != DETECTION_TYPE:
        errors.append("detectionType must be possible_vehicle_collision.")
    timestamp = event.get("eventTimestamp")
    if not _finite(timestamp) or timestamp < 0:
        errors.append("eventTimestamp must be a non-negative number of clip seconds.")
    tracks = event.get("involvedTracks")
    if not isinstance(tracks, list) or any(not isinstance(track, str) or not track.isdigit() for track in tracks):
        errors.append("involvedTracks must be numeric track id strings.")
    evidence = event.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence is required.")
    else:
        if evidence.get("status") not in {"unavailable", "reference"}:
            errors.append("evidence.status must be unavailable or reference.")
        start, end = evidence.get("windowStart"), evidence.get("windowEnd")
        if not _finite(start) or not _finite(end) or end < start:
            errors.append("Evidence window is invalid.")
    if event.get("detectionMode") != "computer-vision":
        errors.append("A CV runner event must use detectionMode computer-vision.")
    return errors


def events_to_send(analysis: dict) -> list[dict]:
    """Nothing is sent unless the existing state machine marked the row detected."""
    found = []
    for item in analysis.get("events") or []:
        if item.get("collisionDetected"):
            found.append(item)
    return found


def dump_event(event: dict) -> str:
    return json.dumps(event, indent=2, sort_keys=True)
