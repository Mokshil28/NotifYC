#!/usr/bin/env python3
"""Play tracked clips with a short motion readout.

Controls: SPACE pause/play, N next, P previous, R restart, Q quit.
No trajectory tails and no collision coloring.
"""

import json
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = REPO_ROOT / "outputs" / "tracking"
MOTION_PATH = REPO_ROOT / "outputs" / "motion" / "motion_analysis.json"
CLIP_NAMES = [f"cam_{index:03d}_tracked.mp4" for index in range(1, 11)]
WINDOW = "NotifYC motion"
TEXT = (255, 255, 255)


def clip_paths() -> list[Path]:
    paths = [VIDEO_DIR / name for name in CLIP_NAMES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing tracked clips:\n" + "\n".join(missing))
    if not MOTION_PATH.is_file():
        raise SystemExit("Missing outputs/motion/motion_analysis.json\nRun cv/analyze_motion.py first.")
    return paths


def load_motion() -> dict:
    data = json.loads(MOTION_PATH.read_text())
    indexed = {}
    for camera, record in data["cameras"].items():
        by_frame = {}
        for track in record["tracks"].values():
            for sample in track["observations"]:
                by_frame.setdefault(sample["frame"], {"tracks": [], "pairs": []})
                by_frame[sample["frame"]]["tracks"].append(sample)
        for pair in record["pairs"]:
            for sample in pair["samples"]:
                by_frame.setdefault(sample["frame"], {"tracks": [], "pairs": []})
                by_frame[sample["frame"]]["pairs"].append(sample)
        indexed[camera] = by_frame
    return indexed


def draw_line(frame, text: str, y: int) -> None:
    cv2.putText(frame, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TEXT, 1, cv2.LINE_AA)


def motion_word(sample: dict) -> str:
    if sample["is_stationary"]:
        return "stationary"
    speed = sample["speed_px_s"]
    if speed is None:
        return "no step"
    if speed <= 0:
        return "idle"
    return "moving"


def approach_word(sample: dict) -> str:
    rate = sample["relative_approach_px_s"]
    if rate is None:
        return "held"
    if rate > 20:
        return "approaching"
    if rate < -20:
        return "separating"
    return "holding"


def draw_readout(frame, camera: str, index: int, total: int, duration: float, paused: bool, frame_index: int, motion) -> None:
    lines = [
        camera,
        f"Clip {index} / {total}",
        f"Duration: {duration:.0f} sec" + ("  PAUSED" if paused else ""),
    ]
    page = motion.get(camera, {}).get(frame_index, {"tracks": [], "pairs": []})
    tracks = sorted(page["tracks"], key=lambda sample: abs(sample["speed_px_s"] or 0), reverse=True)[:6]
    for sample in tracks:
        speed = sample["speed_px_s"]
        speed_text = "n/a" if speed is None else f"{speed:.0f} px/s"
        lines.append(f"{sample['class'].upper()} #{sample['track_id']}  {speed_text}  {motion_word(sample)}")
    pairs = sorted(page["pairs"], key=lambda sample: sample["separation_px"])[:3]
    for sample in pairs:
        lines.append(
            f"#{sample['track_a']}/#{sample['track_b']}  "
            f"{sample['separation_px']:.0f} px  {approach_word(sample)}"
        )
    y = 28
    for line in lines:
        draw_line(frame, line, y)
        y += 24


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
    motion = load_motion()
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
        draw_readout(display, f"CAM-{index + 1:03d}", index + 1, len(paths), duration, paused, shown, motion)
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
