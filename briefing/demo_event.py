"""TEST / DEMO record for exercising the briefing without the CV pipeline."""

from __future__ import annotations

DEMO_LABEL = "TEST / DEMO EVENT"


def demo_event(camera_id: str = "CAM-004") -> dict[str, object]:
    """A labeled test record. It is not a camera detection."""
    return {
        "label": DEMO_LABEL,
        "cameraId": camera_id,
        "location": "Demo placement, not a live camera",
        "eventTimestamp": "demo-clock",
        "detectionType": "possible_vehicle_collision",
        "operationalPriority": "normal",
        "involvedTracks": ["demo-1", "demo-2"],
        "observableMetrics": {},
        "evidence": {"status": "unavailable"},
        "detectionProvenance": "TEST / DEMO EVENT. Not produced by the CV pipeline.",
    }
