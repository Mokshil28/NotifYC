"""Accept only a small briefing object grounded in the supplied evidence."""

from __future__ import annotations

import json
from typing import Any

MAX_SUMMARY = 500
MAX_OBSERVATIONS = 4
MAX_OBSERVATION = 240
MAX_LIMITATIONS = 400

ALLOWED_KEYS = frozenset({"summary", "observations", "limitations"})

# Affirmative claims the briefing is not allowed to carry. A limitations
# sentence may say these topics were not supplied; that wording is checked
# separately so a denial is not treated as an inference.
AFFIRMATIVE_CLAIMS = (
    "confirmed crash",
    "confirmed collision",
    "definite collision",
    "definitely occurred",
    "collision occurred",
    "severe crash",
    "serious crash",
    "injured",
    "injury occurred",
    "injuries were",
    "fatal",
    "fatality",
    "at fault",
    "intoxicated",
    "drunk",
    "occupant",
    "nypd",
    "fdny",
    "911",
    "ems required",
    "dispatched",
)


class BriefingRejected(Exception):
    """The model text is not a usable grounded briefing."""


def parse_briefing(raw: str) -> dict[str, Any]:
    payload = _json_object(raw)
    if payload is None:
        raise BriefingRejected("Grok did not return a JSON object.")
    extra = set(payload) - ALLOWED_KEYS
    if extra:
        raise BriefingRejected("Grok returned fields that are not part of the briefing.")
    missing = ALLOWED_KEYS - set(payload)
    if missing:
        raise BriefingRejected("Grok omitted a required briefing field.")

    summary = _sentence(payload.get("summary"), MAX_SUMMARY)
    limitations = _sentence(payload.get("limitations"), MAX_LIMITATIONS)
    observations = _observations(payload.get("observations"))
    if summary is None or limitations is None or observations is None:
        raise BriefingRejected("Grok briefing fields had the wrong shape.")
    combined = " ".join([summary, limitations, *observations])
    if _has_affirmative_claim(combined):
        raise BriefingRejected("Grok briefing included an unsupported claim.")
    return {
        "summary": summary,
        "observations": observations,
        "limitations": limitations,
        "source": "grok",
    }


def _json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _sentence(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > limit:
        return None
    return text


def _observations(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value or len(value) > MAX_OBSERVATIONS:
        return None
    lines: list[str] = []
    for item in value:
        text = _sentence(item, MAX_OBSERVATION)
        if text is None:
            return None
        lines.append(text)
    return lines


def _has_affirmative_claim(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in AFFIRMATIVE_CLAIMS)
