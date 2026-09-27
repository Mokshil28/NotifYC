#!/usr/bin/env python3
"""Image-space motion of Phase 3 tracks. Not a collision decision.

Raw centers and boxes come from outputs/tracking/tracks.json. A short causal
mean and a pixel deadband reduce detector jitter. Those derived values are
stored beside the raw centers. Phase 3 files are not modified.
"""

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKS_PATH = REPO_ROOT / "outputs" / "tracking" / "tracks.json"
OUTPUT_PATH = REPO_ROOT / "outputs" / "motion" / "motion_analysis.json"

# Same constants for every camera.
FILTER_WINDOW = 3
MAX_GAP_FRAMES = 2
DEADBAND_FLOOR_PX = 2.0
DEADBAND_BOX_FRACTION = 0.02
STATIONARY_SAMPLES = 5
STATIONARY_SPEED_PX_S = 1.0
ABRUPT_SCORE = 2.5
ABRUPT_SPEED_CHANGE_PX_S = 200.0
ABRUPT_HISTORY = 3
HEADING_SAMPLES = 3
HEADING_LOOKBACK = 8
NEIGHBORHOOD_DIAGONALS = 3.0
CLOSE_NORMALIZED_SEPARATION = 1.25
PROBE_SECONDS = 0.5
PARALLEL_DEGREES = 30.0
CONVERGE_RATIO = 0.85
DIVERGE_RATIO = 1.15

FORBIDDEN_WORDS = ("collision", "crash", "accident", "severity", "injury")


def load_tracks() -> dict:
    if not TRACKS_PATH.is_file():
        raise SystemExit(f"Tracking data not found: {TRACKS_PATH}")
    return json.loads(TRACKS_PATH.read_text())


def method_notes() -> dict:
    return {
        "coordinates": (
            "raw center_x and center_y stay on each sample; when a stabilized center exists it is the motion input"
        ),
        "units": "velocities are pixels per second, not road speed",
        "filtered_center": (
            f"causal mean of up to {FILTER_WINDOW} raw centers; "
            f"a gap longer than {MAX_GAP_FRAMES} frames clears the window"
        ),
        "displacement_deadband_px": (
            f"max({DEADBAND_FLOOR_PX}, {DEADBAND_BOX_FRACTION} * max(width, height)); "
            "smaller steps are stored as zero displacement"
        ),
        "velocity": "vx = dx / dt and vy = dy / dt from deadbanded filtered displacement and the timestamp gap",
        "direction_angle": "degrees, atan2(dy, dx); null when displacement is inside the deadband",
        "stationary": (
            f"true only when the last {STATIONARY_SAMPLES} valid speeds are all below "
            f"{STATIONARY_SPEED_PX_S} px/s"
        ),
        "motion_change": (
            "delta speed in px/s between successive valid samples; "
            f"score is abs(delta speed) / max(median recent abs delta, 80); "
            f"abrupt when at least {ABRUPT_HISTORY} prior deltas exist, "
            f"score >= {ABRUPT_SCORE}, and abs(delta speed) >= {ABRUPT_SPEED_CHANGE_PX_S}"
        ),
        "pair_gate": (
            f"center separation <= {NEIGHBORHOOD_DIAGONALS} * mean bounding-box diagonal"
        ),
        "normalized_separation": "center separation divided by the mean of the two box diagonals",
        "trajectory_relationship": (
            f"constant-velocity probe of {PROBE_SECONDS} s in image space; "
            f"roughly_parallel when the velocity angle is under {PARALLEL_DEGREES} degrees "
            f"and the predicted separation stays within {CONVERGE_RATIO}-{DIVERGE_RATIO}; "
            "converging or diverging from that predicted separation; otherwise uncertain. "
            "This is not a forecast that the vehicles will meet"
        ),
        "close_interaction": (
            f"normalized separation < {CLOSE_NORMALIZED_SEPARATION}; not a contact decision"
        ),
        "bbox_iou": "intersection over union of the raw boxes; overlap is not contact",
    }


