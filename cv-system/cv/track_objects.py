#!/usr/bin/env python3
"""Track road users in the ten NotifYC demo clips with YOLO11n and ByteTrack.

Every frame is detected, duplicate boxes of one physical object are removed
before association, and ByteTrack keeps the ID. The video shows one current
box. tracks.json stores the raw detection box and its center.
"""

import json
import math
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

# Detections at or above this are normal measurements. A new track still needs
# either one detection at NEW_TRACK_CONFIDENCE or several weaker ones.
CONFIDENCE_THRESHOLD = 0.15
LOW_CONFIDENCE = 0.08
NEW_TRACK_CONFIDENCE = 0.30
CONFIRM_FRAMES = 2
INFERENCE_SIZE = 640
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


def compatible_class(first: str, second: str) -> bool:
    return first == second or (first in VEHICLE_NAMES and second in VEHICLE_NAMES)


def shift_box(box, vx: float, vy: float):
    return [box[0] + vx, box[1] + vy, box[2] + vx, box[3] + vy]


class TrackMemory:
    """Last confirmed box and step for each live track."""

    def __init__(self, memory_frames: int = 12):
        self.memory_frames = memory_frames
        self.tracks: dict[int, dict] = {}

    def remember(self, objects: list[dict], frame_index: int) -> None:
        for item in objects:
            previous = self.tracks.get(item["track_id"])
            vx = vy = 0.0
            if previous is not None and frame_index - previous["frame"] <= 2:
                vx = item["center_x"] - previous["center"][0]
                vy = item["center_y"] - previous["center"][1]
            self.tracks[item["track_id"]] = {
                "bbox": item["bbox"],
                "center": (item["center_x"], item["center_y"]),
                "class": item["class"],
                "width": item["width"],
                "height": item["height"],
                "vx": vx,
                "vy": vy,
                "frame": frame_index,
            }
        stale = [track_id for track_id, state in self.tracks.items() if frame_index - state["frame"] > self.memory_frames]
        for track_id in stale:
            del self.tracks[track_id]

    def matches(self, box, class_name: str) -> list[int]:
        """Return one track when it is clearly closer than any other."""
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        width = max(1.0, box[2] - box[0])
        height = max(1.0, box[3] - box[1])
        ranked = []
        for track_id, state in self.tracks.items():
            if not compatible_class(class_name, state["class"]):
                continue
            predicted = shift_box(state["bbox"], state["vx"], state["vy"])
            iou, cover = overlap_pair(box, predicted)
            reach = max(1.0, float(np.hypot(state["width"], state["height"])))
            distance = float(np.hypot(cx - (state["center"][0] + state["vx"]), cy - (state["center"][1] + state["vy"])))
            ratio = (width * height) / max(1.0, state["width"] * state["height"])
            if ratio < 0.45 or ratio > 2.2:
                continue
            if iou < 0.25 and distance > 0.45 * reach and cover < 0.5:
                continue
            ranked.append((iou, -distance, track_id))
        ranked.sort(reverse=True)
        if not ranked:
            return []
        if len(ranked) == 1:
            return [ranked[0][2]]
        best_iou, best_distance, best_id = ranked[0][0], -ranked[0][1], ranked[0][2]
        second_iou, second_distance = ranked[1][0], -ranked[1][1]
        if best_iou >= 0.25 and (second_iou <= best_iou * 0.5 or second_distance > best_distance + 25):
            return [best_id]
        return []


def gate_low_detections(boxes: Boxes, names: dict, memory: TrackMemory) -> tuple[Boxes, int]:
    """Keep a sub-0.15 box only when it agrees with exactly one live track."""
    if len(boxes) == 0:
        return boxes, 0
    xyxy = boxes.xyxy.numpy()
    classes = boxes.cls.numpy().astype(int)
    keep = []
    for index, box in enumerate(xyxy):
        matched = memory.matches(box, names[int(classes[index])])
        if len(matched) == 1:
            keep.append(index)
    if not keep:
        return Boxes(boxes.data[:0], boxes.orig_shape), 0
    return Boxes(boxes.data[keep], boxes.orig_shape), len(keep)


