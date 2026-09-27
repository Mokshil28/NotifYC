import json
import unittest
from typing import Any

from briefing.client import GrokResponseError, GrokUnavailable, extract_output_text, request_body
from briefing.demo_event import demo_event
from briefing.evidence import build_responder_briefing_input
from briefing.fallback import fallback_briefing
from briefing.prompt import SYSTEM_PROMPT
from briefing.service import create_briefing
from briefing.validate import BriefingRejected, parse_briefing


def surfaced_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schemaVersion": 1,
        "eventId": "evt-test-not-used",
        "cameraId": "CAM-006",
        "eventTimestamp": 4.5,
        "detectionType": "possible_vehicle_collision",
        "priority": "high",
        "involvedTracks": ["3", "9"],
        "observableMetrics": {"collisionEvidenceScore": 70, "closing_speed_px_s": 40.5},
        "evidence": {
            "status": "reference",
            "clipRef": "outputs/tracking/cam_006_tracked.mp4",
            "windowStart": 3.0,
            "windowEnd": 4.5,
        },
        "detectionMode": "computer-vision",
        "provenance": {
            "pipeline": "cv/detect_collisions.py",
            "label": "Surfaced by the existing collision state machine",
        },
    }
    event.update(overrides)
    return event


class FakeGrok:
    def __init__(self, raw: str | None = None, error: Exception | None = None) -> None:
        self.raw = raw
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.error:
            raise self.error
        assert self.raw is not None
        return self.raw


def model_json(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "summary": "Possible vehicle collision surfaced at CAM-006. Review the supplied record.",
        "observations": [
            "Track ids 3 and 9 are on the record.",
            "Operational review priority on the record is high.",
        ],
        "limitations": "This wording does not confirm a collision.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class EvidenceInputTest(unittest.TestCase):
    def test_valid_structured_incident_keeps_only_supplied_facts(self) -> None:
        evidence = build_responder_briefing_input(surfaced_event())
        payload = evidence.to_model_payload()
        self.assertEqual(payload["cameraId"], "CAM-006")
        self.assertEqual(payload["detectionType"], "possible_vehicle_collision")
        self.assertEqual(payload["operationalPriority"], "high")
        self.assertEqual(payload["involvedTracks"], ["3", "9"])
        self.assertEqual(payload["observableMetrics"]["closing_speed_px_s"], 40.5)
        self.assertEqual(payload["evidenceWindow"], {"start": 3.0, "end": 4.5})
        self.assertEqual(payload["evidenceStatus"], "reference")
        self.assertNotIn("clipRef", json.dumps(payload))
        self.assertNotIn("detect_collisions", json.dumps(payload))
        self.assertIn("state machine", payload["detectionProvenance"])

    def test_missing_optional_metrics_stay_absent(self) -> None:
        event = surfaced_event()
        del event["observableMetrics"]
        del event["priority"]
        event.pop("location", None)
        evidence = build_responder_briefing_input(event)
        payload = evidence.to_model_payload()
        self.assertEqual(payload["observableMetrics"], {})
        self.assertNotIn("operationalPriority", payload)
        self.assertNotIn("location", payload)
        self.assertNotIn("injury", json.dumps(payload))

    def test_unsafe_detection_label_is_not_forwarded(self) -> None:
        evidence = build_responder_briefing_input(surfaced_event(detectionType="confirmed crash"))
        self.assertIsNone(evidence.detection_type)
        self.assertNotIn("confirmed", json.dumps(evidence.to_model_payload()))

    def test_blocked_metric_names_are_dropped(self) -> None:
        evidence = build_responder_briefing_input(
            surfaced_event(observableMetrics={"injury": True, "closing_speed_px_s": 1})
        )
        self.assertNotIn("injury", evidence.observable_metrics)
        self.assertIn("closing_speed_px_s", evidence.observable_metrics)


class GroundedResponseTest(unittest.TestCase):
    def test_documented_output_text_is_read(self) -> None:
        text = extract_output_text(
            {
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": model_json()}],
                    },
                ]
            }
        )
        parsed = parse_briefing(text)
        self.assertEqual(parsed["source"], "grok")
        self.assertIn("CAM-006", parsed["summary"])

    def test_valid_structured_incident_uses_grok_text(self) -> None:
        client = FakeGrok(model_json())
        result = create_briefing(surfaced_event(), client)
        self.assertEqual(result["source"], "grok")
        self.assertEqual(result["summary"].startswith("Possible vehicle collision"), True)
        sent = json.loads(client.calls[0][1])
        self.assertEqual(sent["cameraId"], "CAM-006")
        self.assertIn("you do not decide whether a collision occurred", client.calls[0][0].lower())

    def test_missing_metrics_do_not_get_invented_in_the_prompt(self) -> None:
        event = surfaced_event()
        del event["observableMetrics"]
        client = FakeGrok(model_json())
        create_briefing(event, client)
        sent = json.loads(client.calls[0][1])
        self.assertEqual(sent["observableMetrics"], {})

    def test_evidence_unavailable_is_passed_through(self) -> None:
        event = surfaced_event(evidence={"status": "unavailable", "clipRef": "", "windowStart": 1, "windowEnd": 2})
        client = FakeGrok(model_json(limitations="Visual evidence was not available in the supplied record."))
        result = create_briefing(event, client)
        sent = json.loads(client.calls[0][1])
        self.assertEqual(sent["evidenceStatus"], "unavailable")
        self.assertIn("not available", result["limitations"])

    def test_api_unavailable_uses_fallback(self) -> None:
        client = FakeGrok(error=GrokUnavailable("down"))
        result = create_briefing(surfaced_event(), client)
        self.assertEqual(result["source"], "fallback")
        self.assertIn("CAM-006", result["summary"])
        self.assertNotIn("confirmed", result["summary"].lower())

    def test_malformed_response_uses_fallback(self) -> None:
        result = create_briefing(surfaced_event(), FakeGrok("this is not json"))
        self.assertEqual(result["source"], "fallback")
        with self.assertRaises(BriefingRejected):
            parse_briefing("this is not json")

    def test_unsupported_fields_are_rejected(self) -> None:
        raw = model_json()
        payload = json.loads(raw)
        payload["injured"] = True
        payload["nypdRequired"] = True
        result = create_briefing(surfaced_event(), FakeGrok(json.dumps(payload)))
        self.assertEqual(result["source"], "fallback")
        self.assertNotIn("injured", result)
        self.assertNotIn("nypdRequired", result)

    def test_affirmative_claims_do_not_enter_the_briefing(self) -> None:
        raw = model_json(
            summary="Injured driver. Confirmed crash. NYPD required. 911 dispatched.",
            observations=["Driver at fault."],
            limitations="Severe crash.",
        )
        result = create_briefing(surfaced_event(), FakeGrok(raw))
        blob = json.dumps(result).lower()
        for phrase in ("injured", "confirmed crash", "nypd", "911", "at fault", "severe crash"):
            self.assertNotIn(phrase, blob)
        self.assertEqual(result["source"], "fallback")

    def test_unusable_output_shape_uses_fallback(self) -> None:
        client = FakeGrok(error=GrokResponseError("no output"))
        result = create_briefing(surfaced_event(), client)
        self.assertEqual(result["source"], "fallback")


