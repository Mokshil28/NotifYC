#!/usr/bin/env python3
"""Detect road users in the ten NotifYC demo clips. No tracking."""

import json
from pathlib import Path

import cv2
from ultralytics import YOLO

from process_video import (
    ALLOWED_CLASSES,
    CLASS_COLORS,
    box_center,
    class_ids_for,
    draw_label,
    open_writer,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CAMERA_DIR = REPO_ROOT / "data" / "cameras"
OUTPUT_DIR = REPO_ROOT / "outputs" / "detection"
MODEL_PATH = REPO_ROOT / "yolo11n.pt"
CONFIDENCE_THRESHOLD = 0.25
CLIP_NAMES = [f"cam_{index:03d}.mp4" for index in range(1, 11)]


def camera_id(filename: str) -> str:
    number = filename.removeprefix("cam_").removesuffix(".mp4")
    return f"CAM-{number}"


def detections_in(result) -> list[dict]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []

    found = []
    names = result.names
    for box, class_id, confidence in zip(
        boxes.xyxy.cpu().numpy(),
        boxes.cls.cpu().numpy().astype(int),
        boxes.conf.cpu().numpy(),
    ):
        name = names[int(class_id)]
        if name not in CLASS_COLORS:
            continue
        x1, y1, x2, y2 = (int(value) for value in box)
        center = box_center(box)
        found.append(
            {
                "class": name,
                "confidence": round(float(confidence), 2),
                "bbox": [x1, y1, x2, y2],
                "center": [center[0], center[1]],
            }
        )
        draw_label(result.plot_ready, box, f"{name.upper()} {confidence:.2f}", CLASS_COLORS[name])
    return found


def process_clip(model: YOLO, class_ids: list[int], path: Path, writer_path: Path) -> dict:
    probe = cv2.VideoCapture(str(path))
    if not probe.isOpened():
        raise SystemExit(f"Could not open {path}")
    width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = probe.get(cv2.CAP_PROP_FPS) or 30.0
    probe.release()

    writer = open_writer(writer_path, fps, (width, height))
    frames = []
    classes = set()
    confidences = []
    frames_with_objects = 0
    max_simultaneous = 0
    frame_index = 0

    try:
        for result in model.predict(
            source=str(path),
            stream=True,
            conf=CONFIDENCE_THRESHOLD,
            classes=class_ids,
            verbose=False,
        ):
            result.plot_ready = result.orig_img.copy()
            objects = detections_in(result)
            writer.write(result.plot_ready)
            if objects:
                frames_with_objects += 1
                max_simultaneous = max(max_simultaneous, len(objects))
                for item in objects:
                    classes.add(item["class"])
                    confidences.append(item["confidence"])
                frames.append(
                    {
                        "frame": frame_index,
                        "timestamp": round(frame_index / fps, 2),
                        "objects": objects,
                    }
                )
            frame_index += 1
    finally:
        writer.release()

    if frame_index == 0:
        raise SystemExit(f"No frames were read from {path}")

    average = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    return {
        "record": {
            "fps": round(fps, 2),
            "width": width,
            "height": height,
            "frames": frames,
        },
        "summary": {
            "frames_processed": frame_index,
            "frames_with_detections": frames_with_objects,
            "classes": sorted(classes),
            "total_detections": len(confidences),
            "max_simultaneous_road_users": max_simultaneous,
            "average_confidence": average,
            "note": "total_detections counts boxes across frames, not unique vehicles",
        },
    }


def print_summary(summaries: dict[str, dict]) -> None:
    print(f"\nConfidence threshold: {CONFIDENCE_THRESHOLD:.2f} on every camera")
    for camera, summary in summaries.items():
        class_list = ", ".join(summary["classes"]) if summary["classes"] else "none"
        print(f"\n{camera}")
        print(f"Frames: {summary['frames_processed']}")
        print(f"Classes: {class_list}")
        print(f"Frames with detections: {summary['frames_with_detections']}")
        print(f"Max simultaneous road users: {summary['max_simultaneous_road_users']}")
        print(f"Average confidence: {summary['average_confidence']:.2f}")
        print(f"Total detections: {summary['total_detections']}")


def main() -> None:
    missing = [name for name in CLIP_NAMES if not (CAMERA_DIR / name).is_file()]
    if missing:
        raise SystemExit("Missing clips:\n" + "\n".join(missing))
    if not MODEL_PATH.is_file():
        raise SystemExit(f"Model weights not found: {MODEL_PATH}")

    print(f"Loading {MODEL_PATH.name}")
    model = YOLO(str(MODEL_PATH))
    class_ids = class_ids_for(model)
    print("Classes:", ", ".join(model.names[index] for index in class_ids))

    detections = {}
    summaries = {}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in CLIP_NAMES:
        camera = camera_id(name)
        print(f"Detecting {camera}...", flush=True)
        result = process_clip(model, class_ids, CAMERA_DIR / name, OUTPUT_DIR / f"{name.removesuffix('.mp4')}_detected.mp4")
        detections[camera] = result["record"]
        summaries[camera] = result["summary"]

    (OUTPUT_DIR / "detections.json").write_text(json.dumps(detections, indent=2))
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2))
    print_summary(summaries)
    print(f"\nWrote annotations to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
