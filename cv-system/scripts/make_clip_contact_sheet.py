#!/usr/bin/env python3
"""Build a labeled contact sheet from the middle frame of each demo clip."""

from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
CAMERA_DIR = REPO_ROOT / "data" / "cameras"
OUTPUT_PATH = REPO_ROOT / "outputs" / "demo_clips_contact_sheet.jpg"
CLIP_NAMES = [f"cam_{index:03d}.mp4" for index in range(1, 11)]
CELL_WIDTH = 384
CELL_HEIGHT = 240
LABEL_HEIGHT = 36
COLUMNS = 5


def middle_frame(path: Path):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return None
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frame_count > 1:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
    ok, frame = capture.read()
    if not ok:
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = capture.read()
    capture.release()
    if not ok:
        return None
    return frame


def cell_for(path: Path, camera: str) -> np.ndarray:
    tile = np.full((CELL_HEIGHT + LABEL_HEIGHT, CELL_WIDTH, 3), 32, dtype=np.uint8)
    frame = middle_frame(path) if path.is_file() else None
    if frame is None:
        message = "MISSING" if not path.is_file() else "UNREADABLE"
        cv2.putText(tile, message, (16, CELL_HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 80, 220), 2, cv2.LINE_AA)
    else:
        height, width = frame.shape[:2]
        scale = min(CELL_WIDTH / width, CELL_HEIGHT / height)
        resized = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
        y = (CELL_HEIGHT - resized.shape[0]) // 2
        x = (CELL_WIDTH - resized.shape[1]) // 2
        tile[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    cv2.putText(
        tile,
        camera,
        (12, CELL_HEIGHT + 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return tile


def main() -> None:
    tiles = [cell_for(CAMERA_DIR / name, f"CAM-{index:03d}") for index, name in enumerate(CLIP_NAMES, start=1)]
    rows = [np.hstack(tiles[start : start + COLUMNS]) for start in range(0, len(tiles), COLUMNS)]
    sheet = np.vstack(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(OUTPUT_PATH), sheet):
        raise SystemExit(f"Could not write {OUTPUT_PATH}")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