def bbox_iou(first, second) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def round_or_none(value, digits: int):
    if value is None:
        return None
    return round(float(value), digits)


def angle_between(first, second) -> float:
    a = math.hypot(first[0], first[1])
    b = math.hypot(second[0], second[1])
    if a == 0 or b == 0:
        return 180.0
    cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / (a * b)))
    return math.degrees(math.acos(cosine))


def group_observations(record: dict) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for frame in record["frames"]:
        seen = set()
        for item in frame["objects"]:
            track_id = int(item["track_id"])
            if track_id in seen:
                raise SystemExit(f"Track {track_id} appears twice in frame {item['frame']}")
            seen.add(track_id)
            grouped[track_id].append(item)
    for observations in grouped.values():
        observations.sort(key=lambda item: item["frame"])
        frames = [item["frame"] for item in observations]
        times = [item["timestamp"] for item in observations]
        if frames != sorted(frames) or times != sorted(times):
            raise SystemExit("Track observations are not chronological")
    return grouped


def analyze_track(observations: list[dict]) -> list[dict]:
    window: list[tuple[float, float]] = []
    filtered_prev = None
    previous_frame = None
    previous_time = None
    previous_velocity = None
    previous_speed = None
    recent_speeds: list[float] = []
    recent_deltas: list[float] = []
    recent_headings: list[tuple[float, float]] = []
    samples = []

    for item in observations:
        raw = (float(item["center_x"]), float(item["center_y"]))
        if item.get("stabilized_center_x") is not None:
            measured = (float(item["stabilized_center_x"]), float(item["stabilized_center_y"]))
            box_w = float(item.get("stabilized_width", item["width"]))
            box_h = float(item.get("stabilized_height", item["height"]))
        else:
            measured = raw
            box_w = float(item["width"])
            box_h = float(item["height"])
        frame = int(item["frame"])
        timestamp = float(item["timestamp"])
        gap = None if previous_frame is None else frame - previous_frame
        if gap is None or gap > MAX_GAP_FRAMES:
            window = [measured]
            filtered_prev = None
            previous_velocity = None
            previous_speed = None
            recent_speeds = []
            recent_deltas = []
            recent_headings = []
        else:
            window.append(measured)
            window = window[-FILTER_WINDOW:]

        filtered = (
            sum(point[0] for point in window) / len(window),
            sum(point[1] for point in window) / len(window),
        )
        dx = dy = dt = vx = vy = speed = direction = None
        if filtered_prev is not None and gap is not None and 1 <= gap <= MAX_GAP_FRAMES:
            dt = timestamp - previous_time
            dx = filtered[0] - filtered_prev[0]
            dy = filtered[1] - filtered_prev[1]
            deadband = max(DEADBAND_FLOOR_PX, DEADBAND_BOX_FRACTION * max(box_w, box_h, 1))
            if math.hypot(dx, dy) < deadband:
                dx = 0.0
                dy = 0.0
            if dt > 0:
                vx = dx / dt
                vy = dy / dt
                speed = math.hypot(vx, vy)
                if dx != 0.0 or dy != 0.0:
                    direction = math.degrees(math.atan2(dy, dx))
            else:
                dx = dy = vx = vy = speed = None

        is_stationary = False
        if speed is not None:
            recent_speeds.append(speed)
            recent_speeds = recent_speeds[-STATIONARY_SAMPLES:]
            is_stationary = len(recent_speeds) == STATIONARY_SAMPLES and all(
                value < STATIONARY_SPEED_PX_S for value in recent_speeds
            )

        delta_vx = delta_vy = delta_speed = motion_change = None
        abrupt = False
        if previous_velocity is not None and vx is not None and previous_speed is not None and speed is not None:
            delta_vx = vx - previous_velocity[0]
            delta_vy = vy - previous_velocity[1]
            delta_speed = speed - previous_speed
            scale = median(recent_deltas) if len(recent_deltas) >= ABRUPT_HISTORY else 80.0
            motion_change = abs(delta_speed) / max(scale, 80.0)
            abrupt = (
                len(recent_deltas) >= ABRUPT_HISTORY
                and motion_change >= ABRUPT_SCORE
                and abs(delta_speed) >= ABRUPT_SPEED_CHANGE_PX_S
            )
            recent_deltas.append(abs(delta_speed))
            recent_deltas = recent_deltas[-8:]

        heading = None
        if direction is not None and vx is not None:
            recent_headings.append((vx, vy))
            recent_headings = recent_headings[-HEADING_LOOKBACK:]
            directed = recent_headings[-HEADING_SAMPLES:]
            if len(directed) >= 2:
                heading = (
                    sum(vector[0] for vector in directed) / len(directed),
                    sum(vector[1] for vector in directed) / len(directed),
                )

        samples.append(
            {
                "frame": frame,
                "timestamp": round(timestamp, 3),
                "track_id": int(item["track_id"]),
                "class": item["class"],
                "raw_center": [raw[0], raw[1]],
                "filtered_center": [round(filtered[0], 2), round(filtered[1], 2)],
                "dx": round_or_none(dx, 3),
                "dy": round_or_none(dy, 3),
                "vx_px_s": round_or_none(vx, 2),
                "vy_px_s": round_or_none(vy, 2),
                "speed_px_s": round_or_none(speed, 2),
                "direction_angle": round_or_none(direction, 1),
                "is_stationary": is_stationary,
                "delta_vx_px_s": round_or_none(delta_vx, 2),
                "delta_vy_px_s": round_or_none(delta_vy, 2),
                "delta_speed_px_s": round_or_none(delta_speed, 2),
                "motion_change": round_or_none(motion_change, 3),
                "abrupt_motion_change": abrupt,
                "_heading": heading,
                "_source_center": measured,
            }
        )
        filtered_prev = filtered
        previous_frame = frame
        previous_time = timestamp
        if vx is not None:
            previous_velocity = (vx, vy)
            previous_speed = speed
    return samples


