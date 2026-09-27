"""Instructions and the small JSON payload sent to Grok."""

from __future__ import annotations

import json

from briefing.evidence import BriefingEvidence

SYSTEM_PROMPT = """You write a short operational briefing for a person reviewing a traffic-camera record.

Use only the JSON evidence in the user message. Do not add facts, names, or measurements that are not in that JSON.

The computer-vision record is authoritative about whether anything was surfaced. You do not decide whether a collision occurred. If detectionType is possible_vehicle_collision, keep the wording at "possible vehicle collision" or "suspected traffic incident". Never say a collision is confirmed, definite, or proven.

Do not infer injuries, medical severity, fatalities, fault, intent, intoxication, occupants, emergency-service requirements, or legal conclusions. operationalPriority is an operational review priority, not a medical severity.

If a field is missing, say that it was not supplied. If evidenceStatus is unavailable, say visual evidence was not available in the supplied record. If evidenceStatus is reference, say visual evidence was referenced and should be reviewed. Do not describe what the picture shows unless that description is already in observableMetrics.

Return one JSON object and no other text. The only keys are:
- summary: one or two short sentences
- observations: an array of at most four short sentences
- limitations: one short sentence about missing evidence or uncertainty

Do not include markdown."""


def user_message(evidence: BriefingEvidence) -> str:
    return json.dumps(evidence.to_model_payload(), sort_keys=True, separators=(",", ":"))
