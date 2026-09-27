#!/usr/bin/env python3
"""Read-only YOLO versus ByteTrack diagnostic for two known problem windows.

Does not change tracking settings or Phase 5. The low confidence floor is only
used here so detections below the pipeline threshold are visible.
"""

import json
import math
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

REPO = Path(__file__).resolve().parent.parent
DIAG_CONF = 0.05
PIPE_CONF = 0.15
NMS_IOU = 0.5
CLASSES = ("person", "bicycle", "car", "motorcycle", "bus", "truck", "train")
OUT = REPO / "outputs" / "diagnostics"


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    return inter / (area_a + area_b - inter)


def cover(inner, outer):
    ax1, ay1, ax2, ay2 = inner
    bx1, by1, bx2, by2 = outer
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    return inter / area


def center(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def read_window(model, names, class_ids, path, t0, t1, by_frame):
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    start = max(0, int(t0 * fps) - 1)
    end = int(t1 * fps) + 1
    capture.set(cv2.CAP_PROP_POS_FRAMES, start)
    rows = []
    frame_index = start
    while frame_index <= end:
        ok, frame = capture.read()
        if not ok:
            break
        result = model.predict(frame, conf=DIAG_CONF, iou=NMS_IOU, classes=class_ids, verbose=False, imgsz=640)[0]
        detections = []
        if result.boxes is not None:
            for box, class_id, conf in zip(
                result.boxes.xyxy.cpu().numpy(),
                result.boxes.cls.cpu().numpy().astype(int),
                result.boxes.conf.cpu().numpy(),
            ):
                xyxy = [float(value) for value in box]
                detections.append(
                    {
                        "class": names[int(class_id)],
                        "confidence": round(float(conf), 3),
                        "bbox": [round(value, 1) for value in xyxy],
                        "above_pipeline_conf": float(conf) >= PIPE_CONF,
                    }
                )
        rows.append(
            {
                "frame": frame_index,
                "timestamp": round(frame_index / fps, 3),
                "detections": detections,
                "tracks": by_frame.get(frame_index, []),
            }
        )
        frame_index += 1
        if frame_index % 15 == 0:
            print(f"  frame {frame_index}", flush=True)
    capture.release()
    return rows, fps


def track_rows(camera_record):
    grouped = {}
    for frame in camera_record["frames"]:
        grouped[frame["frame"]] = frame["objects"]
    return grouped


def closest(detections, point, limit):
    best = None
    for detection in detections:
        cx, cy = center(detection["bbox"])
        distance = math.hypot(cx - point[0], cy - point[1])
        if best is None or distance < best[0]:
            best = (distance, detection)
    if best and best[0] <= limit:
        return best
    return None


def follow(rows, seed_id, search_limit=140):
    point = None
    series = []
    for row in rows:
        owned = next((item for item in row["tracks"] if item["track_id"] == seed_id), None)
        if owned is not None:
            point = (owned["center_x"], owned["center_y"])
        if point is None:
            continue
        found = closest(row["detections"], point, search_limit)
        attached = []
        if found:
            detection = found[1]
            point = center(detection["bbox"])
            for item in row["tracks"]:
                if iou(item["bbox"], detection["bbox"]) > 0.15 or math.hypot(item["center_x"] - point[0], item["center_y"] - point[1]) < 70:
                    attached.append(item["track_id"])
        series.append(
            {
                "timestamp": row["timestamp"],
                "frame": row["frame"],
                "yolo": None if not found else found[1],
                "distance_px": None if not found else round(found[0], 1),
                "track_ids_on_box": attached,
                "seed_track_present": owned is not None,
            }
        )
    return series


def main() -> None:
    print("Loading yolo11n.pt", flush=True)
    model = YOLO(str(REPO / "yolo11n.pt"))
    names = model.names
    class_ids = [index for index, name in names.items() if name in CLASSES]
    tracks = json.loads((REPO / "outputs" / "tracking" / "tracks.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("CAM-001", REPO / "data" / "cameras" / "cam_001.mp4", 1.8, 3.2, 1),
        ("CAM-002", REPO / "data" / "cameras" / "cam_002.mp4", 1.5, 4.2, 12),
    ]
    summary = {"pipeline_confidence": PIPE_CONF, "diagnostic_floor": DIAG_CONF, "imgsz": 640, "nms_iou": NMS_IOU, "cases": {}}
    for camera, path, t0, t1, seed in jobs:
        print(f"Scanning {camera} {t0}-{t1}s", flush=True)
        rows, fps = read_window(model, names, class_ids, path, t0, t1, track_rows(tracks[camera]))
        # For CAM-002, seed the search from the first #12 box, then the follower walks forward.
        # A backward pass is stored separately.
        series = follow(rows, seed)
        backward = list(reversed(follow(list(reversed(rows)), seed, 160)))
        summary["cases"][camera] = {
            "fps": fps,
            "forward": series,
            "backward": backward,
            "frames": rows,
        }
    (OUT / "perception_trace.json").write_text(json.dumps(summary))
    print(f"Wrote {OUT / 'perception_trace.json'}")


if __name__ == "__main__":
    main()
