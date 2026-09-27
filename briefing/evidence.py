"""Compact evidence copied from an already-surfaced incident record.

The field names match ``cv/notifyc_event.py`` when that record is present.
Missing optional fields stay missing. This module does not score collisions
and does not invent a second incident schema.
"""

from __future__ import annotations

from typing import Any

MAX_TRACKS = 8
MAX_METRICS = 12
MAX_TEXT = 160

# Detection labels the briefing is allowed to repeat. Anything else is not
# echoed, so a bad label cannot be upgraded into a collision claim.
SAFE_DETECTION_TYPES = frozenset({"possible_vehicle_collision"})

# Scalar diagnostics the CV record may already carry. Other keys are dropped
# so the model is not handed nested or named medical/fault fields.
BLOCKED_METRIC_FRAGMENTS = (
    "injury",
    "injuries",
    "fatal",
    "fault",
    "intent",
    "intox",
    "occupant",
    "passenger",
    "nypd",
    "fdny",
    "ems",
    "911",
    "medical",
    "severity",
)


class BriefingEvidence:
    def __init__(
        self,
        *,
        camera_id: str | None,
        location: str | None,
        event_timestamp: str | int | float | None,
        detection_type: str | None,
        operational_priority: str | None,
        involved_tracks: list[str],
        observable_metrics: dict[str, bool | int | float],
        evidence_status: str | None,
        evidence_window: tuple[int | float, int | float] | None,
        provenance: str | None,
        demo_label: str | None,
    ) -> None:
        self.camera_id = camera_id
        self.location = location
        self.event_timestamp = event_timestamp
        self.detection_type = detection_type
        self.operational_priority = operational_priority
        self.involved_tracks = involved_tracks
        self.observable_metrics = observable_metrics
        self.evidence_status = evidence_status
        self.evidence_window = evidence_window
        self.provenance = provenance
        self.demo_label = demo_label

    def to_model_payload(self) -> dict[str, Any]:
        """Facts sent to Grok. Local file paths are omitted."""
        payload: dict[str, Any] = {}
        if self.demo_label:
            payload["recordLabel"] = self.demo_label
        if self.camera_id:
            payload["cameraId"] = self.camera_id
        if self.location:
            payload["location"] = self.location
        if self.event_timestamp is not None:
            payload["eventTimestamp"] = self.event_timestamp
        if self.detection_type:
            payload["detectionType"] = self.detection_type
        if self.operational_priority:
            payload["operationalPriority"] = self.operational_priority
        payload["involvedTracks"] = list(self.involved_tracks)
        payload["observableMetrics"] = dict(self.observable_metrics)
        if self.evidence_status:
            payload["evidenceStatus"] = self.evidence_status
        if self.evidence_window is not None:
            start, end = self.evidence_window
            payload["evidenceWindow"] = {"start": start, "end": end}
        if self.provenance:
            payload["detectionProvenance"] = self.provenance
        return payload


def build_responder_briefing_input(event: dict[str, Any]) -> BriefingEvidence:
    if not isinstance(event, dict):
        raise TypeError("Incident evidence must be a dict.")

    evidence = event.get("evidence") if isinstance(event.get("evidence"), dict) else {}
    provenance = _provenance(event)
    demo = _demo_label(event, provenance)
    return BriefingEvidence(
        camera_id=_short_text(_first(event, "cameraId", "camera_id")),
        location=_short_text(_first(event, "location", "locationName", "location_name")),
        event_timestamp=_timestamp(_first(event, "eventTimestamp", "event_timestamp", "surfaced_at")),
        detection_type=_detection_type(_first(event, "detectionType", "detection_type")),
        operational_priority=_short_text(_first(event, "operationalPriority", "operational_priority", "priority")),
        involved_tracks=_tracks(_first(event, "involvedTracks", "involved_tracks", "participantTrackIds", "participant_track_ids")),
        observable_metrics=_metrics(event.get("observableMetrics", event.get("observable_metrics"))),
        evidence_status=_evidence_status(evidence.get("status") if evidence else event.get("evidenceStatus")),
        evidence_window=_window(evidence if evidence else event),
        provenance=_short_text(provenance),
        demo_label=demo,
    )


def _first(event: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in event and event[key] not in (None, ""):
            return event[key]
    return None


def _short_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:MAX_TEXT]


def _timestamp(value: Any) -> str | int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return _short_text(value)


def _detection_type(value: Any) -> str | None:
    text = _short_text(value)
    if text in SAFE_DETECTION_TYPES:
        return text
    return None


def _tracks(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tracks: list[str] = []
    for item in value:
        text = _short_text(str(item)) if isinstance(item, (str, int)) and not isinstance(item, bool) else None
        if text:
            tracks.append(text)
        if len(tracks) >= MAX_TRACKS:
            break
    return tracks


def _metrics(value: Any) -> dict[str, bool | int | float]:
    if not isinstance(value, dict):
        return {}
    kept: dict[str, bool | int | float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            continue
        name = " ".join(key.split())[:64]
        if _blocked_metric(name):
            continue
        if isinstance(item, bool) or (isinstance(item, (int, float)) and not isinstance(item, bool)):
            kept[name] = item
        if len(kept) >= MAX_METRICS:
            break
    return kept


def _blocked_metric(name: str) -> bool:
    lowered = name.lower()
    return any(fragment in lowered for fragment in BLOCKED_METRIC_FRAGMENTS)


def _evidence_status(value: Any) -> str | None:
    if value in {"unavailable", "reference"}:
        return value
    return None


def _window(source: dict[str, Any]) -> tuple[int | float, int | float] | None:
    start = source.get("windowStart", source.get("evidenceWindowStart"))
    end = source.get("windowEnd", source.get("evidenceWindowEnd"))
    nested = source.get("evidenceWindow")
    if isinstance(nested, dict):
        start = nested.get("start", start)
        end = nested.get("end", end)
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start:
        return (start, end)
    return None


def _provenance(event: dict[str, Any]) -> str | None:
    raw = event.get("detectionProvenance", event.get("provenance"))
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        label = raw.get("label")
        if isinstance(label, str) and label.strip():
            return label
    return None


def _demo_label(event: dict[str, Any], provenance: str | None) -> str | None:
    markers = [
        event.get("label"),
        event.get("recordLabel"),
        provenance,
        event.get("detectionMode"),
    ]
    for marker in markers:
        if isinstance(marker, str) and "TEST / DEMO" in marker.upper():
            return "TEST / DEMO EVENT"
    if event.get("detectionMode") == "demo_fallback":
        return "TEST / DEMO EVENT"
    return None