class FallbackTest(unittest.TestCase):
    def test_fallback_restates_supplied_fields_only(self) -> None:
        evidence = build_responder_briefing_input(surfaced_event())
        result = fallback_briefing(evidence)
        self.assertEqual(result["source"], "fallback")
        self.assertIn("CAM-006", str(result["summary"]))
        self.assertIn("3, 9", " ".join(result["observations"]))  # type: ignore[arg-type]
        self.assertIn("collisionEvidenceScore=70", " ".join(result["observations"]))  # type: ignore[arg-type]
        self.assertIn("3.0 to 4.5", str(result["limitations"]))
        self.assertIn("does not confirm a collision", str(result["limitations"]))

    def test_unavailable_evidence_is_stated(self) -> None:
        event = demo_event("CAM-002")
        result = fallback_briefing(build_responder_briefing_input(event))
        self.assertIn("TEST / DEMO EVENT", result["summary"])
        self.assertIn("CAM-002", result["summary"])
        self.assertIn("not available", str(result["limitations"]))
        self.assertTrue(any("No observable metrics were supplied" in line for line in result["observations"]))

    def test_empty_optional_record_does_not_invent_a_camera_story(self) -> None:
        result = fallback_briefing(build_responder_briefing_input({}))
        self.assertIn("the camera on the record", str(result["summary"]))
        self.assertNotIn("CAM-001", json.dumps(result))
        self.assertNotIn("demo-1", json.dumps(result))


class RequestShapeTest(unittest.TestCase):
    def test_request_uses_the_documented_responses_body(self) -> None:
        body = request_body("grok-4.6", SYSTEM_PROMPT, "{}")
        self.assertEqual(body["model"], "grok-4.6")
        self.assertFalse(body["store"])
        self.assertEqual(body["input"][0]["role"], "system")
        self.assertEqual(body["input"][1]["role"], "user")
        self.assertIn("possible_vehicle_collision", body["input"][0]["content"])


if __name__ == "__main__":
    unittest.main()
