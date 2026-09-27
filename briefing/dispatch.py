"""Short spoken and written dispatch from a validated briefing.

Uses only fields already present on the event and briefing. Does not detect
collisions, rank incidents, or assign responders.
"""

from __future__ import annotations

import re
from typing import Any

_BLOCKED = (
    "confirmed crash",
    "confirmed collision",
    "injured",
    "injury",
    "fatal",
    "fatality",
    "at fault",
    "medical severity",
    "people trapped",
    "dispatched",
    "911",
    "nypd",
    "ems",
)


def concise_dispatch(camera_id: str, summary: str, priority: str = "", responder: str = "") -> str:
    sentences = [f"NotifYC alert. Possible collision surfaced at {camera_id}."]
    text = " ".join(summary.split()).strip()
    if text:
        if not text.endswith("."):
            text += "."
        sentences.append(text)
    if priority.strip():
        sentences.append(f"Operational priority {priority.strip()}.")
    if responder.strip():
        sentences.append(f"Simulated responder {responder.strip()}.")
    sentences.append("Review the visual evidence.")
    return " ".join(sentences)


def briefing_is_sendable(briefing: dict[str, Any]) -> bool:
    if briefing.get("source") not in {"grok", "fallback"}:
        return False
    summary = briefing.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return False
    observations = briefing.get("observations")
    limitations = briefing.get("limitations")
    if not isinstance(observations, list) or not isinstance(limitations, str):
        return False
    combined = " ".join([summary, limitations, *[str(item) for item in observations]]).lower()
    return not any(phrase in combined for phrase in _BLOCKED)


def evidence_clip(camera_id: str, root) -> str | None:
    match = re.fullmatch(r"CAM-(0\d{2})", camera_id)
    if match is None:
        return None
    number = int(match.group(1))
    if not 1 <= number <= 10:
        return None
    path = root / "data" / "cameras" / f"cam_{match.group(1)}.mp4"
    return str(path) if path.is_file() else None