def trajectory_relationship(first, second, separation: float) -> str:
    heading_a = first["_heading"]
    heading_b = second["_heading"]
    if heading_a is None or heading_b is None or separation <= 0:
        return "uncertain"
    point_a = first["filtered_center"]
    point_b = second["filtered_center"]
    future_a = (point_a[0] + heading_a[0] * PROBE_SECONDS, point_a[1] + heading_a[1] * PROBE_SECONDS)
    future_b = (point_b[0] + heading_b[0] * PROBE_SECONDS, point_b[1] + heading_b[1] * PROBE_SECONDS)
    future = math.hypot(future_b[0] - future_a[0], future_b[1] - future_a[1])
    ratio = future / separation
    angle = angle_between(heading_a, heading_b)
    if angle <= PARALLEL_DEGREES and CONVERGE_RATIO <= ratio <= DIVERGE_RATIO:
        return "roughly_parallel"
    if ratio < CONVERGE_RATIO:
        return "converging"
    if ratio > DIVERGE_RATIO:
        return "diverging"
    return "uncertain"


def analyze_pairs(by_frame: dict[int, list[dict]], motion_at: dict[tuple[int, int], dict]) -> list[dict]:
    series: dict[tuple[int, int], list[dict]] = defaultdict(list)
    previous = {}
    for frame in sorted(by_frame):
        present = []
        for item in by_frame[frame]:
            sample = motion_at.get((int(item["track_id"]), frame))
            if sample is not None:
                present.append((item, sample))
        present.sort(key=lambda pair: pair[1]["track_id"])
        active_keys = set()
        for index, (left_item, left) in enumerate(present):
            for right_item, right in present[index + 1 :]:
                point_a = left["_source_center"]
                point_b = right["_source_center"]
                separation = math.hypot(point_b[0] - point_a[0], point_b[1] - point_a[1])
                diag_a = math.hypot(left_item["width"], left_item["height"])
                diag_b = math.hypot(right_item["width"], right_item["height"])
                scale = (diag_a + diag_b) / 2
                if scale <= 0 or separation > NEIGHBORHOOD_DIAGONALS * scale:
                    continue
                key = (left["track_id"], right["track_id"])
                active_keys.add(key)
                timestamp = float(left_item["timestamp"])
                earlier = previous.get(key)
                separation_delta = approach = None
                if earlier is not None and 1 <= frame - earlier["frame"] <= MAX_GAP_FRAMES:
                    dt = timestamp - earlier["timestamp"]
                    if dt > 0:
                        separation_delta = separation - earlier["separation"]
                        approach = (earlier["separation"] - separation) / dt
                iou = bbox_iou(left_item["bbox"], right_item["bbox"])
                normalized = separation / scale
                series[key].append(
                    {
                        "frame": frame,
                        "timestamp": round(timestamp, 3),
                        "track_a": key[0],
                        "track_b": key[1],
                        "separation_px": round(separation, 2),
                        "normalized_separation": round(normalized, 3),
                        "separation_delta": round_or_none(separation_delta, 2),
                        "relative_approach_px_s": round_or_none(approach, 2),
                        "trajectory_relationship": trajectory_relationship(left, right, separation),
                        "bbox_iou": round(iou, 4),
                        "boxes_overlapping": iou > 0,
                        "close_interaction": normalized < CLOSE_NORMALIZED_SEPARATION,
                    }
                )
                previous[key] = {"frame": frame, "timestamp": timestamp, "separation": separation}
        for key in list(previous):
            if key not in active_keys and frame - previous[key]["frame"] > MAX_GAP_FRAMES:
                previous.pop(key)
    return [
        {"track_a": key[0], "track_b": key[1], "samples": samples}
        for key, samples in sorted(series.items())
        if samples
    ]


