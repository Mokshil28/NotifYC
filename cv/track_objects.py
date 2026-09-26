#!/usr/bin/env python3
"""Track road users in the ten NotifYC demo clips with YOLO11n and ByteTrack.

Every frame is detected, duplicate boxes of one physical object are removed
before association, and ByteTrack keeps the ID. The video shows one current
box. tracks.json stores the raw detection box and its center.
"""

import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import YAML, IterableSimpleNamespace

from process_video import ALLOWED_CLASSES, class_ids_for, draw_label, open_writer
from trajectories import TrajectoryStore

REPO_ROOT = Path(__file__).resolve().parent.parent
CAMERA_DIR = REPO_ROOT / "data" / "cameras"
OUTPUT_DIR = REPO_ROOT / "outputs" / "tracking"
MODEL_PATH = REPO_ROOT / "yolo11n.pt"
TRACKER_PATH = Path(__file__).resolve().parent / "bytetrack.yaml"
CLIP_NAMES = [f"cam_{index:03d}.mp4" for index in range(1, 11)]

# One detector setup for every camera. Confidence stays below track_high_thresh
# so a weaker box can still continue an existing ID.
CONFIDENCE_THRESHOLD = 0.15
NMS_IOU = 0.5
HISTORY_LENGTH = 20
# Display only. Raw boxes in tracks.json are not passed through this.
DISPLAY_ALPHA = 0.75
# Same-class boxes are one object when one mostly contains the other, or IoU is high.
SAME_CLASS_IOU = 0.55
SAME_CLASS_COVER = 0.8
# car/bus/truck hypotheses on the same physical vehicle.
VEHICLE_COVER = 0.85
VEHICLE_NAMES = {"car", "bus", "truck"}
# Green in BGR. Red stays unused until a later collision stage.
TRACK_COLOR = (70, 190, 60)

EDGE_MARGIN = 48
MIN_HANDOFF_FRAMES = 8
HANDOFF_FRAMES = 10
HANDOFF_PIXELS = 80


def camera_id(filename: str) -> str:
    number = filename.removeprefix("cam_").removesuffix(".mp4")
    return f"CAM-{number}"


def detection_boxes(result) -> Boxes:
    """Return this frame's YOLO boxes, or an empty set so lost-track timing still advances."""
    if result.boxes is not None and len(result.boxes) > 0:
        return result.boxes.cpu()
    height, width = result.orig_img.shape[:2]
    return Boxes(torch.zeros((0, 6)), (height, width))


def overlap_pair(first, second) -> tuple[float, float]:
    """Return IoU and the fraction of the smaller box that lies inside the other."""
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter
    return inter / union, inter / min(area_a, area_b)


def suppress_duplicate_detections(boxes: Boxes, names: dict) -> tuple[Boxes, int]:
    """Keep one detection when two boxes are the same physical object.

    YOLO NMS is per class and uses IoU, so a tight car box inside a loose car
    or truck box both survive and ByteTrack assigns each an ID. This runs
    before association and keeps the higher-confidence detection.
    """
    count = len(boxes)
    if count <= 1:
        return boxes, 0

    xyxy = boxes.xyxy.numpy()
    classes = boxes.cls.numpy().astype(int)
    vehicle_ids = {index for index, name in names.items() if name in VEHICLE_NAMES}
    order = np.argsort(-boxes.conf.numpy())
    keep: list[int] = []
    dropped = 0
    for index in order:
        reject = False
        for kept in keep:
            same_class = classes[index] == classes[kept]
            both_vehicles = int(classes[index]) in vehicle_ids and int(classes[kept]) in vehicle_ids
            if not same_class and not both_vehicles:
                continue
            iou, cover = overlap_pair(xyxy[index], xyxy[kept])
            if same_class and (iou >= SAME_CLASS_IOU or cover >= SAME_CLASS_COVER):
                reject = True
                break
            if both_vehicles and not same_class and cover >= VEHICLE_COVER:
                reject = True
                break
        if reject:
            dropped += 1
        else:
            keep.append(int(index))

    if dropped == 0:
        return boxes, 0
    return Boxes(boxes.data[keep], boxes.orig_shape), dropped


def load_tracker() -> tuple[BYTETracker, dict]:
    if not TRACKER_PATH.is_file():
        raise SystemExit(f"Tracker config not found: {TRACKER_PATH}")
    values = YAML.load(TRACKER_PATH)
    tracker = BYTETracker(args=IterableSimpleNamespace(**values))
    return tracker, values


