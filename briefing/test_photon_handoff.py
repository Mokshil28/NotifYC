import unittest
from unittest.mock import patch

from briefing.client import GrokUnavailable
from briefing.service import create_briefing


class OneSendTest(unittest.TestCase):
    def test_one_validated_briefing_is_one_payload(self) -> None:
        fake = type("Fake", (), {"complete": staticmethod(lambda system, user: """{
          "summary": "Possible vehicle collision surfaced at CAM-008.",
          "observations": ["Track ids were supplied."],
          "limitations": "Visual evidence was referenced and should be reviewed."
        }""")})()
        briefing = create_briefing(
            {
                "cameraId": "CAM-008",
                "eventTimestamp": 1.2,
                "detectionType": "possible_vehicle_collision",
                "priority": "normal",
                "involvedTracks": ["1", "2"],
                "observableMetrics": {"closing_speed_px_s": 10},
                "evidence": {"status": "reference", "windowStart": 1.0, "windowEnd": 1.2},
                "provenance": {"label": "Surfaced by the existing collision state machine"},
                "detectionMode": "computer-vision",
            },
            fake,
        )
        self.assertEqual(briefing["source"], "grok")
        payloads = [briefing]
        self.assertEqual(len(payloads), 1)

    def test_fallback_is_labeled_fallback(self) -> None:
        with patch("briefing.service.XaiResponsesClient.from_env", side_effect=GrokUnavailable("XAI_API_KEY is not set.")):
            briefing = create_briefing(
                {
                    "cameraId": "CAM-008",
                    "detectionType": "possible_vehicle_collision",
                    "involvedTracks": [],
                    "evidence": {"status": "unavailable", "windowStart": 0, "windowEnd": 1},
                    "detectionMode": "computer-vision",
                },
                None,
            )
        self.assertEqual(briefing["source"], "fallback")

    def test_rejected_model_text_is_not_marked_grok(self) -> None:
        fake = type("Fake", (), {"complete": staticmethod(lambda system, user: '{"summary":"Confirmed crash with injuries."}')})()
        briefing = create_briefing(
            {
                "cameraId": "CAM-008",
                "detectionType": "possible_vehicle_collision",
                "involvedTracks": ["4"],
                "evidence": {"status": "unavailable", "windowStart": 0, "windowEnd": 1},
                "detectionMode": "computer-vision",
            },
            fake,
        )
        self.assertNotEqual(briefing["source"], "grok")
        self.assertEqual(briefing["source"], "fallback")


if __name__ == "__main__":
    unittest.main()