class TentativeTracks:
    """Birth a track from repeated 0.15–0.30 detections. One strong detection does not wait."""

    def __init__(self, confirm_frames: int):
        self.confirm_frames = confirm_frames
        self._items: list[dict] = []

    def _consistent(self, box, class_name: str, item: dict) -> bool:
        if not compatible_class(class_name, item["class"]):
            return False
        iou, cover = overlap_pair(box, item["bbox"])
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        distance = np.hypot(cx - item["center"][0], cy - item["center"][1])
        reach = np.hypot(item["width"], item["height"])
        ratio = ((box[2] - box[0]) * (box[3] - box[1])) / max(1.0, item["width"] * item["height"])
        if ratio < 0.45 or ratio > 2.2:
            return False
        return iou >= 0.3 or cover >= 0.5 or distance <= 0.5 * reach

    def boost_indices(self, xyxy, classes, confidences, names: dict, frame_index: int) -> list[int]:
        used = set()
        kept = []
        boost = []
        for item in self._items:
            best = None
            for index, box in enumerate(xyxy):
                confidence = float(confidences[index])
                if index in used or not (CONFIDENCE_THRESHOLD <= confidence < NEW_TRACK_CONFIDENCE):
                    continue
                if not self._consistent(box, names[int(classes[index])], item):
                    continue
                distance = np.hypot((box[0] + box[2]) / 2 - item["center"][0], (box[1] + box[3]) / 2 - item["center"][1])
                if best is None or distance < best[0]:
                    best = (distance, index, box)
            if best is not None and frame_index - item["frame"] <= 2:
                _, index, box = best
                used.add(index)
                item["hits"] += 1
                item["frame"] = frame_index
                item["bbox"] = [float(value) for value in box]
                item["center"] = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                item["width"] = float(box[2] - box[0])
                item["height"] = float(box[3] - box[1])
                item["confidences"].append(float(confidences[index]))
                if item["hits"] >= self.confirm_frames:
                    boost.append(index)
                else:
                    kept.append(item)
            elif frame_index - item["frame"] <= 2:
                kept.append(item)
        for index, box in enumerate(xyxy):
            confidence = float(confidences[index])
            if index in used or not (CONFIDENCE_THRESHOLD <= confidence < NEW_TRACK_CONFIDENCE):
                continue
            kept.append(
                {
                    "class": names[int(classes[index])],
                    "bbox": [float(value) for value in box],
                    "center": ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
                    "width": float(box[2] - box[0]),
                    "height": float(box[3] - box[1]),
                    "hits": 1,
                    "frame": frame_index,
                    "confidences": [confidence],
                }
            )
        self._items = kept
        return boost


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


def refine_matched_box(track_id: int, box, class_name: str, confidence: float, memory: TrackMemory, candidates: list[dict]):
    """Prefer a same-size detection near the predicted center when YOLO also emits a jumped box."""
    state = memory.tracks.get(track_id)
    if state is None or not candidates:
        return box, confidence
    previous_area = max(1.0, state["width"] * state["height"])
    width = max(1.0, box[2] - box[0])
    height = max(1.0, box[3] - box[1])
    area_ratio = (width * height) / previous_area
    predicted = (state["center"][0] + state["vx"], state["center"][1] + state["vy"])
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    step = max(18.0, float(np.hypot(state["vx"], state["vy"])) + 12.0)
    jump = float(np.hypot(center_x - predicted[0], center_y - predicted[1]))
    if 0.65 <= area_ratio <= 1.55 and jump <= step:
        return box, confidence
    if area_ratio > 1.7:
        clamped_x = min(max(predicted[0], box[0]), box[2])
        clamped_y = min(max(predicted[1], box[1]), box[3])
        if float(np.hypot(clamped_x - predicted[0], clamped_y - predicted[1])) <= 24:
            half_w = state["width"] / 2
            half_h = state["height"] / 2
            cx = min(max(clamped_x, box[0] + half_w), box[2] - half_w)
            cy = min(max(clamped_y, box[1] + half_h), box[3] - half_h)
            return [cx - half_w, cy - half_h, cx + half_w, cy + half_h], confidence
    best = None
    for candidate in candidates:
        if not compatible_class(candidate["class"], state["class"]):
            continue
        cbox = candidate["bbox"]
        cand_area = max(1.0, (cbox[2] - cbox[0]) * (cbox[3] - cbox[1]))
        ratio = cand_area / previous_area
        if ratio < 0.6 or ratio > 1.55:
            continue
        cand_center = ((cbox[0] + cbox[2]) / 2, (cbox[1] + cbox[3]) / 2)
        distance = float(np.hypot(cand_center[0] - predicted[0], cand_center[1] - predicted[1]))
        if distance > step:
            continue
        score = distance + abs(math.log(ratio)) * 30.0
        if best is None or score < best[0]:
            best = (score, cbox, candidate["confidence"])
    if best is None:
        return box, confidence
    return best[1], best[2]


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
    source_confidence=None,
    memory: TrackMemory | None = None,
    candidates: list[dict] | None = None,
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
        track_id = int(row[4])
        name = names[int(classes[det_index])]
        if name not in ALLOWED_CLASSES:
            continue

        raw_box = [float(value) for value in xyxy[det_index]]
        confidence = float(confidences[det_index] if source_confidence is None else source_confidence[det_index])
        if memory is not None and candidates:
            raw_box, confidence = refine_matched_box(track_id, raw_box, name, confidence, memory, candidates)
        x1, y1, x2, y2 = (int(value) for value in raw_box)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
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


def concat_boxes(first: Boxes, second: Boxes) -> tuple[Boxes, np.ndarray]:
    if len(first) == 0:
        return second, second.conf.numpy().copy() if len(second) else np.empty(0)
    if len(second) == 0:
        return first, first.conf.numpy().copy()
    data = torch.cat([first.data, second.data], dim=0)
    confidence = torch.cat([first.conf, second.conf], dim=0).numpy().copy()
    return Boxes(data, first.orig_shape), confidence


