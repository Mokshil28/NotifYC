"""Short visual continuation and causal geometry for established vehicles.

Continuation never creates a track. It only holds a vehicle that already has
several detector observations, using pyramidal Lucas-Kanade on features inside
the last reliable box. Stabilized center and size are for motion only. The
raw detector box stays on the observation.
"""

import math

import cv2
import numpy as np

VEHICLE_NAMES = {"car", "bus", "truck"}


def overlap_pair(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter
    return inter / union, inter / min(area_a, area_b)


def compatible_class(first: str, second: str) -> bool:
    return first == second or (first in VEHICLE_NAMES and second in VEHICLE_NAMES)

# About a third of a second at 30 fps. Longer gaps are a new detection problem.
MAX_PROPAGATED_FRAMES = 10
MIN_DETECTOR_FRAMES = 8
MIN_FEATURES = 6
MIN_INLIER_FRACTION = 0.5
MAX_FLOW_ERROR = 12.0


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _area(box):
    return max(1.0, (box[2] - box[0]) * (box[3] - box[1]))


def _median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


class GeometryStabilizer:
    """Causal center and size. A single inconsistent jump does not set velocity."""

    def __init__(self):
        self._state: dict[int, dict] = {}

    def apply(self, item: dict) -> None:
        track_id = item["track_id"]
        frame_index = item["frame"]
        raw_center = (float(item["center_x"]), float(item["center_y"]))
        raw_w = float(item["width"])
        raw_h = float(item["height"])
        previous = self._state.get(track_id)
        if previous is None or frame_index - previous["frame"] > 2:
            center = raw_center
            width, height = raw_w, raw_h
            points = [raw_center]
            widths = [raw_w]
            heights = [raw_h]
            steps: list[float] = []
            baseline = 8.0
        else:
            points = (previous["points"] + [raw_center])[-3:]
            center = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
            step = (center[0] - previous["center"][0], center[1] - previous["center"][1])
            magnitude = math.hypot(*step)
            baseline = previous.get("baseline", 8.0)
            cap = max(16.0, 1.45 * baseline)
            if magnitude > cap and magnitude > 0:
                scale = cap / magnitude
                center = (
                    previous["center"][0] + step[0] * scale,
                    previous["center"][1] + step[1] * scale,
                )
                magnitude = cap
            # Rise slowly, so one released jump cannot become the new speed ceiling.
            baseline = 0.75 * baseline + 0.25 * magnitude
            widths = (previous["widths"] + [raw_w])[-5:]
            heights = (previous["heights"] + [raw_h])[-5:]
            width = _median(widths)
            height = _median(heights)
            steps = (previous["steps"] + [magnitude])[-5:]
        self._state[track_id] = {
            "frame": frame_index,
            "center": center,
            "width": width,
            "height": height,
            "points": points,
            "widths": widths,
            "heights": heights,
            "steps": steps,
            "baseline": baseline,
        }
        half_w = width / 2
        half_h = height / 2
        item["stabilized_center_x"] = round(center[0], 1)
        item["stabilized_center_y"] = round(center[1], 1)
        item["stabilized_width"] = round(width, 1)
        item["stabilized_height"] = round(height, 1)
        item["stabilized_bbox"] = [
            round(center[0] - half_w, 1),
            round(center[1] - half_h, 1),
            round(center[0] + half_w, 1),
            round(center[1] + half_h, 1),
        ]


class VisualContinuation:
    """Continue an established vehicle through a short detector gap."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._prev_gray = None
        self._tracks: dict[int, dict] = {}

    def _features(self, gray, box):
        x1 = max(0, int(box[0] + 0.1 * (box[2] - box[0])))
        y1 = max(0, int(box[1] + 0.1 * (box[3] - box[1])))
        x2 = min(self.width, int(box[2] - 0.1 * (box[2] - box[0])))
        y2 = min(self.height, int(box[3] - 0.1 * (box[3] - box[1])))
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        mask = np.zeros(gray.shape, dtype=np.uint8)
        mask[y1:y2, x1:x2] = 255
        needed = 4 if (x2 - x1) * (y2 - y1) < 3500 else MIN_FEATURES
        points = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=30,
            qualityLevel=0.01,
            minDistance=3,
            blockSize=5,
            mask=mask,
        )
        if points is None or len(points) < needed:
            return None
        return points.reshape(-1, 1, 2)

    def _seed(self, gray, state, box):
        state["points"] = self._features(gray, box)
        state["box"] = [float(value) for value in box]
        state["center"] = _center(box)

    def _fresh(self, class_name: str, box, confidence: float) -> dict:
        center = _center(box)
        return {
            "class": class_name,
            "detector_frames": 0,
            "propagated": 0,
            "box": [float(value) for value in box],
            "detector_box": [float(value) for value in box],
            "center": center,
            "steps": [],
            "points": None,
            "reliability": min(1.0, 0.55 + 0.45 * confidence),
        }

    def _note_step(self, state, box):
        center = _center(box)
        step = math.hypot(center[0] - state["center"][0], center[1] - state["center"][1])
        state["steps"] = (state["steps"] + [step])[-5:]
        state["center"] = center
        state["box"] = [float(value) for value in box]
        state["detector_box"] = [float(value) for value in box]

    def _eligible(self, state) -> bool:
        return state["class"] in VEHICLE_NAMES and state["detector_frames"] >= MIN_DETECTOR_FRAMES

    def _used_by_established(self, box, objects) -> bool:
        for item in objects:
            state = self._tracks.get(item["track_id"])
            if state is None or state["detector_frames"] < MIN_DETECTOR_FRAMES:
                continue
            iou, cover = overlap_pair(box, item["bbox"])
            if iou >= 0.35 or cover >= 0.6:
                return True
        return False

    def _consistent(self, state, detection) -> bool:
        if not compatible_class(detection["class"], state["class"]):
            return False
        box = detection["bbox"]
        ratio = _area(box) / _area(state["box"])
        if ratio < 0.4 or ratio > 2.2:
            return False
        center = _center(box)
        typical = _median(state["steps"]) if state["steps"] else 0.0
        span = min(max(state["box"][2] - state["box"][0], state["box"][3] - state["box"][1]), 100.0)
        reach = max(22.0, 3.0 * typical, 0.4 * span)
        return math.hypot(center[0] - state["center"][0], center[1] - state["center"][1]) <= reach

    def _claim(self, state, detections, objects):
        best = None
        for detection in detections:
            if self._used_by_established(detection["bbox"], objects):
                continue
            if not self._consistent(state, detection):
                continue
            center = _center(detection["bbox"])
            distance = math.hypot(center[0] - state["center"][0], center[1] - state["center"][1])
            ratio = _area(detection["bbox"]) / _area(state["box"])
            score = distance + abs(math.log(max(ratio, 1e-3))) * 20.0
            if best is None or score < best[0]:
                best = (score, detection)
        return None if best is None else best[1]

    def _flow(self, gray, state):
        if self._prev_gray is None or state["points"] is None or state["propagated"] >= MAX_PROPAGATED_FRAMES:
            return None
        nxt, status, error = cv2.calcOpticalFlowPyrLK(
            self._prev_gray,
            gray,
            state["points"],
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        )
        if nxt is None or status is None:
            return None
        old = state["points"].reshape(-1, 2)
        new = nxt.reshape(-1, 2)
        ok = []
        for index, (flag, residual) in enumerate(zip(status.reshape(-1), error.reshape(-1))):
            if int(flag) != 1 or residual > MAX_FLOW_ERROR:
                continue
            shift = new[index] - old[index]
            ok.append((index, shift, new[index]))
        needed = 4 if _area(state["box"]) < 4000 else MIN_FEATURES
        if len(ok) < needed:
            return None
        dx = _median([shift[0] for _, shift, _ in ok])
        dy = _median([shift[1] for _, shift, _ in ok])
        residuals = [math.hypot(shift[0] - dx, shift[1] - dy) for _, shift, _ in ok]
        limit = max(2.5, 2.5 * _median(residuals))
        inliers = [item for item, residual in zip(ok, residuals) if residual <= limit]
        if len(inliers) < needed or len(inliers) / len(ok) < MIN_INLIER_FRACTION:
            return None
        dx = _median([shift[0] for _, shift, _ in inliers])
        dy = _median([shift[1] for _, shift, _ in inliers])
        move = math.hypot(dx, dy)
        typical = _median(state["steps"]) if state["steps"] else 0.0
        width = state["box"][2] - state["box"][0]
        height = state["box"][3] - state["box"][1]
        bound = max(12.0, 2.4 * typical)
        if move > bound:
            return None
        old_in = np.array([old[index] for index, _, _ in inliers])
        new_in = np.array([point for _, _, point in inliers])
        old_spread = _median(np.hypot(old_in[:, 0] - np.median(old_in[:, 0]), old_in[:, 1] - np.median(old_in[:, 1])))
        new_spread = _median(np.hypot(new_in[:, 0] - np.median(new_in[:, 0]), new_in[:, 1] - np.median(new_in[:, 1])))
        if old_spread > 1 and not 0.7 <= new_spread / old_spread <= 1.4:
            return None
        box = [state["box"][0] + dx, state["box"][1] + dy, state["box"][2] + dx, state["box"][3] + dy]
        inside_w = max(0.0, min(box[2], self.width) - max(box[0], 0))
        inside_h = max(0.0, min(box[3], self.height) - max(box[1], 0))
        if inside_w * inside_h < 0.4 * _area(state["box"]):
            return None
        return box, new_in.reshape(-1, 1, 2), len(inliers) / len(ok)

    def extend(self, gray, objects, detections, frame_index, timestamp, camera, store) -> list[dict]:
        """Add observations for established vehicles missing from this frame's detector tracks.

        Points were measured on the previous frame. Detector updates happen after
        that search so a gap uses the last real vehicle features.
        """
        kept = []
        for item in objects:
            state = self._tracks.get(item["track_id"])
            if (
                state
                and not state.get("closed")
                and self._eligible(state)
                and not self._consistent(state, {"class": item["class"], "bbox": item["bbox"]})
            ):
                continue
            kept.append(item)
        objects[:] = kept
        present = {item["track_id"] for item in objects}
        added = []
        claimed_young = set()
        for track_id, state in list(self._tracks.items()):
            if track_id in present or state.get("closed") or not self._eligible(state):
                continue
            if frame_index - state.get("last_frame", frame_index - 1) != 1:
                state["closed"] = True
                continue
            detection = self._claim(state, detections, objects)
            if detection is not None:
                box = [float(value) for value in detection["bbox"]]
                self._note_step(state, box)
                state["detector_frames"] += 1
                state["propagated"] = 0
                state["reliability"] = min(1.0, 0.55 + 0.45 * detection["confidence"])
                self._seed(gray, state, box)
                state["last_frame"] = frame_index
                added.append(
                    self._object(
                        camera, frame_index, timestamp, track_id, state, box,
                        "detector", detection["confidence"], store,
                    )
                )
                for item in objects:
                    young = self._tracks.get(item["track_id"])
                    if young is None or young["detector_frames"] >= MIN_DETECTOR_FRAMES:
                        continue
                    iou, cover = overlap_pair(box, item["bbox"])
                    if iou >= 0.5 or cover >= 0.7:
                        claimed_young.add(item["track_id"])
                continue
            flowed = self._flow(gray, state)
            if flowed is None:
                state["closed"] = True
                state["points"] = None
                continue
            box, points, inlier_fraction = flowed
            state["propagated"] += 1
            state["reliability"] = max(0.05, state["reliability"] * 0.82 * inlier_fraction)
            if state["reliability"] < 0.15:
                state["closed"] = True
                state["points"] = None
                continue
            center = _center(box)
            step = math.hypot(center[0] - state["center"][0], center[1] - state["center"][1])
            state["steps"] = (state["steps"] + [step])[-5:]
            state["center"] = center
            state["box"] = [float(value) for value in box]
            state["points"] = points
            state["last_frame"] = frame_index
            added.append(
                self._object(
                    camera, frame_index, timestamp, track_id, state, box,
                    "propagated", None, store,
                )
            )

        if claimed_young:
            objects[:] = [item for item in objects if item["track_id"] not in claimed_young]
            for track_id in claimed_young:
                self._tracks.pop(track_id, None)

        for item in list(objects):
            state = self._tracks.get(item["track_id"])
            confidence = float(item["confidence"] if item["confidence"] is not None else 0.5)
            if state is None or state.get("closed"):
                state = self._fresh(item["class"], item["bbox"], confidence)
                self._tracks[item["track_id"]] = state
            else:
                state["propagated"] = 0
                state["closed"] = False
                state["reliability"] = min(1.0, 0.55 + 0.45 * confidence)
                self._note_step(state, item["bbox"])
            state["detector_frames"] += 1
            state["class"] = item["class"]
            state["last_frame"] = frame_index
            self._seed(gray, state, item["bbox"])
            item["observation"] = "detector"
            item["reliability"] = round(state["reliability"], 2)
            item["raw_bbox"] = list(item["bbox"])

        self._prev_gray = gray
        return added

    def _object(self, camera, frame_index, timestamp, track_id, state, box, observation, confidence, store):
        x1 = int(round(box[0]))
        y1 = int(round(box[1]))
        x2 = int(round(box[2]))
        y2 = int(round(box[3]))
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        store.update(track_id, (cx, cy))
        history = [[point[0], point[1]] for point in store.points(track_id)]
        return {
            "camera": camera,
            "frame": frame_index,
            "timestamp": timestamp,
            "track_id": track_id,
            "class": state["class"],
            "confidence": None if confidence is None else round(float(confidence), 2),
            "bbox": [x1, y1, x2, y2],
            "raw_bbox": None if observation == "propagated" else [x1, y1, x2, y2],
            "center_x": cx,
            "center_y": cy,
            "center": [cx, cy],
            "center_history": history,
            "width": max(0, x2 - x1),
            "height": max(0, y2 - y1),
            "observation": observation,
            "reliability": round(state["reliability"], 2),
        }