def public_sample(sample: dict) -> dict:
    return {key: value for key, value in sample.items() if not key.startswith("_")}


def noisy_tracks(samples_by_id: dict[int, list[dict]]) -> list[int]:
    flagged = []
    for track_id, samples in samples_by_id.items():
        reversals = 0
        previous = None
        for sample in samples:
            angle = sample["direction_angle"]
            speed = sample["speed_px_s"]
            if angle is None or speed is None or speed >= 400:
                previous = None if angle is None else angle
                continue
            if previous is not None:
                change = abs(angle - previous)
                change = min(change, 360 - change)
                if change > 120:
                    reversals += 1
            previous = angle
        if reversals >= 3:
            flagged.append(track_id)
    return flagged


def analyze_camera(record: dict) -> dict:
    grouped = group_observations(record)
    motion_at = {}
    tracks = {}
    noisy = []
    for track_id, observations in sorted(grouped.items()):
        samples = analyze_track(observations)
        noisy.extend(track_id for track_id in noisy_tracks({track_id: samples}))
        for sample, source in zip(samples, observations):
            if sample["raw_center"] != [float(source["center_x"]), float(source["center_y"])]:
                raise SystemExit(f"Raw center changed for track {track_id}")
            motion_at[(track_id, sample["frame"])] = sample
        counts = defaultdict(int)
        for item in observations:
            counts[item["class"]] += 1
        tracks[str(track_id)] = {
            "track_id": track_id,
            "class": max(counts, key=counts.get),
            "observations": [public_sample(sample) for sample in samples],
        }
    by_frame = defaultdict(list)
    for frame in record["frames"]:
        by_frame[int(frame["frame"])].extend(frame["objects"])
    pairs = analyze_pairs(by_frame, motion_at)
    return {
        "fps": record["fps"],
        "width": record["width"],
        "height": record["height"],
        "tracks_analyzed": len(tracks),
        "pair_relationships": len(pairs),
        "pair_samples": sum(len(pair["samples"]) for pair in pairs),
        "noisy_tracks": noisy,
        "tracks": tracks,
        "pairs": pairs,
    }


