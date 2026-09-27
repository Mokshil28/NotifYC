"""Isolated responder briefing.

Call ``create_briefing`` only after a collision has already been surfaced.
A Grok outage returns a deterministic restatement and does not raise, so
incident creation and responder routing can ignore this module.
"""

from briefing.service import create_briefing

__all__ = ["create_briefing"]
