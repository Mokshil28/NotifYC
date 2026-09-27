import unittest

from cv.notifyc_event import event_from_cv, events_to_send, validate_event


def surfaced(**overrides):
    event = {
        "camera_id": "CAM-003",
        "collisionDetected": True,
        "collisionEvidenceScore": 64,
        "participant_track_ids": [8, 2],
        "surfaced_at": 3.2,
        "closest_interaction_time": 2.8,
        "label": "possible_vehicle_collision",
        "candidateDiagnostics": {
            "closing_speed_px_s": 80.5,
            "projected_path_convergence": True,
            "candidate_metrics": {"ignored": 1},
        },
    }
    event.update(overrides)
    return event


class EventConversionTest(unittest.TestCase):
    def test_no_detection_sends_nothing(self):
        analysis = {"events": [], "rejected_candidates": [surfaced(collisionDetected=False)]}
        self.assertEqual(events_to_send(analysis), [])

    def test_surfaced_event_is_valid_and_stable(self):
        first = event_from_cv(surfaced())
        second = event_from_cv(surfaced())
        self.assertEqual(first["eventId"], second["eventId"])
        self.assertEqual(validate_event(first), [])
        self.assertEqual(first["cameraId"], "CAM-003")
        self.assertEqual(first["involvedTracks"], ["8", "2"])
        self.assertNotIn("candidate_metrics", first["observableMetrics"])
        self.assertEqual(first["detectionMode"], "computer-vision")
        self.assertNotIn("injury", json_blob(first))

    def test_rejected_row_is_not_converted(self):
        with self.assertRaises(ValueError):
            event_from_cv(surfaced(collisionDetected=False))


def json_blob(event):
    import json

    return json.dumps(event)


if __name__ == "__main__":
    unittest.main()