class DisplaySmoother:
    """Light EMA of a box that already belongs to one track. Display only."""

    def __init__(self, alpha: float = DISPLAY_ALPHA):
        self.alpha = alpha
        self._boxes: dict[int, tuple[int, np.ndarray]] = {}

    def box(self, track_id: int, frame_index: int, raw_box, center, width: int, height: int) -> np.ndarray:
        current = np.asarray(raw_box, dtype=float)
        previous = self._boxes.get(track_id)
        if previous is not None and frame_index == previous[0] + 1:
            last = previous[1]
            distance = float(np.hypot(center[0] - (last[0] + last[2]) / 2, center[1] - (last[1] + last[3]) / 2))
            # Skip smoothing when the raw box actually jumps. Small edge jitter is damped.
            if distance <= max(24.0, 0.45 * max(width, height, 1)):
                current = self.alpha * current + (1.0 - self.alpha) * last
        self._boxes[track_id] = (frame_index, current)
        return current


def tracked_objects(
    names,
    boxes: Boxes,
    tracks,
    frame_index: int,
    timestamp: float,
    camera: str,
    store: TrajectoryStore,
    smoother: DisplaySmoother,
    canvas,
) -> list[dict]:
    """Store the raw detection and draw one smoothed box. No trail is drawn."""
    if tracks is None or len(tracks) == 0 or len(boxes) == 0:
        return []

    xyxy = boxes.xyxy.numpy()
    classes = boxes.cls.numpy().astype(int)
    confidences = boxes.conf.numpy()
    found = []

    for row in tracks:
        det_index = int(row[-1])
        if det_index < 0 or det_index >= len(xyxy):
            continue
        name = names[int(classes[det_index])]
        if name not in ALLOWED_CLASSES:
            continue

        x1, y1, x2, y2 = (int(value) for value in xyxy[det_index])
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
        track_id = int(row[4])
        confidence = float(confidences[det_index])
        store.update(track_id, (cx, cy))
        history = [[point[0], point[1]] for point in store.points(track_id)]
        shown = smoother.box(track_id, frame_index, (x1, y1, x2, y2), (cx, cy), width, height)
        draw_label(
            canvas,
            shown,
            f"{name.upper()} #{track_id} {confidence:.2f}",
            TRACK_COLOR,
        )
        found.append(
            {
                "camera": camera,
                "frame": frame_index,
                "timestamp": timestamp,
                "track_id": track_id,
                "class": name,
                "confidence": round(confidence, 2),
                "bbox": [x1, y1, x2, y2],
                "center_x": cx,
                "center_y": cy,
                "center": [cx, cy],
                "center_history": history,
                "width": width,
                "height": height,
            }
        )
    return found


def process_clip(model: YOLO, tracker: BYTETracker, class_ids: list[int], path: Path, writer_path: Path) -> dict:
    tracker.reset()
    probe = cv2.VideoCapture(str(path))
    if not probe.isOpened():
        raise SystemExit(f"Could not open {path}")
    width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = probe.get(cv2.CAP_PROP_FPS) or 30.0
    probe.release()

    writer = open_writer(writer_path, fps, (width, height))
    store = TrajectoryStore(max_length=HISTORY_LENGTH)
    smoother = DisplaySmoother()
    camera = camera_id(path.name)
    frames = []
    frame_index = 0
    suppressed = 0

    try:
        for result in model.predict(
            source=str(path),
            stream=True,
            conf=CONFIDENCE_THRESHOLD,
            iou=NMS_IOU,
            agnostic_nms=False,
            classes=class_ids,
            verbose=False,
        ):
            canvas = result.orig_img.copy()
            kept, dropped = suppress_duplicate_detections(detection_boxes(result), result.names)
            suppressed += dropped
            tracks = tracker.update(kept, result.orig_img)
            timestamp = round(frame_index / fps, 3)
            objects = tracked_objects(
                result.names,
                kept,
                tracks,
                frame_index,
                timestamp,
                camera,
                store,
                smoother,
                canvas,
            )
            writer.write(canvas)
            if objects:
                frames.append({"frame": frame_index, "timestamp": timestamp, "objects": objects})
            frame_index += 1
            if frame_index % 100 == 0:
                print(f"  {frame_index} frames", flush=True)
    finally:
        writer.release()

    if frame_index == 0:
        raise SystemExit(f"No frames were read from {path}")

    return {
        "fps": round(float(fps), 2),
        "width": width,
        "height": height,
        "frames_processed": frame_index,
        "duplicate_detections_suppressed": suppressed,
        "frames": frames,
    }


