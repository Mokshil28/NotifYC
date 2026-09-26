#!/usr/bin/env python3
"""Annotate a fixed-camera traffic video with YOLO11n boxes and ByteTrack IDs."""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from trajectories import TrajectoryStore, draw_trail

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "outputs" / "processed"

# COCO names we care about for vehicle-pedestrian and vehicle-cyclist review.
ALLOWED_CLASSES = ("person", "bicycle", "car", "motorcycle", "bus", "truck")

# BGR colors, one per class, so trails stay readable on asphalt.
CLASS_COLORS = {
    "person": (0, 200, 255),
    "bicycle": (255, 160, 0),
    "car": (80, 200, 80),
    "motorcycle": (220, 80, 220),
    "bus": (60, 140, 255),
    "truck": (40, 80, 220),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect and track road users in a fixed-camera traffic video."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to the input video.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Annotated video path. Defaults to outputs/processed/<stem>_processed.mp4.",
    )
    parser.add_argument("--model", default="yolo11n.pt", help="Pretrained Ultralytics weights.")
    parser.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold.")
    return parser.parse_args()


def class_ids_for(model: YOLO) -> list[int]:
    wanted = set(ALLOWED_CLASSES)
    ids = [index for index, name in model.names.items() if name in wanted]
    missing = wanted.difference(model.names[index] for index in ids)
    if missing:
        raise SystemExit(f"Model is missing expected classes: {sorted(missing)}")
    return sorted(ids)


def box_center(xyxy) -> tuple[int, int]:
    x1, y1, x2, y2 = xyxy
    return int((x1 + x2) / 2), int((y1 + y2) / 2)


def draw_label(frame, xyxy, label: str, color: tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = (int(value) for value in xyxy)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, text_height), baseline = cv2.getTextSize(label, font, 0.5, 1)
    top = max(0, y1 - text_height - baseline - 4)
    cv2.rectangle(frame, (x1, top), (x1 + text_width + 4, top + text_height + baseline + 4), color, -1)
    cv2.putText(frame, label, (x1 + 2, top + text_height + 1), font, 0.5, (0, 0, 0), 1, cv2.LINE_AA)


def annotate_frame(frame, result, store: TrajectoryStore, stats: dict) -> None:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return

    xyxy = boxes.xyxy.cpu().numpy()
    classes = boxes.cls.cpu().numpy().astype(int)
    confidences = boxes.conf.cpu().numpy()
    if boxes.id is None:
        track_ids = [None] * len(xyxy)
    else:
        track_ids = boxes.id.cpu().numpy().astype(int)

    names = result.names
    for box, class_id, confidence, track_id in zip(xyxy, classes, confidences, track_ids):
        name = names[int(class_id)]
        if name not in CLASS_COLORS:
            continue

        color = CLASS_COLORS[name]
        if track_id is None:
            label = f"{name} {confidence:.2f}"
        else:
            track_id = int(track_id)
            center = box_center(box)
            store.update(track_id, center)
            draw_trail(frame, store.points(track_id), color)
            stats["track_ids"].add(track_id)
            stats["tracks_by_class"][name].add(track_id)
            label = f"{name} #{track_id} {confidence:.2f}"

        draw_label(frame, box, label, color)
        stats["detections"] += 1


def open_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():
        raise SystemExit(f"Could not open video writer for {path}")
    return writer


def print_stats(stats: dict, elapsed: float) -> None:
    frames = stats["frames"]
    rate = frames / elapsed if elapsed > 0 else 0.0
    print("\nProcessing complete")
    print(f"Input:            {stats['input']}")
    print(f"Output:           {stats['output']}")
    print(f"Resolution:       {stats['width']}x{stats['height']}")
    print(f"Source FPS:       {stats['fps']:.2f}")
    print(f"Frames written:   {frames}")
    print(f"Elapsed seconds:  {elapsed:.1f}")
    print(f"Processing FPS:   {rate:.1f}")
    print(f"Boxes drawn:      {stats['detections']}")
    print(f"Unique track IDs: {len(stats['track_ids'])}")
    print("Unique tracks by class:")
    for name in ALLOWED_CLASSES:
        print(f"  {name:12} {len(stats['tracks_by_class'][name])}")


def main() -> None:
    args = parse_args()
    input_path = args.input
    if not input_path.is_file():
        raise SystemExit(f"Input video not found: {input_path}")

    output_path = args.output
    if output_path is None:
        output_path = OUTPUT_DIR / f"{input_path.stem}_processed.mp4"

    probe = cv2.VideoCapture(str(input_path))
    if not probe.isOpened():
        raise SystemExit(f"Could not open video: {input_path}")
    width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = probe.get(cv2.CAP_PROP_FPS) or 30.0
    probe.release()

    print(f"Loading {args.model}")
    model = YOLO(args.model)
    selected = class_ids_for(model)
    print("Tracking classes:", ", ".join(model.names[index] for index in selected))

    store = TrajectoryStore(max_length=20)
    writer = open_writer(output_path, fps, (width, height))
    stats = {
        "input": input_path,
        "output": output_path,
        "width": width,
        "height": height,
        "fps": fps,
        "frames": 0,
        "detections": 0,
        "track_ids": set(),
        "tracks_by_class": {name: set() for name in ALLOWED_CLASSES},
    }

    started = time.perf_counter()
    results = model.track(
        source=str(input_path),
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        classes=selected,
        conf=args.conf,
        verbose=False,
    )

    try:
        for result in results:
            frame = result.orig_img.copy()
            annotate_frame(frame, result, store, stats)
            writer.write(frame)
            stats["frames"] += 1
            if stats["frames"] % 100 == 0:
                print(f"Processed {stats['frames']} frames...", flush=True)
    finally:
        writer.release()

    if stats["frames"] == 0:
        raise SystemExit("No frames were written. Check that the input video is readable.")

    print_stats(stats, time.perf_counter() - started)


if __name__ == "__main__":
    main()