def finite_numbers(value, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(word in lowered for word in FORBIDDEN_WORDS):
                raise SystemExit(f"Unexpected field {path}.{key}")
            finite_numbers(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            finite_numbers(item, f"{path}[{index}]")
        return
    if isinstance(value, str) and any(word in value.lower() for word in FORBIDDEN_WORDS):
        raise SystemExit(f"Unexpected text in {path}")
    if isinstance(value, float) and not math.isfinite(value):
        raise SystemExit(f"Non-finite number at {path}")


def validate(camera: str, record: dict, phase3_ids: set[int]) -> None:
    for track_id, track in record["tracks"].items():
        if int(track_id) not in phase3_ids:
            raise SystemExit(f"{camera} track {track_id} is not in Phase 3")
        previous_frame = None
        previous_time = None
        for sample in track["observations"]:
            frame = sample["frame"]
            timestamp = sample["timestamp"]
            if previous_frame is not None and frame <= previous_frame:
                raise SystemExit(f"{camera} track {track_id} frames are not increasing")
            if previous_time is not None and timestamp < previous_time:
                raise SystemExit(f"{camera} track {track_id} timestamps are not chronological")
            if sample["is_stationary"] and sample["direction_angle"] is not None:
                raise SystemExit(f"{camera} track {track_id} has a direction while stationary")
            if sample["dx"] == 0 and sample["dy"] == 0 and sample["direction_angle"] is not None:
                raise SystemExit(f"{camera} track {track_id} has a direction without displacement")
            previous_frame = frame
            previous_time = timestamp
    for pair in record["pairs"]:
        if pair["track_a"] not in phase3_ids or pair["track_b"] not in phase3_ids:
            raise SystemExit(f"{camera} pair uses an unknown track")
        previous_frame = None
        for sample in pair["samples"]:
            if sample["separation_px"] < 0:
                raise SystemExit(f"{camera} pair separation is negative")
            if not 0 <= sample["bbox_iou"] <= 1:
                raise SystemExit(f"{camera} pair IoU is outside 0..1")
            if sample["trajectory_relationship"] not in {"converging", "roughly_parallel", "diverging", "uncertain"}:
                raise SystemExit(f"{camera} pair has an unknown motion relationship")
            if previous_frame is not None and sample["frame"] <= previous_frame:
                raise SystemExit(f"{camera} pair frames are not increasing")
            previous_frame = sample["frame"]
    finite_numbers(record, camera)


def main() -> None:
    source = load_tracks()
    analysis = {"method": method_notes(), "cameras": {}}
    print("Motion filtering:", method_notes()["filtered_center"])
    print("Deadband:", method_notes()["displacement_deadband_px"])
    for camera, record in source.items():
        print(f"Analyzing {camera}...", flush=True)
        result = analyze_camera(record)
        phase3_ids = {int(item["track_id"]) for frame in record["frames"] for item in frame["objects"]}
        if phase3_ids != {int(track_id) for track_id in result["tracks"]}:
            raise SystemExit(f"{camera} motion tracks do not match Phase 3 ids")
        validate(camera, result, phase3_ids)
        analysis["cameras"][camera] = result
        noisy = ", ".join(f"#{track_id}" for track_id in result["noisy_tracks"]) or "none"
        print(
            f"  tracks {result['tracks_analyzed']}, "
            f"pairs {result['pair_relationships']} ({result['pair_samples']} samples), "
            f"noisy {noisy}",
            flush=True,
        )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(analysis, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")
    print("View: python scripts/view_motion_results.py")


if __name__ == "__main__":
    main()
