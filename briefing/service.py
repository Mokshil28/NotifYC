"""Turn an already-surfaced incident record into a responder briefing."""

from __future__ import annotations

from typing import Any, Protocol

from briefing.client import GrokResponseError, GrokUnavailable, XaiResponsesClient
from briefing.evidence import BriefingEvidence, build_responder_briefing_input
from briefing.fallback import fallback_briefing
from briefing.prompt import SYSTEM_PROMPT, user_message
from briefing.validate import BriefingRejected, parse_briefing


class BriefingClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text."""


def create_briefing(event: dict[str, Any], client: BriefingClient | None = None) -> dict[str, Any]:
    """Return a briefing. Grok failures become the deterministic fallback.

    ``event`` may be the dict produced by ``cv.notifyc_event.event_from_cv``
    or a smaller record with only some of those fields.
    """
    evidence = build_responder_briefing_input(event)
    return briefing_from_evidence(evidence, client)


def briefing_from_evidence(evidence: BriefingEvidence, client: BriefingClient | None = None) -> dict[str, Any]:
    model_client = client
    if model_client is None:
        try:
            model_client = XaiResponsesClient.from_env()
        except GrokUnavailable:
            return fallback_briefing(evidence)
    try:
        raw = model_client.complete(SYSTEM_PROMPT, user_message(evidence))
        return parse_briefing(raw)
    except (GrokUnavailable, GrokResponseError, BriefingRejected):
        return fallback_briefing(evidence)
