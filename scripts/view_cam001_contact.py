#!/usr/bin/env python3
"""CAM-001 multi-metric contact viewer.

Every calculation uses the video's own frame times. Playback speed, including
slow motion, only changes how long each frame stays on screen.

Controls: SPACE pause/play, D/Right one frame forward, A/Left one frame back,
R restart, S slow-motion view, Q quit.
"""

import json
import math
import sys
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parent.parent
VIDEO = REPO / "outputs" / "tracking" / "cam_001_tracked.mp4"
SOURCE = REPO / "data" / "cameras" / "cam_001.mp4"
TRACKS = REPO / "outputs" / "tracking" / "tracks.json"
WINDOW = "CAM-001 multi-metric"
GREEN = (70, 190, 60)
RED = (0, 0, 255)
TEXT = (255, 255, 255)
BODY_INSET = 0.15
BODY_GAP = 2.0
APPROACH_DROP_PX = 40.0
SLOW_VIEW_MS = 160


def edge_gaps(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    if ax2 < bx1:
        gap_x = bx1 - ax2
    elif bx2 < ax1:
        gap_x = ax1 - bx2
    else:
        gap_x = 0.0
    if ay2 < by1:
        gap_y = by1 - ay2
    elif by2 < ay1:
        gap_y = ay1 - by2
    else:
        gap_y = 0.0
    return float(gap_x), float(gap_y)


def edge_distance(first, second) -> float:
    gap_x, gap_y = edge_gaps(first, second)
    return math.hypot(gap_x, gap_y)


def inset_box(box, fraction=BODY_INSET):
    x1, y1, x2, y2 = box
    pad_x = (x2 - x1) * fraction
    pad_y = (y2 - y1) * fraction
    if (x2 - x1) - 2 * pad_x < 4 or (y2 - y1) - 2 * pad_y < 4:
        return list(box)
    return [x1 + pad_x, y1 + pad_y, x2 - pad_x, y2 - pad_y]


def bbox_iou(first, second) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return 0.0 if union <= 0 else inter / union


def bodies_touch(first, second) -> bool:
    gap_x, gap_y = edge_gaps(inset_box(first), inset_box(second))
    return gap_x <= BODY_GAP and gap_y <= BODY_GAP


def load_tracks():
    record = json.loads(TRACKS.read_text())["CAM-001"]
    frames = {}
    for frame in record["frames"]:
        frames[frame["frame"]] = {item["track_id"]: item for item in frame["objects"]}
    return frames, float(record["fps"])


def history(frames, track_id, frame_index, count):
    found = []
    for index in range(frame_index - count + 1, frame_index + 1):
        item = frames.get(index, {}).get(track_id)
        if item is not None:
            found.append(item)
    return found


def velocity(samples):
    if len(samples) < 2:
        return None
    dx = []
    dy = []
    for earlier, later in zip(samples, samples[1:]):
        dt = later["timestamp"] - earlier["timestamp"]
        if dt <= 0:
            continue
        dx.append((later["center_x"] - earlier["center_x"]) / dt)
        dy.append((later["center_y"] - earlier["center_y"]) / dt)
    if not dx:
        return None
    return (sum(dx) / len(dx), sum(dy) / len(dy))


def project(origin_a, vector_a, origin_b, vector_b):
    rx = origin_b[0] - origin_a[0]
    ry = origin_b[1] - origin_a[1]
    rvx = vector_b[0] - vector_a[0]
    rvy = vector_b[1] - vector_a[1]
    scale = rvx * rvx + rvy * rvy
    if scale < 1:
        return None
    time_s = -((rx * rvx) + (ry * rvy)) / scale
    miss = math.hypot(rx + rvx * time_s, ry + rvy * time_s)
    return time_s, miss


def shared_frames(frames, first_id, second_id):
    return [index for index in sorted(frames) if first_id in frames[index] and second_id in frames[index]]


def items_in_window(frames, track_id, start_time, end_time):
    found = []
    for index in sorted(frames):
        item = frames[index].get(track_id)
        if item is not None and start_time <= item["timestamp"] <= end_time:
            found.append(item)
    return found


def median_speed(samples):
    speeds = []
    for earlier, later in zip(samples, samples[1:]):
        dt = later["timestamp"] - earlier["timestamp"]
        if dt <= 0:
            continue
        dx = later["center_x"] - earlier["center_x"]
        dy = later["center_y"] - earlier["center_y"]
        speeds.append(math.hypot(dx, dy) / dt)
    if not speeds:
        return None
    speeds.sort()
    return speeds[len(speeds) // 2]


def heading_degrees(vector, speed_floor=40.0):
    if vector is None or math.hypot(*vector) < speed_floor:
        return None
    return math.degrees(math.atan2(vector[1], vector[0]))


def turn_degrees(before, after):
    if before is None or after is None:
        return None
    delta = abs(before - after) % 360.0
    return min(delta, 360.0 - delta)


def closing_stats(frames, first_id, second_id, frame_index):
    sample_a = history(frames, first_id, frame_index, 10)
    sample_b = history(frames, second_id, frame_index, 10)
    count = min(len(sample_a), len(sample_b))
    if count < 5:
        return None
    sample_a = sample_a[-count:]
    sample_b = sample_b[-count:]
    centers = []
    gaps = []
    for left, right in zip(sample_a, sample_b):
        centers.append(math.hypot(left["center_x"] - right["center_x"], left["center_y"] - right["center_y"]))
        gaps.append(edge_distance(left["bbox"], right["bbox"]))
    drop = centers[0] - centers[-1]
    elapsed = sample_a[-1]["timestamp"] - sample_a[0]["timestamp"]
    center_speed = drop / elapsed if elapsed > 0 else 0.0
    edge_speed = (gaps[0] - gaps[-1]) / elapsed if elapsed > 0 else 0.0
    closing_steps = sum(1 for earlier, later in zip(centers, centers[1:]) if later < earlier - 1)
    steps = max(1, len(centers) - 1)
    vector_a = velocity(sample_a)
    vector_b = velocity(sample_b)
    projected = None
    if vector_a and vector_b:
        projected = project(
            (sample_a[-1]["center_x"], sample_a[-1]["center_y"]),
            vector_a,
            (sample_b[-1]["center_x"], sample_b[-1]["center_y"]),
            vector_b,
        )
    box_a = sample_a[-1]["bbox"]
    box_b = sample_b[-1]["bbox"]
    body_widths = [
        0.7 * (box_a[2] - box_a[0]),
        0.7 * (box_b[2] - box_b[0]),
        0.7 * (box_a[3] - box_a[1]),
        0.7 * (box_b[3] - box_b[1]),
    ]
    smaller_body = max(8.0, min(body_widths))
    rel_vx = (vector_b[0] - vector_a[0]) if vector_a and vector_b else 0.0
    rel_vy = (vector_b[1] - vector_a[1]) if vector_a and vector_b else 0.0
    offset_x = sample_b[-1]["center_x"] - sample_a[-1]["center_x"]
    offset_y = sample_b[-1]["center_y"] - sample_a[-1]["center_y"]
    offset = math.hypot(offset_x, offset_y)
    radial_closing = 0.0 if offset < 1 else -((rel_vx * offset_x) + (rel_vy * offset_y)) / offset
    paths_meet = (
        projected is not None
        and 0.0 < projected[0] < 1.0
        and projected[1] <= 0.5 * smaller_body
    )
    approaching = drop >= APPROACH_DROP_PX and center_speed >= 40 and closing_steps >= math.ceil(0.6 * steps)
    return {
        "approaching": approaching,
        "closing_speed_px_s": center_speed,
        "edge_closing_px_s": edge_speed,
        "radial_closing_px_s": radial_closing,
        "center_start_px": centers[0],
        "center_end_px": centers[-1],
        "edge_start_px": gaps[0],
        "edge_end_px": gaps[-1],
        "paths_meet": paths_meet,
        "projected_time_s": None if projected is None else projected[0],
        "projected_miss_px": None if projected is None else projected[1],
        "vector_a": vector_a,
        "vector_b": vector_b,
    }


def speed_stats(samples):
    speeds = []
    for earlier, later in zip(samples, samples[1:]):
        dt = later["timestamp"] - earlier["timestamp"]
        if dt <= 0:
            continue
        dx = later["center_x"] - earlier["center_x"]
        dy = later["center_y"] - earlier["center_y"]
        speeds.append(math.hypot(dx, dy) / dt)
    if len(speeds) < 3:
        return None, None
    speeds.sort()
    middle = speeds[len(speeds) // 2]
    quartile_span = speeds[(3 * len(speeds)) // 4] - speeds[len(speeds) // 4]
    return middle, quartile_span


def speed_change(frames, track_id, when):
    before = items_in_window(frames, track_id, when - 0.55, when - 0.12)
    earlier = items_in_window(frames, track_id, when - 1.15, when - 0.55)
    after = items_in_window(frames, track_id, when + 0.08, when + 0.5)
    pre_speed, pre_span = speed_stats(before)
    prior_speed, _prior_span = speed_stats(earlier)
    post_speed, post_span = speed_stats(after)
    pre_heading = heading_degrees(velocity(before))
    post_heading = heading_degrees(velocity(after))
    turn = turn_degrees(pre_heading, post_heading)
    prior_drop = 0.0 if pre_speed is None or prior_speed is None else prior_speed - pre_speed
    drop = None if pre_speed is None or post_speed is None else pre_speed - post_speed
    speed_stable = pre_span is not None and pre_speed and pre_span <= 0.45 * pre_speed
    abrupt_speed = (
        drop is not None
        and speed_stable
        and pre_speed >= 80
        and drop >= 80
        and post_speed <= 0.55 * pre_speed
        and drop >= prior_drop + 40
        and post_speed < 180
    )
    abrupt_turn = turn is not None and turn >= 35 and pre_speed is not None and pre_speed >= 40 and post_speed is not None and post_speed >= 40
    return {
        "pre_speed": pre_speed,
        "post_speed": post_speed,
        "drop": drop,
        "pre_span": pre_span,
        "abrupt_speed": abrupt_speed,
        "speed_stable": speed_stable,
        "pre_heading": pre_heading,
        "post_heading": post_heading,
        "turn": turn,
        "abrupt_turn": abrupt_turn,
    }


def disrupted(frames, track_id, when):
    nearby = items_in_window(frames, track_id, when - 0.2, when + 0.25)
    if len(nearby) < 2:
        return True
    confidences = [item["confidence"] for item in nearby]
    areas = [(item["bbox"][2] - item["bbox"][0]) * (item["bbox"][3] - item["bbox"][1]) for item in nearby]
    jumped = any(later > 1.7 * earlier or earlier > 1.7 * later for earlier, later in zip(areas, areas[1:]) if earlier > 1)
    present_before = any(
        track_id in frames.get(index, {}) and abs(frames[index][track_id]["timestamp"] - when) < 0.15 and frames[index][track_id]["timestamp"] <= when
        for index in frames
    )
    missing_after = 0
    for index in sorted(frames):
        item_time = None
        if frames[index]:
            item_time = next(iter(frames[index].values()))["timestamp"]
        if item_time is None or item_time <= when or item_time > when + 0.4:
            continue
        if track_id not in frames[index]:
            missing_after += 1
    lost = present_before and missing_after >= 3
    return (max(confidences) - min(confidences) >= 0.25) or jumped or lost


def pair_rows(frames):
    ids = sorted({track_id for frame in frames.values() for track_id in frame})
    rows = []
    for left in range(len(ids)):
        for right in range(left + 1, len(ids)):
            first_id, second_id = ids[left], ids[right]
            together = shared_frames(frames, first_id, second_id)
            if len(together) < 8:
                continue
            closest = min(together, key=lambda index: (
                edge_distance(inset_box(frames[index][first_id]["bbox"]), inset_box(frames[index][second_id]["bbox"])),
                edge_distance(frames[index][first_id]["bbox"], frames[index][second_id]["bbox"]),
            ))
            item_a = frames[closest][first_id]
            item_b = frames[closest][second_id]
            bbox_gap = edge_gaps(item_a["bbox"], item_b["bbox"])
            body_gap = edge_gaps(inset_box(item_a["bbox"]), inset_box(item_b["bbox"]))
            if math.hypot(*bbox_gap) > 90 and math.hypot(*body_gap) > 90:
                continue
            motion = closing_stats(frames, first_id, second_id, closest)
            if motion is None:
                continue
            response_a = speed_change(frames, first_id, item_a["timestamp"])
            response_b = speed_change(frames, second_id, item_a["timestamp"])
            sync = (response_a["abrupt_speed"] or response_a["abrupt_turn"]) and (
                response_b["abrupt_speed"] or response_b["abrupt_turn"]
            )
            track_break = disrupted(frames, first_id, item_a["timestamp"]) or disrupted(frames, second_id, item_a["timestamp"])
            body_touch = body_gap[0] <= BODY_GAP and body_gap[1] <= BODY_GAP
            reasons = []
            if not motion["approaching"]:
                reasons.append("centers do not keep closing into the interaction")
            if not motion["paths_meet"]:
                reasons.append("projected paths miss")
            if not body_touch:
                reasons.append("inset vehicle bodies never meet")
            if not (response_a["abrupt_speed"] or response_b["abrupt_speed"] or response_a["abrupt_turn"] or response_b["abrupt_turn"]):
                reasons.append("no abrupt speed or heading change against the pre-contact trend")
            if not sync:
                reasons.append("the two vehicles do not respond together")
            rows.append(
                {
                    "pair": (first_id, second_id),
                    "frame": closest,
                    "time": item_a["timestamp"],
                    "approach": motion["approaching"],
                    "closing_speed_px_s": motion["closing_speed_px_s"],
                    "edge_closing_px_s": motion["edge_closing_px_s"],
                    "radial_closing_px_s": motion["radial_closing_px_s"],
                    "center_start_px": motion["center_start_px"],
                    "center_end_px": motion["center_end_px"],
                    "paths_meet": motion["paths_meet"],
                    "projected_time_s": motion["projected_time_s"],
                    "projected_miss_px": motion["projected_miss_px"],
                    "bbox_gap": bbox_gap,
                    "bbox_iou": bbox_iou(item_a["bbox"], item_b["bbox"]),
                    "body_gap": body_gap,
                    "body_touch": body_touch,
                    "speed_a": response_a,
                    "speed_b": response_b,
                    "synchronized": sync,
                    "disruption": track_break,
                    "why": "; ".join(reasons) if reasons else "all stages present",
                    "_boxes": (item_a["bbox"], item_b["bbox"]),
                }
            )
    rows.sort(key=lambda row: (not row["approach"], math.hypot(*row["body_gap"]), row["time"]))
    serious = [
        row
        for row in rows
        if row["approach"] or (row["bbox_iou"] > 0.005 and math.hypot(*row["body_gap"]) < 40)
    ]
    return serious


def causal_timeline(frames):
    """State at each frame uses only that frame and earlier ones."""
    last = max(frames)
    phase = {}
    contact = {}
    surfaced = {}
    timeline = []
    for frame_index in range(last + 1):
        current = frames.get(frame_index, {})
        ids = sorted(current)
        nearest = None
        for left in range(len(ids)):
            for right in range(left + 1, len(ids)):
                first_id, second_id = ids[left], ids[right]
                key = (first_id, second_id)
                stats = closing_stats(frames, first_id, second_id, frame_index)
                if stats is None:
                    continue
                body_gap = edge_gaps(inset_box(current[first_id]["bbox"]), inset_box(current[second_id]["bbox"]))
                body_touch = body_gap[0] <= BODY_GAP and body_gap[1] <= BODY_GAP
                state = phase.get(key, "normal")
                if stats["approaching"] and state == "normal":
                    state = "approaching"
                if state == "approaching" and stats["paths_meet"] and math.hypot(*body_gap) < 30:
                    state = "candidate"
                if state in {"approaching", "candidate"} and body_touch and stats["paths_meet"]:
                    state = "physical"
                    contact[key] = frame_index
                if state == "physical" and frame_index > contact[key]:
                    waited = current[first_id]["timestamp"] - frames[contact[key]][first_id]["timestamp"]
                    if waited >= 0.12:
                        response_a = speed_change(frames, first_id, frames[contact[key]][first_id]["timestamp"])
                        response_b = speed_change(frames, second_id, frames[contact[key]][first_id]["timestamp"])
                        if (
                            waited <= 0.5
                            and (response_a["abrupt_speed"] or response_b["abrupt_speed"] or response_a["abrupt_turn"] or response_b["abrupt_turn"])
                        ):
                            state = "surfaced"
                            surfaced[key] = frame_index
                phase[key] = state
                score = {"normal": 0, "approaching": 1, "candidate": 2, "physical": 3, "surfaced": 4}[state]
                gap = math.hypot(*body_gap)
                if nearest is None or (score, -gap) > (nearest[0], -nearest[1]):
                    nearest = (score, gap, key, state, stats, body_gap, body_touch)
        red_ids = set()
        red_since = None
        for key, start in surfaced.items():
            if frame_index >= start:
                red_ids.update(key)
                red_since = start if red_since is None else min(red_since, start)
        status = {
            "pair": None if nearest is None or nearest[0] == 0 else nearest[2],
            "approach": "no" if nearest is None or nearest[0] == 0 else ("yes" if nearest[3] != "normal" else "no"),
            "proximity": "none",
            "response": "none",
            "surfaced": bool(red_ids),
            "red_ids": red_ids,
            "body_gap": None,
            "bbox_gap": None,
        }
        if nearest is not None and nearest[0] > 0:
            item_a = current[nearest[2][0]]
            item_b = current[nearest[2][1]]
            status["proximity"] = "contact" if nearest[6] else f"body gap {math.hypot(*nearest[5]):.0f}px"
            status["bbox_gap"] = edge_gaps(item_a["bbox"], item_b["bbox"])
            status["body_gap"] = nearest[5]
            if nearest[3] in {"physical", "surfaced"}:
                status["response"] = "yes" if nearest[3] == "surfaced" else "pending"
        timeline.append(status)
    first_surface = None
    if surfaced:
        key, start = min(surfaced.items(), key=lambda item: item[1])
        first_surface = {"pair": key, "frame": start, "time": frames[start][key[0]]["timestamp"]}
    return timeline, first_surface


def format_speed(change):
    if change["drop"] is None:
        return "not enough samples"
    if change["abrupt_speed"]:
        flag = "abrupt"
    elif not change["speed_stable"]:
        flag = "not abrupt, speed already swinging before the interaction"
    else:
        flag = "not abrupt"
    return f"{change['drop']:+.0f} px/s ({change['pre_speed']:.0f} -> {change['post_speed']:.0f}, {flag})"


def format_heading(change):
    if change["turn"] is None:
        return "heading unstable or vehicle too slow"
    flag = "abrupt" if change["abrupt_turn"] else "small"
    pre = "n/a" if change["pre_heading"] is None else f"{change['pre_heading']:.0f} deg"
    post = "n/a" if change["post_heading"] is None else f"{change['post_heading']:.0f} deg"
    return f"{pre} -> {post}, {change['turn']:.0f} deg ({flag})"


def report_lines(rows):
    lines = []
    if not rows:
        lines.append("No serious candidate pair reached a 90 px edge gap.")
        return lines
    for row in rows:
        first_id, second_id = row["pair"]
        miss = "n/a" if row["projected_miss_px"] is None else f"{row['projected_miss_px']:.0f} px"
        arrival = "n/a" if row["projected_time_s"] is None else f"{row['projected_time_s']:.2f} s"
        mask = row.get("mask")
        mask_text = "not measured" if mask is None else mask
        lines.extend(
            [
                f"PAIR {first_id} / {second_id}",
                f"APPROACH: {'yes' if row['approach'] else 'no'}    closing speed {row['closing_speed_px_s']:.0f} px/s    edge closing {row['edge_closing_px_s']:.0f} px/s    radial {row['radial_closing_px_s']:.0f} px/s",
                f"TRAJECTORY CONVERGENCE: {'yes' if row['paths_meet'] else 'no'}    projected miss {miss}    time to closest {arrival}",
                f"PHYSICAL PROXIMITY: bbox gap {row['bbox_gap'][0]:.0f},{row['bbox_gap'][1]:.0f} px    bbox IoU {row['bbox_iou']:.3f}    body gap {row['body_gap'][0]:.0f},{row['body_gap'][1]:.0f} px    mask {mask_text}",
                f"TIMING: frame {row['frame']}    {row['time']:.3f} s",
                f"SPEED RESPONSE {first_id}: {format_speed(row['speed_a'])}",
                f"SPEED RESPONSE {second_id}: {format_speed(row['speed_b'])}",
                f"DIRECTION RESPONSE {first_id}: {format_heading(row['speed_a'])}",
                f"DIRECTION RESPONSE {second_id}: {format_heading(row['speed_b'])}",
                f"SYNCHRONIZED RESPONSE: {'yes' if row['synchronized'] else 'no'}",
                f"TRACK DISRUPTION: {'yes' if row['disruption'] else 'no'}",
                f"WHY: {row['why']}",
                "",
            ]
        )
    return lines


def attach_masks(rows):
    needed = {}
    for row in rows:
        if row["approach"] or row["bbox_iou"] > 0 or math.hypot(*row["bbox_gap"]) < 60:
            needed.setdefault(row["frame"], []).append(row)
    if not needed:
        return
    weights = REPO / "yolo11n-seg.pt"
    if not weights.is_file() or not SOURCE.is_file():
        for row in rows:
            row["mask"] = "segmentation unavailable"
        return
    from ultralytics import YOLO

    model = YOLO(str(weights))
    capture = cv2.VideoCapture(str(SOURCE))
    for frame_index, group in needed.items():
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, image = capture.read()
        if not ok:
            continue
        result = model.predict(image, conf=0.15, imgsz=640, verbose=False)[0]
        masks = []
        if result.masks is not None:
            raw = result.masks.data.cpu().numpy()
            height, width = image.shape[:2]
            for index in range(len(result.boxes)):
                box = result.boxes.xyxy[index].cpu().numpy().tolist()
                mask = cv2.resize(raw[index], (width, height), interpolation=cv2.INTER_NEAREST) > 0.5
                masks.append((box, mask))
        for row in group:
            left = frames_box(row, 0)
            right = frames_box(row, 1)
            mask_a = match_mask(masks, left)
            mask_b = match_mask(masks, right)
            if mask_a is None or mask_b is None:
                missing = []
                if mask_a is None:
                    missing.append(str(row["pair"][0]))
                if mask_b is None:
                    missing.append(str(row["pair"][1]))
                row["mask"] = "no mask for track " + ",".join(missing)
                continue
            overlap = int((mask_a & mask_b).sum())
            distance = mask_distance(mask_a, mask_b)
            contact = overlap > 0 or distance <= 2
            row["mask"] = f"gap {distance:.0f} px    overlap {overlap} px    contact {'yes' if contact else 'no'}"
    capture.release()


def frames_box(row, which):
    # Filled by the caller through a closure stored on the row.
    return row["_boxes"][which]


def match_mask(masks, box):
    best = None
    best_iou = 0.1
    for other, mask in masks:
        score = bbox_iou(box, other)
        if score > best_iou:
            best_iou = score
            best = mask
    return best


def mask_distance(first, second):
    if first.shape != second.shape:
        return float("inf")
    if not first.any() or not second.any():
        return float("inf")
    if (first & second).any():
        return 0.0
    distance = cv2.distanceTransform((~first).astype("uint8"), cv2.DIST_L2, 3)
    ys, xs = second.nonzero()
    if len(xs) > 4000:
        step = len(xs) // 4000
        xs = xs[::step]
        ys = ys[::step]
    return float(distance[ys, xs].min())


def read_frame(capture, frame_index):
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok or frame is None:
        raise SystemExit(f"OpenCV could not read frame {frame_index}")
    return frame


def draw_box(frame, item, color):
    x1, y1, x2, y2 = [int(value) for value in item["bbox"]]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        frame,
        f"#{item['track_id']} {item['confidence']:.2f}",
        (x1, max(18, y1 - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
        cv2.LINE_AA,
    )


def main() -> None:
    video = SOURCE if SOURCE.is_file() else VIDEO
    if not video.is_file():
        raise SystemExit(f"Missing {VIDEO}")
    frames, fps = load_tracks()
    rows = pair_rows(frames)
    attach_masks(rows)
    timeline, first_surface = causal_timeline(frames)
    print("\n".join(report_lines(rows)))
    if first_surface is None:
        print("SELECTED PAIR: none")
        print("Physical interaction and surfaced collision: none")
    else:
        print(
            f"SELECTED PAIR: {first_surface['pair'][0]} / {first_surface['pair'][1]}  "
            f"surfaced at frame {first_surface['frame']}  t {first_surface['time']:.3f}s"
        )
    if "--report-only" in sys.argv:
        return
    last = max(frames)
    cursor = 0
    paused = False
    slow = False
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise SystemExit(f"OpenCV could not open {video}")
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 1100, 620)
    display = read_frame(capture, 0)
    cv2.imshow(WINDOW, display)
    cv2.waitKey(1)
    normal_delay = max(1, int(round(1000 / fps)))
    while True:
        status = timeline[cursor]
        participants = status["red_ids"]
        for item in frames.get(cursor, {}).values():
            draw_box(display, item, RED if item["track_id"] in participants else GREEN)
        state = "PAUSED" if paused else ("SLOW" if slow else "PLAYING")
        pair = status["pair"]
        pair_text = "none" if pair is None else f"#{pair[0]} / #{pair[1]}"
        lines = [
            f"frame {cursor}    t {cursor / fps:.3f}s    {state}",
            f"candidate pair {pair_text}",
            f"approach {status['approach']}",
            f"physical proximity {status['proximity']}",
            f"response {status['response']}",
            f"collision surfaced {'YES' if status['surfaced'] else 'NO'}",
        ]
        y_pos = 28
        for line in lines:
            cv2.putText(display, line, (16, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(display, line, (16, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT, 1, cv2.LINE_AA)
            y_pos += 26
        cv2.imshow(WINDOW, display)
        if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break
        delay = SLOW_VIEW_MS if slow else normal_delay
        key = cv2.waitKeyEx(delay)
        if key in (ord("q"), ord("Q")):
            break
        if key == ord(" "):
            paused = not paused
        elif key in (ord("s"), ord("S")):
            slow = not slow
        elif key in (ord("r"), ord("R")):
            cursor = 0
            paused = True
            display = read_frame(capture, cursor)
        elif key in (81, 2, 63234, ord("a"), ord("A")):
            cursor = max(0, cursor - 1)
            paused = True
            display = read_frame(capture, cursor)
        elif key in (83, 3, 63235, ord("d"), ord("D")):
            cursor = min(last, cursor + 1)
            paused = True
            display = read_frame(capture, cursor)
        elif not paused and key < 0:
            if cursor >= last:
                cursor = 0
                display = read_frame(capture, cursor)
            else:
                ok, nxt = capture.read()
                cursor += 1
                if ok and nxt is not None:
                    display = nxt
                else:
                    display = read_frame(capture, cursor)
    capture.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
