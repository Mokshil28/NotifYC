import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briefing.client import GrokUnavailable
from briefing.dispatch import briefing_is_sendable, concise_dispatch, evidence_clip
from briefing.elevenlabs import ElevenLabsError
from briefing.service import create_briefing


def ok_briefing(camera: str = "CAM-004") -> dict:
    return {
        "summary": f"Possible vehicle collision surfaced at {camera}.",
        "observations": ["Track ids were supplied."],
        "limitations": "Visual evidence was referenced and should be reviewed.",
        "source": "grok",
    }


class DispatchTest(unittest.TestCase):
    def test_dispatch_uses_the_supplied_camera_and_omits_missing_fields(self) -> None:
        text = concise_dispatch("CAM-004", "Possible vehicle collision surfaced at CAM-004.")
        self.assertIn("CAM-004", text)
        self.assertNotIn("CAM-001", text)
        self.assertNotIn("Operational priority", text)
        self.assertNotIn("Simulated responder", text)

    def test_optional_priority_and_responder_are_included_when_present(self) -> None:
        text = concise_dispatch("CAM-009", "Closing motion was observed.", "normal", "UNIT-12")
        self.assertIn("Operational priority normal.", text)
        self.assertIn("Simulated responder UNIT-12.", text)

    def test_rejected_briefing_is_not_sendable(self) -> None:
        self.assertFalse(briefing_is_sendable({
            "summary": "Confirmed crash with injuries. EMS dispatched.",
            "observations": ["People trapped."],
            "limitations": "",
            "source": "grok",
        }))

    def test_validated_grok_briefing_is_sendable(self) -> None:
        self.assertTrue(briefing_is_sendable(ok_briefing()))

    def test_clip_mapping_matches_the_ten_demo_files(self) -> None:
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(evidence_clip("CAM-001", root), str(root / "data" / "cameras" / "cam_001.mp4"))
        self.assertEqual(evidence_clip("CAM-010", root), str(root / "data" / "cameras" / "cam_010.mp4"))
        self.assertIsNone(evidence_clip("CAM-042", root))

    def test_missing_video_file_is_reported_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(evidence_clip("CAM-003", Path(folder)))

    def test_fallback_source_is_distinct_from_grok(self) -> None:
        with patch("briefing.service.XaiResponsesClient.from_env", side_effect=GrokUnavailable("missing")):
            briefing = create_briefing(
                {
                    "cameraId": "CAM-008",
                    "detectionType": "possible_vehicle_collision",
                    "involvedTracks": [],
                    "evidence": {"status": "unavailable", "windowStart": 0, "windowEnd": 1},
                    "detectionMode": "computer-vision",
                }
            )
        self.assertEqual(briefing["source"], "fallback")
        self.assertNotEqual(briefing["source"], "grok")

    def test_elevenlabs_failure_does_not_remove_the_text(self) -> None:
        calls = []

        def speak(_text):
            raise ElevenLabsError("ElevenLabs request failed with HTTP 401.")

        def deliver(payload):
            calls.append(payload)
            return {"ok": True, "result": {"audio": "SKIPPED", "text": "SENT", "video": "SENT"}}

        text = concise_dispatch("CAM-005", "Possible vehicle collision surfaced at CAM-005.")
        audio = None
        try:
            audio = speak(text)
        except ElevenLabsError:
            audio = None
        result = deliver({"text": text, "audioPath": audio, "videoPath": "cam_005.mp4"})
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]["audioPath"])
        self.assertIn("CAM-005", calls[0]["text"])
        self.assertEqual(result["result"]["text"], "SENT")