def point_of(item: dict) -> list:
    if "center" in item:
        return item["center"]
    return [item["center_x"], item["center_y"]]


def diagnose(tracks: dict) -> dict[str, dict]:
    """Track-quality counts. Same function is used on the previous output and the new one."""
    summary = {}
    for camera, record in tracks.items():
        grouped: dict[int, list[dict]] = defaultdict(list)
        max_simultaneous = 0
        duplicate_pairs = 0
        duplicate_frames = set()
        for frame in record["frames"]:
            objects = frame["objects"]
            max_simultaneous = max(max_simultaneous, len(objects))
            for item in objects:
                grouped[item["track_id"]].append(item)
            for index, first in enumerate(objects):
                for second in objects[index + 1 :]:
                    same = first["class"] == second["class"]
                    both_vehicles = first["class"] in VEHICLE_NAMES and second["class"] in VEHICLE_NAMES
                    if not same and not both_vehicles:
                        continue
                    iou, cover = overlap_pair(first["bbox"], second["bbox"])
                    duplicate = (same and (iou >= SAME_CLASS_IOU or cover >= SAME_CLASS_COVER)) or (
                        both_vehicles and not same and cover >= VEHICLE_COVER
                    )
                    if duplicate:
                        duplicate_pairs += 1
                        duplicate_frames.add(frame["frame"])

        lifetimes = []
        jumps = 0
        ends = []
        for track_id, observations in grouped.items():
            lifetimes.append(len(observations))
            if len(observations) >= MIN_HANDOFF_FRAMES:
                ends.append(observations)
            for earlier, later in zip(observations, observations[1:]):
                if later["frame"] - earlier["frame"] != 1:
                    continue
                start = point_of(earlier)
                finish = point_of(later)
                distance = float(np.hypot(finish[0] - start[0], finish[1] - start[1]))
                scale = max(earlier["width"], earlier["height"], 1)
                if distance > max(100.0, scale):
                    jumps += 1

        switches = 0
        width = record.get("width", 10_000)
        height = record.get("height", 10_000)
        for observations in ends:
            last = observations[-1]
            last_point = point_of(last)
            if not (EDGE_MARGIN < last_point[0] < width - EDGE_MARGIN and EDGE_MARGIN < last_point[1] < height - EDGE_MARGIN):
                continue
            for other in ends:
                if other is observations or other[0]["class"] != last["class"]:
                    continue
                gap = other[0]["frame"] - last["frame"]
                if gap < 1 or gap > HANDOFF_FRAMES:
                    continue
                other_point = point_of(other[0])
                distance = float(np.hypot(other_point[0] - last_point[0], other_point[1] - last_point[1]))
                if distance <= HANDOFF_PIXELS:
                    switches += 1

        ordered = sorted(lifetimes)
        summary[camera] = {
            "unique_tracks": len(grouped),
            "max_simultaneous": max_simultaneous,
            "median_lifetime": ordered[len(ordered) // 2] if ordered else 0,
            "short_tracks": sum(1 for life in lifetimes if life <= 3),
            "duplicate_pairs": duplicate_pairs,
            "duplicate_frames": len(duplicate_frames),
            "center_jumps": jumps,
            "id_switches": switches,
            "suppressed_detections": record.get("duplicate_detections_suppressed", 0),
        }
    return summary


def print_diagnostics(title: str, summary: dict[str, dict]) -> None:
    print(f"\n{title}")
    print(
        f"{'camera':8} {'ids':5} {'max':5} {'median':7} {'short':6} "
        f"{'dup_pairs':10} {'dup_frames':11} {'jumps':6} {'switches':9} {'suppressed':11}"
    )
    for camera, row in summary.items():
        print(
            f"{camera:8} {row['unique_tracks']:5} {row['max_simultaneous']:5} {row['median_lifetime']:7} "
            f"{row['short_tracks']:6} {row['duplicate_pairs']:10} {row['duplicate_frames']:11} "
            f"{row['center_jumps']:6} {row['id_switches']:9} {row['suppressed_detections']:11}"
        )


def print_settings(updated: dict) -> None:
    print("\nYOLO")
    print(f"  confidence {CONFIDENCE_THRESHOLD}")
    print(f"  nms iou {NMS_IOU} (same class)")
    print(f"  agnostic nms off; duplicate boxes are removed before ByteTrack")
    print("ByteTrack")
    for key in (
        "track_high_thresh",
        "track_low_thresh",
        "new_track_thresh",
        "track_buffer",
        "match_thresh",
        "fuse_score",
    ):
        print(f"  {key} {updated[key]}")
    print(f"Display smoothing alpha {DISPLAY_ALPHA} on consecutive frames only. JSON stores raw boxes.")
    blue, green, red = TRACK_COLOR
    print(f"Track color BGR ({blue}, {green}, {red})")


def verify(paths: list[Path], tracks: dict) -> None:
    import inspect

    drawing = inspect.getsource(tracked_objects)
    if "draw_trail(" in drawing or "cv2.line(" in drawing:
        raise SystemExit("Tracking video code still draws a trajectory line.")
    _blue, green, red = TRACK_COLOR
    if red >= green or red >= 120:
        raise SystemExit("Normal tracking color uses red.")

    print("\nOpenCV playback check")
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Missing or empty video: {path}")
        capture = cv2.VideoCapture(str(path))
        opened = capture.isOpened()
        ok, frame = capture.read()
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        if not opened or not ok or frame is None or frame_count <= 0:
            raise SystemExit(f"OpenCV could not read {path}")
        print(f"  {path.name}: {frame_count} frames, {frame.shape[1]}x{frame.shape[0]}")

    if len(tracks) != len(CLIP_NAMES):
        raise SystemExit(f"Expected {len(CLIP_NAMES)} cameras in tracks.json, found {len(tracks)}")

    for camera, record in tracks.items():
        ids = set()
        for frame in record["frames"]:
            for item in frame["objects"]:
                ids.add(item["track_id"])
                center = item["center"]
                x1, y1, x2, y2 = item["bbox"]
                raw_center = [(x1 + x2) / 2, (y1 + y2) / 2]
                if item["center_x"] != raw_center[0] or item["center_y"] != raw_center[1] or center != raw_center:
                    raise SystemExit(f"{camera} frame {item['frame']} center is not the raw box center")
                if item["center_history"][-1] != center:
                    raise SystemExit(f"{camera} track {item['track_id']} history does not end at the raw center")
                if len(item["center_history"]) > HISTORY_LENGTH:
                    raise SystemExit(f"{camera} track {item['track_id']} stored more than {HISTORY_LENGTH} centers")
                if "smooth" in item or "display" in item:
                    raise SystemExit(f"{camera} stored a display-smoothed coordinate")
        if not ids:
            raise SystemExit(f"{camera} produced no track IDs")
        print(f"  {camera}: {len(ids)} track IDs, raw centers stored")


def main() -> None:
    missing = [name for name in CLIP_NAMES if not (CAMERA_DIR / name).is_file()]
    if missing:
        raise SystemExit("Missing clips:\n" + "\n".join(missing))
    if not MODEL_PATH.is_file():
        raise SystemExit(f"Model weights not found: {MODEL_PATH}")

    tracks_path = OUTPUT_DIR / "tracks.json"
    if tracks_path.is_file():
        previous = json.loads(tracks_path.read_text())
        print_diagnostics("Previous tracking diagnostics", diagnose(previous))

    print(f"\nLoading {MODEL_PATH.name}")
    model = YOLO(str(MODEL_PATH))
    tracker, settings = load_tracker()
    class_ids = class_ids_for(model)
    print("Classes:", ", ".join(model.names[index] for index in class_ids))
    print_settings(settings)

    tracks = {}
    written = []
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in CLIP_NAMES:
        camera = camera_id(name)
        output_path = OUTPUT_DIR / f"{name.removesuffix('.mp4')}_tracked.mp4"
        print(f"Tracking {camera}...", flush=True)
        record = process_clip(model, tracker, class_ids, CAMERA_DIR / name, output_path)
        tracks[camera] = record
        written.append(output_path)
        print(
            f"  wrote {output_path.name} ({record['frames_processed']} frames, "
            f"{record['duplicate_detections_suppressed']} duplicate detections removed)",
            flush=True,
        )

    tracks_path.write_text(json.dumps(tracks, indent=2))
    print_diagnostics("Updated tracking diagnostics", diagnose(tracks))
    verify(written, tracks)
    print(f"\nWrote {tracks_path}")
    print("View: python scripts/view_tracking_results.py")


if __name__ == "__main__":
    main()
