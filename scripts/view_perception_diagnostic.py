#!/usr/bin/env python3
"""Overlay raw YOLO scores and ByteTrack IDs for the perception diagnostic windows.

Controls: SPACE pause/play, N next window, P previous window, R restart, Q quit.
This does not change the collision viewer.
"""

import json
import sys
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parent.parent
TRACE = REPO / "outputs" / "diagnostics" / "perception_trace.json"
WINDOWS = [
    ("CAM-001", REPO / "data" / "cameras" / "cam_001.mp4"),
    ("CAM-002", REPO / "data" / "cameras" / "cam_002.mp4"),
]
NAME = "NotifYC perception diagnostic"


def load():
    if not TRACE.is_file():
        raise SystemExit("Missing outputs/diagnostics/perception_trace.json\nRun scripts/diagnose_perception.py first.")
    return json.loads(TRACE.read_text())


def draw(frame, row):
    for detection in row["detections"]:
        x1, y1, x2, y2 = [int(value) for value in detection["bbox"]]
        color = (0, 220, 0) if detection["above_pipeline_conf"] else (0, 180, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        label = f"{detection['class']} YOLO {detection['confidence']:.2f}"
        cv2.putText(frame, label, (x1, max(16, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
    for item in row["tracks"]:
        x1, y1, x2, y2 = item["bbox"]
        cv2.putText(
            frame,
            f"Track #{item['track_id']}",
            (x1, min(frame.shape[0] - 8, y2 + 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )


def main() -> None:
    trace = load()
    index = 0
    camera, path = WINDOWS[index]
    frames = {row["frame"]: row for row in trace["cases"][camera]["frames"]}
    ordered = sorted(frames)
    cursor = 0
    capture = cv2.VideoCapture(str(path))
    paused = False
    held = None
    cv2.namedWindow(NAME, cv2.WINDOW_NORMAL)
    while True:
        frame_index = ordered[cursor]
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            break
        held = frame
        display = held.copy()
        draw(display, frames[frame_index])
        cv2.putText(display, f"{camera}  {frame_index}", (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow(NAME, display)
        key = cv2.waitKey(0 if paused else 40) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        if key == ord(" "):
            paused = not paused
        elif key in (ord("n"), ord("N"), ord("p"), ord("P")):
            index = (index + 1 if key in (ord("n"), ord("N")) else index - 1) % len(WINDOWS)
            camera, path = WINDOWS[index]
            frames = {row["frame"]: row for row in trace["cases"][camera]["frames"]}
            ordered = sorted(frames)
            cursor = 0
            capture.release()
            capture = cv2.VideoCapture(str(path))
            paused = False
        elif key in (ord("r"), ord("R")):
            cursor = 0
        elif not paused:
            cursor = min(cursor + 1, len(ordered) - 1)
    capture.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