def process_clip(
    model: YOLO,
    tracker: BYTETracker,
    class_ids: list[int],
    path: Path,
    writer_path: Path | None,
    confirm_frames: int = CONFIRM_FRAMES,
    image_size: int = INFERENCE_SIZE,
) -> dict:
    tracker.reset()
    probe = cv2.VideoCapture(str(path))
    if not probe.isOpened():
        raise SystemExit(f"Could not open {path}")
    width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = probe.get(cv2.CAP_PROP_FPS) or 30.0
    probe.release()

    writer = open_writer(writer_path, fps, (width, height)) if writer_path is not None else None
    store = TrajectoryStore(max_length=HISTORY_LENGTH)
    smoother = DisplaySmoother()
    memory = TrackMemory()
    tentative = TentativeTracks(confirm_frames)
    camera = camera_id(path.name)
    frames = []
    frame_index = 0
    suppressed = 0
    low_continuations = 0
    normal_detections = 0
    untracked_detections = 0

    try:
        for result in model.predict(
            source=str(path),
            stream=True,
            conf=LOW_CONFIDENCE,
            iou=NMS_IOU,
            imgsz=image_size,
            agnostic_nms=False,
            classes=class_ids,
            verbose=False,
        ):
            canvas = result.orig_img.copy()
            detected = detection_boxes(result)
            if len(detected):
                confidence = detected.conf
                low = detected[(confidence >= LOW_CONFIDENCE) & (confidence < CONFIDENCE_THRESHOLD)]
                normal = detected[confidence >= CONFIDENCE_THRESHOLD]
            else:
                low = detected
                normal = detected
            normal, dropped = suppress_duplicate_detections(normal, result.names)
            suppressed += dropped
            normal_detections += len(normal)
            measured_confidence = normal.conf.numpy().copy() if len(normal) else np.empty(0)
            if len(normal):
                promote = tentative.boost_indices(
                    normal.xyxy.numpy(),
                    normal.cls.numpy().astype(int),
                    measured_confidence,
                    result.names,
                    frame_index,
                )
                if promote:
                    edited = normal.data.clone()
                    edited[promote, 4] = NEW_TRACK_CONFIDENCE
                    normal = Boxes(edited, normal.orig_shape)
            low_kept, continued = gate_low_detections(low, result.names, memory)
            low_continuations += continued
            if len(normal) and len(low_kept):
                combined = Boxes(torch.cat([normal.data, low_kept.data], dim=0), normal.orig_shape)
                source_confidence = np.concatenate([measured_confidence, low_kept.conf.numpy()])
            elif len(normal):
                combined = normal
                source_confidence = measured_confidence
            else:
                combined = low_kept
                source_confidence = low_kept.conf.numpy().copy() if len(low_kept) else None
            tracks = tracker.update(combined, result.orig_img)
            timestamp = round(frame_index / fps, 3)
            candidate_boxes = []
            if len(combined):
                for box, class_id, conf in zip(combined.xyxy.numpy(), combined.cls.numpy().astype(int), combined.conf.numpy()):
                    candidate_boxes.append(
                        {
                            "bbox": [float(value) for value in box],
                            "class": result.names[int(class_id)],
                            "confidence": float(conf),
                        }
                    )
            objects = tracked_objects(
                result.names,
                combined,
                tracks,
                frame_index,
                timestamp,
                camera,
                store,
                smoother,
                canvas,
                source_confidence if len(combined) else None,
                memory,
                candidate_boxes,
            )
            # Count normal detections that did not land on an output box.
            if len(normal):
                used = set()
                if tracks is not None and len(tracks):
                    used = {int(row[-1]) for row in tracks if int(row[-1]) < len(normal)}
                for index, box in enumerate(normal.xyxy.numpy()):
                    if index in used:
                        continue
                    untracked_detections += 1
            memory.remember(objects, frame_index)
            if writer is not None:
                writer.write(canvas)
            if objects:
                frames.append({"frame": frame_index, "timestamp": timestamp, "objects": objects})
            frame_index += 1
            if frame_index % 100 == 0:
                print(f"  {frame_index} frames", flush=True)
    finally:
        if writer is not None:
            writer.release()

    if frame_index == 0:
        raise SystemExit(f"No frames were read from {path}")

    return {
        "fps": round(float(fps), 2),
        "width": width,
        "height": height,
        "frames_processed": frame_index,
        "duplicate_detections_suppressed": suppressed,
        "low_continuations": low_continuations,
        "normal_detections": normal_detections,
        "untracked_detections": untracked_detections,
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
    print(f"  model yolo11n  imgsz {INFERENCE_SIZE}")
    print(f"  normal confidence {CONFIDENCE_THRESHOLD}")
    print(f"  continuation floor {LOW_CONFIDENCE}")
    print(f"  immediate new track {NEW_TRACK_CONFIDENCE}")
    print(f"  tentative confirmation {CONFIRM_FRAMES} frames")
    print(f"  nms iou {NMS_IOU} (same class)")
    print("  agnostic nms off; duplicate boxes are removed before ByteTrack")
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
