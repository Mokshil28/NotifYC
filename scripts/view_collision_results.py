#!/usr/bin/env python3
"""Play the ten tracked clips and mark Possible Collision events in red.

Controls: SPACE pause/play, N next, P previous, R restart, Q quit.
Unrelated vehicles keep the tracking color already drawn on the clip.
"""

import json
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = REPO_ROOT / "outputs" / "tracking"
TRACKS_PATH = REPO_ROOT / "outputs" / "tracking" / "tracks.json"
RESULTS_PATH = REPO_ROOT / "outputs" / "evaluation" / "results.json"
CLIP_NAMES = [f"cam_{index:03d}_tracked.mp4" for index in range(1, 11)]
WINDOW = "NotifYC possible collisions"
RED = (0, 0, 255)
TEXT = (255, 255, 255)


def clip_paths() -> list[Path]:
    paths = [VIDEO_DIR / name for name in CLIP_NAMES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing tracked clips:\n" + "\n".join(missing))
    if not RESULTS_PATH.is_file():
        raise SystemExit("Missing outputs/evaluation/results.json\nRun cv/detect_collisions.py first.")
    return paths


def load_indexes() -> tuple[dict, dict]:
    results = json.loads(RESULTS_PATH.read_text())
    tracks = json.loads(TRACKS_PATH.read_text())
    events = {}
    boxes = {}
    for camera, record in results["cameras"].items():
        events[camera] = [event for event in record["events"] if event.get("collisionDetected")]
        boxes[camera] = {}
        for frame in tracks[camera]["frames"]:
            for item in frame["objects"]:
                boxes[camera][(frame["frame"], item["track_id"])] = item
    return events, boxes


def draw_text(frame, text: str, origin: tuple[int, int], scale: float, color: tuple[int, int, int]) -> None:
    x_pos, y_pos = origin
    cv2.putText(frame, text, (x_pos, y_pos), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, (x_pos, y_pos), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def draw_red_box(frame, item: dict) -> None:
    x1, y1, x2, y2 = item["bbox"]
    cv2.rectangle(frame, (x1, y1), (x2, y2), RED, 3)
    label = f"{item['class'].upper()} #{item['track_id']}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, text_height), baseline = cv2.getTextSize(label, font, 0.5, 1)
    top = max(0, y1 - text_height - baseline - 4)
    cv2.rectangle(frame, (x1, top), (x1 + text_width + 4, top + text_height + baseline + 4), RED, -1)
    cv2.putText(frame, label, (x1 + 2, top + text_height + 1), font, 0.5, (0, 0, 0), 1, cv2.LINE_AA)


def active_events(events: list[dict], frame_index: int) -> list[dict]:
    visible = []
    for event in events:
        start = event.get("surfaced_frame")
        end = event.get("display_end_frame")
        if start is None or end is None:
            continue
        if start <= frame_index <= end:
            visible.append(event)
    return visible


def draw_overlay(frame, camera: str, index: int, total: int, duration: float, paused: bool, frame_index: int, events, boxes) -> None:
    lines = [camera, f"Clip {index} / {total}", f"Duration: {duration:.0f} sec" + ("  PAUSED" if paused else "")]
    y_pos = 28
    for line in lines:
        draw_text(frame, line, (16, y_pos), 0.7, TEXT)
        y_pos += 28

    current = active_events(events.get(camera, []), frame_index)
    involved = set()
    for event in current:
        participants = event.get("participant_track_ids") or event["track_ids_examined"]
        involved.update(participants)
        names = "  ".join(
            f"{class_name.upper()} #{track_id}" for track_id, class_name in zip(participants, event["classes"])
        )
        draw_text(frame, "POSSIBLE COLLISION", (16, y_pos), 0.7, RED)
        y_pos += 28
        draw_text(frame, f"Evidence: {event['collisionEvidenceScore']}/100", (16, y_pos), 0.6, TEXT)
        y_pos += 26
        draw_text(frame, names, (16, y_pos), 0.6, TEXT)
        y_pos += 30
    for track_id in involved:
        item = boxes.get(camera, {}).get((frame_index, track_id))
        if item is not None:
            draw_red_box(frame, item)


def open_clip(path: Path) -> tuple[cv2.VideoCapture, float, float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"OpenCV could not open {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frames / fps if fps else 0.0
    return capture, fps, duration


def main() -> None:
    paths = clip_paths()
    events, boxes = load_indexes()
    index = 0
    frame_index = 0
    capture, fps, duration = open_clip(paths[index])
    paused = False
    held = None
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    while True:
        if not paused:
            ok, frame = capture.read()
            if not ok:
                capture.release()
                index = (index + 1) % len(paths)
                frame_index = 0
                capture, fps, duration = open_clip(paths[index])
                paused = False
                held = None
                continue
            held = frame
            shown = frame_index
            frame_index += 1
        elif held is None:
            ok, frame = capture.read()
            if not ok:
                index = (index + 1) % len(paths)
                frame_index = 0
                capture.release()
                capture, fps, duration = open_clip(paths[index])
                paused = False
                continue
            held = frame
            shown = frame_index
            frame_index += 1
        else:
            shown = max(0, frame_index - 1)

        display = held.copy()
        camera = f"CAM-{index + 1:03d}"
        draw_overlay(display, camera, index + 1, len(paths), duration, paused, shown, events, boxes)
        cv2.imshow(WINDOW, display)

        delay = 30 if paused else max(1, int(1000 / fps))
        key = cv2.waitKey(delay) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        if key == ord(" "):
            paused = not paused
        elif key in (ord("n"), ord("N"), ord("p"), ord("P"), ord("r"), ord("R")):
            if key in (ord("n"), ord("N")):
                index = (index + 1) % len(paths)
            elif key in (ord("p"), ord("P")):
                index = (index - 1) % len(paths)
            capture.release()
            frame_index = 0
            capture, fps, duration = open_clip(paths[index])
            paused = False
            held = None

    capture.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
