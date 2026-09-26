#!/usr/bin/env python3
"""Play the ten cut demo clips so the cuts can be checked by eye.

Controls: SPACE pause/play, N next, P previous, R restart, Q quit.
No detection runs in this viewer.
"""

import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
CAMERA_DIR = REPO_ROOT / "data" / "cameras"
CLIP_NAMES = [f"cam_{index:03d}.mp4" for index in range(1, 11)]
WINDOW = "NotifYC demo clips"


def clip_paths() -> list[Path]:
    paths = [CAMERA_DIR / name for name in CLIP_NAMES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(
            "Missing clips in data/cameras:\n"
            + "\n".join(missing)
            + "\nRun scripts/prepare_demo_clips.py first."
        )
    return paths


def draw_banner(frame, camera: str, index: int, total: int, duration: float, paused: bool) -> None:
    lines = [
        camera,
        f"Clip {index} / {total}",
        f"Duration: {duration:.0f} sec" + ("  PAUSED" if paused else ""),
    ]
    y = 28
    for line in lines:
        cv2.putText(frame, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
        y += 28


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
    index = 0
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
                capture, fps, duration = open_clip(paths[index])
                paused = False
                held = None
                continue
            held = frame
        elif held is None:
            ok, frame = capture.read()
            if not ok:
                index = (index + 1) % len(paths)
                capture.release()
                capture, fps, duration = open_clip(paths[index])
                paused = False
                continue
            held = frame

        display = held.copy()
        draw_banner(display, f"CAM-{index + 1:03d}", index + 1, len(paths), duration, paused)
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
