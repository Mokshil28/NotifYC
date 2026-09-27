"""Deterministic briefing used when Grok is missing or unusable.

The text is assembled from the supplied fields only. It is not produced by a model.
"""

from __future__ import annotations

from briefing.evidence import BriefingEvidence


def fallback_briefing(evidence: BriefingEvidence) -> dict[str, object]:
    camera = evidence.camera_id or "the camera on the record"
    prefix = "TEST / DEMO EVENT. " if evidence.demo_label else ""
    if evidence.detection_type == "possible_vehicle_collision":
        lead = f"{prefix}Possible vehicle collision surfaced at {camera}."
    else:
        lead = f"{prefix}Suspected traffic incident surfaced at {camera}."
    summary = f"{lead} This text restates the supplied record for operational review."

    observations: list[str] = []
    if evidence.location:
        observations.append(f"Location on the record: {evidence.location}.")
    if evidence.event_timestamp is not None:
        observations.append(f"Event timestamp on the record: {evidence.event_timestamp}.")
    if evidence.involved_tracks:
        observations.append("Tracked ids on the record: " + ", ".join(evidence.involved_tracks) + ".")
    else:
        observations.append("No participant track ids were supplied.")
    if evidence.observable_metrics:
        rendered = ", ".join(f"{key}={value}" for key, value in sorted(evidence.observable_metrics.items()))
        observations.append(f"Observable metrics on the record: {rendered}.")
    else:
        observations.append("No observable metrics were supplied.")
    if evidence.operational_priority:
        observations.append(f"Operational review priority on the record: {evidence.operational_priority}.")
    if evidence.provenance:
        note = evidence.provenance.rstrip(".")
        observations.append(f"Detection provenance on the record: {note}.")

    if evidence.evidence_status == "reference" and evidence.evidence_window is not None:
        start, end = evidence.evidence_window
        limitations = (
            f"A visual evidence reference was supplied for window {start} to {end}. "
            "Review that evidence before any operational action. This text does not confirm a collision."
        )
    elif evidence.evidence_status == "reference":
        limitations = (
            "A visual evidence reference was supplied without a window. "
            "Review that evidence before any operational action. This text does not confirm a collision."
        )
    elif evidence.evidence_status == "unavailable":
        limitations = (
            "Visual evidence was not available in the supplied record. "
            "This text does not confirm a collision."
        )
    else:
        limitations = "Evidence status was not supplied. This text does not confirm a collision."

    return {
        "summary": summary,
        "observations": observations,
        "limitations": limitations,
        "source": "fallback",
    }
