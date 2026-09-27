#!/usr/bin/env python3
"""Pair-centric possible-collision events from Phase 4 motion.

A slowdown is not a collision. The pair has to approach one region, arrive
there together, and then change motion immediately. collisionEvidenceScore
stays 0 unless that sequence holds. The score is evidence out of 100, not a
chance estimate. The same rules run on every camera.
"""

import json
import math
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parent.parent
MOTION_PATH = REPO_ROOT / "outputs" / "motion" / "motion_analysis.json"
TRACKS_PATH = REPO_ROOT / "outputs" / "tracking" / "tracks.json"
OUTPUT_PATH = REPO_ROOT / "outputs" / "evaluation" / "results.json"

PRE_SECONDS = 1.0
CONTACT_LOOK_S = 0.35
RESPONSE_S = 0.4
HOLD_RED_S = 1.5
EPISODE_GAP_S = 0.75
CLOSING_MIN_PX_S = 60.0
APPROACH_MIN_SAMPLES = 5
APPROACH_MIN_SPAN_S = 0.25
APPROACH_DROP_PX = 30.0
PROJECTION_HORIZON_S = 1.2
MISS_BODY_FRACTION = 0.35
CONTACT_SEP_FRACTION = 0.55
CANDIDATE_NORM = 1.6
MOVING_PX_S = 40.0
IMPACT_POST_PX_S = 120.0
IMPACT_DROP_PX_S = 80.0
DEFLECTION_DEG = 40.0
PARALLEL_DEG = 30.0
ASPECT_CHANGE_MIN = 0.35
STATIC_OBSTACLE_CLASS = "static_scene_obstacle"

PASSED_WEIGHTS = {
    "approach_strength": 15,
    "path_convergence": 12,
    "proximity_strength": 13,
    "overlap_support": 5,
    "trajectory_deflection": 18,
    "velocity_response": 15,
    "stationary_response": 7,
    "synchronized_response": 10,
    "geometry_change": 5,
}


def method_notes() -> dict:
    if sum(PASSED_WEIGHTS.values()) != 100:
        raise SystemExit("Passed-event weights must add up to 100")
    return {
        "score_meaning": "collisionEvidenceScore is 0 unless approach, contact, and an immediate pair response all pass",
        "gates": ["approach", "interaction", "physical_response"],
        "gate_rule": "points from one stage cannot fill in a missing stage",
        "closing_speed": "positive only while center separation is decreasing, in pixels per second",
        "relative_speed": "magnitude of the difference of the two image-space velocity vectors",
        "projection": "short constant-velocity image paths; not a road time-to-contact",
        "response_window_s": RESPONSE_S,
        "red_box": "green until surfaced_at, then red only for participant tracks",
        "passed_event_weights": PASSED_WEIGHTS,
        "static_scene": f"only a detected {STATIC_OBSTACLE_CLASS} track can open that path",
    }


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing {path}")
    return json.loads(path.read_text())


def box_index(tracks: dict) -> dict:
    indexed = {}
    for camera, record in tracks.items():
        indexed[camera] = {}
        for frame in record["frames"]:
            for item in frame["objects"]:
                indexed[camera][(item["frame"], item["track_id"])] = item
    return indexed


def round_or_none(value, digits=2):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return round(float(value), digits)


def diagonal(box) -> float:
    return math.hypot(box["width"], box["height"])


def rect_gap(first, second) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    gap_x = max(0.0, max(ax1, bx1) - min(ax2, bx2))
    gap_y = max(0.0, max(ay1, by1) - min(ay2, by2))
    return math.hypot(gap_x, gap_y)


def angle_gap(first, second) -> float:
    change = abs(first - second) % 360.0
    return min(change, 360.0 - change)


def angle_between(first, second) -> float:
    a_len = math.hypot(*first)
    b_len = math.hypot(*second)
    if a_len == 0 or b_len == 0:
        return 180.0
    cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / (a_len * b_len)))
    return math.degrees(math.acos(cosine))


def in_window(samples, start, end):
    return [sample for sample in samples if start <= sample["timestamp"] <= end]


def episodes(samples):
    groups = []
    current = []
    ordered = sorted(samples, key=lambda sample: sample["timestamp"])
    for sample in ordered:
        if current and sample["timestamp"] - current[-1]["timestamp"] > EPISODE_GAP_S:
            groups.append(current)
            current = []
        current.append(sample)
    if current:
        groups.append(current)
    return groups


def nearest_box(boxes, observations, track_id, timestamp):
    nearby = in_window(observations, timestamp - 0.12, timestamp + 0.12)
    for sample in reversed(nearby or observations):
        item = boxes.get((sample["frame"], track_id))
        if item is not None:
            return item
    return None


def speed_median(observations, start, end):
    values = [
        sample["speed_px_s"]
        for sample in observations
        if start <= sample["timestamp"] <= end and sample["speed_px_s"] is not None
    ]
    if len(values) < 3:
        return None
    return float(median(values))


def velocity_median(observations, start, end):
    chosen = [
        sample
        for sample in observations
        if start <= sample["timestamp"] <= end
        and sample["vx_px_s"] is not None
        and sample["speed_px_s"] is not None
        and sample["speed_px_s"] >= MOVING_PX_S
    ]
    if len(chosen) < 3:
        return None
    vx = float(median(sample["vx_px_s"] for sample in chosen))
    vy = float(median(sample["vy_px_s"] for sample in chosen))
    return {"vx": vx, "vy": vy, "speed": math.hypot(vx, vy), "position": chosen[-1]["filtered_center"]}


def heading_deg(observations, start, end):
    angles = [
        sample["direction_angle"]
        for sample in observations
        if start <= sample["timestamp"] <= end and sample["direction_angle"] is not None and (sample["speed_px_s"] or 0) >= MOVING_PX_S
    ]
    if len(angles) < 3:
        return None
    x_sum = sum(math.cos(math.radians(angle)) for angle in angles)
    y_sum = sum(math.sin(math.radians(angle)) for angle in angles)
    if math.hypot(x_sum, y_sum) < 1e-6:
        return None
    return math.degrees(math.atan2(y_sum, x_sum))


def ray_miss(mover, point) -> tuple[float, float] | None:
    speed = mover["speed"]
    if speed < 1:
        return None
    dx = point[0] - mover["position"][0]
    dy = point[1] - mover["position"][1]
    time_s = (dx * mover["vx"] + dy * mover["vy"]) / (speed * speed)
    miss = abs(dx * mover["vy"] - dy * mover["vx"]) / speed
    return time_s, miss


def project_pair(first, second):
    if first is None or second is None:
        return None
    rx = second["position"][0] - first["position"][0]
    ry = second["position"][1] - first["position"][1]
    rvx = second["vx"] - first["vx"]
    rvy = second["vy"] - first["vy"]
    relative_sq = rvx * rvx + rvy * rvy
    if relative_sq < 1:
        return None
    time_s = -((rx * rvx) + (ry * rvy)) / relative_sq
    miss = math.hypot(rx + rvx * time_s, ry + rvy * time_s)
    heading = angle_between((first["vx"], first["vy"]), (second["vx"], second["vy"]))
    return {"time_s": time_s, "miss_px": miss, "heading_deg": heading, "relative_speed": math.sqrt(relative_sq)}


def aspect_change(boxes, observations, track_id, pre, post):
    def values(start, end):
        found = []
        for sample in observations:
            if not start <= sample["timestamp"] <= end:
                continue
            item = boxes.get((sample["frame"], track_id))
            if item is None or item["height"] <= 0:
                continue
            found.append(item["width"] / item["height"])
        return found

    before = values(*pre)
    after = values(*post)
    if len(before) < 3 or len(after) < 3 or median(before) <= 0:
        return 0.0
    change = abs(median(after) - median(before)) / median(before)
    if change < ASPECT_CHANGE_MIN:
        return 0.0
    return min(1.0, change / 0.7)


def score_episode(camera, pair, episode, observations, classes, boxes) -> dict | None:
    norms = [sample["normalized_separation"] for sample in episode]
    if min(norms) > CANDIDATE_NORM and max(sample["bbox_iou"] for sample in episode) < 0.02:
        return None
    closest = min(episode, key=lambda sample: (sample["separation_px"], -sample["bbox_iou"]))
    closest_time = closest["timestamp"]
    track_ids = [pair["track_a"], pair["track_b"]]
    tracks = [observations[track_id] for track_id in track_ids]
    before = [sample for sample in episode if closest_time - PRE_SECONDS <= sample["timestamp"] < closest_time - 0.05]
    rates = [
        (sample["timestamp"], sample["relative_approach_px_s"])
        for sample in before
        if sample["relative_approach_px_s"] is not None and sample["relative_approach_px_s"] >= CLOSING_MIN_PX_S
    ]
    span = 0.0 if len(rates) < 2 else rates[-1][0] - rates[0][0]
    net_drop = None if not before else before[0]["separation_px"] - closest["separation_px"]
    sustained = len(rates) >= APPROACH_MIN_SAMPLES and span >= APPROACH_MIN_SPAN_S and (net_drop or 0) >= APPROACH_DROP_PX
    closing_speed = None if not rates else float(median(rate for _, rate in rates))

    present = []
    vectors = []
    for track_id, samples in zip(track_ids, tracks):
        box = nearest_box(boxes, samples, track_id, closest_time)
        present.append(box)
        vectors.append(velocity_median(samples, closest_time - 0.8, closest_time - 0.2))
    both_present = all(present)
    smaller = None
    if both_present:
        smaller = min(present, key=diagonal)
    mean_diag = None
    if closest["normalized_separation"] > 1e-6:
        mean_diag = closest["separation_px"] / closest["normalized_separation"]

    rel_vx = rel_vy = relative_speed = None
    if vectors[0] and vectors[1]:
        rel_vx = vectors[0]["vx"] - vectors[1]["vx"]
        rel_vy = vectors[0]["vy"] - vectors[1]["vy"]
        relative_speed = math.hypot(rel_vx, rel_vy)
    elif vectors[0]:
        rel_vx, rel_vy, relative_speed = vectors[0]["vx"], vectors[0]["vy"], vectors[0]["speed"]
    elif vectors[1]:
        rel_vx, rel_vy, relative_speed = -vectors[1]["vx"], -vectors[1]["vy"], vectors[1]["speed"]

    projection = project_pair_meeting(vectors, present)
    parallel = False
    if vectors[0] and vectors[1]:
        parallel = angle_between((vectors[0]["vx"], vectors[0]["vy"]), (vectors[1]["vx"], vectors[1]["vy"])) <= PARALLEL_DEG
        if projection and projection["miss_px"] <= 0.4 * (diagonal(smaller) if smaller else 1e9):
            parallel = False
    paths_meet = bool(projection and projection["meets"])
    approach_ok = sustained and paths_meet and not parallel and both_present

    contact_sep = closest["separation_px"]
    contact_limit = CONTACT_SEP_FRACTION * diagonal(smaller) if smaller else 0
    gap = rect_gap(present[0]["bbox"], present[1]["bbox"]) if both_present else 1e9
    short_side = min(min(present[0]["width"], present[0]["height"]), min(present[1]["width"], present[1]["height"])) if both_present else 1
    contact_ok = both_present and (contact_sep <= contact_limit or (gap <= 0.15 * short_side and closest["bbox_iou"] >= 0.08))
    if projection and not projection["meets"]:
        contact_ok = False

    responses = [impact_response(samples, closest_time) for samples in tracks]
    for index, track_id in enumerate(track_ids):
        responses[index]["geometry"] = aspect_change(boxes, tracks[index], track_id, closest_time)
        responses[index]["deflection_deg"] = deflection(tracks[index], closest_time)
    responded = [response["responded"] for response in responses]
    response_ok = any(responded)
    response_time = min((response["response_time"] for response in responses if response["response_time"] is not None), default=None)
    delay = None if response_time is None else response_time - closest_time

    gates = {"approach": approach_ok, "interaction": contact_ok, "physical_response": response_ok}
    metrics = pair_metrics(
        approach_ok, sustained, rates, net_drop, projection, closest, responses, both_present
    )
    detected, score, label, failed = decision(gates, metrics)
    surfaced = None if not detected else (response_time if response_time is not None else closest_time + RESPONSE_S)
    surfaced_frame, display_end = display_bounds(observations, track_ids, surfaced) if surfaced is not None else (None, None)
    return {
        "camera_id": camera,
        "track_ids_examined": track_ids,
        "participant_track_ids": track_ids if detected else [],
        "classes": [classes.get(track_id, "unknown") for track_id in track_ids],
        "collisionDetected": detected,
        "collisionEvidenceScore": score,
        "label": label,
        "detection_label": "Possible Collision" if detected else None,
        "closest_interaction_time": round(closest_time, 3),
        "detected_at": None if surfaced is None else round(surfaced, 3),
        "surfaced_at": None if surfaced is None else round(surfaced, 3),
        "closest_frame": closest["frame"],
        "surfaced_frame": surfaced_frame,
        "display_end_frame": display_end,
        "gates": gates,
        "failed_gates": failed,
        "candidateDiagnostics": {
            "approach_detected": approach_ok,
            "approach_duration": round(span if (span := (rates[-1][0] - rates[0][0] if len(rates) > 1 else 0)) else 0, 3),
            "separation_reduction": round_or_none(net_drop, 2),
            "relative_approach_rate": round_or_none(closing_speed, 2),
            "relative_speed_px_s": round_or_none(relative_speed, 2),
            "closing_speed_px_s": round_or_none(closing_speed, 2),
            "projected_path_convergence": bool(paths_meet),
            "projected_closest_distance": None if not projection else round(projection["miss_px"], 2),
            "projected_time_alignment": None if not projection else round_or_none(projection["time_s"], 3),
            "minimum_separation_px": round(contact_sep, 2),
            "minimum_normalized_separation": closest["normalized_separation"],
            "bbox_iou_at_interaction": closest["bbox_iou"],
            "motion_response_delay_s": round_or_none(delay, 3),
            "trajectory_deflection_deg": [response["deflection_deg"] for response in responses],
            "pre_speed_px_s": [response["pre_speed"] for response in responses],
            "interaction_speed_px_s": [response["interaction_speed"] for response in responses],
            "post_speed_px_s": [response["post_speed"] for response in responses],
            "speed_change_px_s": [response["speed_change"] for response in responses],
            "synchronized_response": sum(responded) >= 2,
            "abrupt_geometry_change": any(response["geometry"] > 0 for response in responses),
            "candidate_metrics": metrics,
        },
    }


def project_pair_meeting(vectors, present):
    if not all(present):
        return None
    smaller = min(present, key=lambda item: min(item["width"], item["height"]))
    body = MISS_BODY_FRACTION * min(smaller["width"], smaller["height"])
    if vectors[0] and vectors[1] and vectors[0]["speed"] >= MOVING_PX_S and vectors[1]["speed"] >= MOVING_PX_S:
        planned = project_pair(vectors[0], vectors[1])
        if planned is None:
            return None
        meets = 0 <= planned["time_s"] <= PROJECTION_HORIZON_S and planned["miss_px"] <= body
        return {**planned, "meets": meets, "body_px": round(body, 2)}
    mover = still = None
    if vectors[0] and vectors[0]["speed"] >= MOVING_PX_S and (vectors[1] is None or vectors[1]["speed"] < MOVING_PX_S):
        mover, still = vectors[0], present[1]
    elif vectors[1] and vectors[1]["speed"] >= MOVING_PX_S and (vectors[0] is None or vectors[0]["speed"] < MOVING_PX_S):
        mover, still = vectors[1], present[0]
    if mover is None or still is None:
        return None
    hit = ray_miss(mover, [(still["bbox"][0] + still["bbox"][2]) / 2, (still["bbox"][1] + still["bbox"][3]) / 2])
    if hit is None:
        return None
    time_s, miss = hit
    return {
        "time_s": time_s,
        "miss_px": miss,
        "heading_deg": None,
        "relative_speed": mover["speed"],
        "meets": 0 < time_s <= PROJECTION_HORIZON_S and miss <= body,
        "body_px": round(body, 2),
    }


def impact_response(observations, closest_time) -> dict:
    earlier = speed_median(observations, closest_time - 0.85, closest_time - 0.45)
    before = speed_median(observations, closest_time - 0.4, closest_time - 0.08)
    after = speed_median(observations, closest_time + 0.08, closest_time + RESPONSE_S)
    at_contact = speed_median(observations, closest_time - 0.12, closest_time + 0.12)
    drop_now = None if before is None or after is None else before - after
    drop_already = None if earlier is None or before is None else earlier - before
    sharp = (
        before is not None
        and after is not None
        and before >= 80
        and drop_now is not None
        and drop_now >= IMPACT_DROP_PX_S
        and after <= 0.45 * before
        and after <= IMPACT_POST_PX_S
        and (drop_already is None or drop_now >= drop_already + 60)
    )
    stopped = before is not None and before >= MOVING_PX_S and after is not None and after < 15 and (drop_already is None or drop_already < 40)
    deflection_deg = None
    pre_heading = heading_deg(observations, closest_time - 0.7, closest_time - 0.12)
    post_heading = heading_deg(observations, closest_time + 0.08, closest_time + RESPONSE_S)
    pre_fast = before is not None and before >= MOVING_PX_S
    post_fast = after is not None and after >= MOVING_PX_S
    if pre_heading is not None and post_heading is not None and pre_fast and post_fast:
        deflection_deg = angle_gap(pre_heading, post_heading)
    turned = deflection_deg is not None and deflection_deg >= DEFLECTION_DEG
    response_time = None
    if sharp or stopped or turned:
        response_time = closest_time + RESPONSE_S
    return {
        "responded": sharp or stopped or turned,
        "response_time": response_time,
        "pre_speed": round_or_none(before, 2),
        "interaction_speed": round_or_none(at_contact, 2),
        "post_speed": round_or_none(after, 2),
        "speed_change": round_or_none(None if before is None or after is None else after - before, 2),
        "deflection_deg": round_or_none(deflection_deg, 1),
        "geometry": 0.0,
    }


def aspect_change(boxes, observations, track_id, closest_time) -> float:
    def values(start, end):
        found = []
        for sample in observations:
            if not start <= sample["timestamp"] <= end:
                continue
            item = boxes.get((sample["frame"], track_id))
            if item is None or item["height"] <= 0:
                continue
            found.append(item["width"] / item["height"])
        return found

    before = values(closest_time - 0.7, closest_time - 0.12)
    after = values(closest_time + 0.08, closest_time + RESPONSE_S)
    if len(before) < 3 or len(after) < 3 or median(before) <= 0:
        return 0.0
    change = abs(median(after) - median(before)) / median(before)
    if change < ASPECT_CHANGE_MIN:
        return 0.0
    return min(1.0, change / 0.7)


def deflection(observations, closest_time):
    pre_heading = heading_deg(observations, closest_time - 0.7, closest_time - 0.12)
    post_heading = heading_deg(observations, closest_time + 0.08, closest_time + RESPONSE_S)
    if pre_heading is None or post_heading is None:
        return None
    return round(angle_gap(pre_heading, post_heading), 1)


def pair_metrics(approach_ok, sustained, rates, net_drop, projection, closest, responses, both_present) -> dict:
    if approach_ok and rates and net_drop:
        approach_strength = min(1.0, median(rate for _, rate in rates) / 220.0) * min(1.0, net_drop / 80.0)
    else:
        approach_strength = 0.0
    if projection and projection["meets"]:
        miss_score = 1.0 if projection["miss_px"] <= 0.5 * projection["body_px"] else 0.6
    else:
        miss_score = 0.0
    proximity = 1.0 if closest["normalized_separation"] <= 0.45 else max(0.0, min(1.0, (1.2 - closest["normalized_separation"]) / 0.75))
    overlap = 0.0 if closest["bbox_iou"] < 0.02 else min(1.0, closest["bbox_iou"] / 0.25)
    deflection_score = 0.0
    velocity_score = 0.0
    stationary_score = 0.0
    for response in responses:
        if response["deflection_deg"] is not None:
            deflection_score = max(deflection_score, min(1.0, max(0.0, (response["deflection_deg"] - 15) / 60)))
        if response["responded"] and response["post_speed"] is not None and response["pre_speed"]:
            if response["post_speed"] <= IMPACT_POST_PX_S:
                velocity_score = max(velocity_score, 1.0 if response["post_speed"] < 15 else 0.7)
        if response["post_speed"] is not None and response["post_speed"] < 15 and response["responded"]:
            stationary_score = 1.0
    sync = 1.0 if sum(response["responded"] for response in responses) >= 2 else 0.0
    geometry = max(response["geometry"] for response in responses) if responses else 0.0
    if not approach_ok:
        approach_strength = 0.0
        miss_score = 0.0
    return {
        "approach_strength": round(approach_strength, 3),
        "path_convergence": round(miss_score, 3),
        "proximity_strength": round(proximity if both_present else 0.0, 3),
        "overlap_support": round(overlap, 3),
        "trajectory_deflection": round(deflection_score, 3),
        "velocity_response": round(velocity_score, 3),
        "stationary_response": stationary_score,
        "synchronized_response": sync,
        "geometry_change": round(geometry, 3),
    }


def decision(gates, metrics):
    failed = [name for name, passed in gates.items() if not passed]
    if failed:
        return False, 0, "no_collision_event", failed
    total = sum(PASSED_WEIGHTS[name] * metrics[name] for name in PASSED_WEIGHTS)
    return True, max(1, min(100, int(round(total)))), "possible_vehicle_collision", []


def display_bounds(tracks, track_ids, surfaced_time):
    frames = []
    end_frames = []
    for track_id in track_ids:
        for sample in tracks[track_id]:
            if sample["timestamp"] + 1e-6 >= surfaced_time:
                frames.append(sample["frame"])
            if surfaced_time <= sample["timestamp"] <= surfaced_time + HOLD_RED_S:
                end_frames.append(sample["frame"])
    if not frames:
        return None, None
    start = min(frames)
    end = max(end_frames or frames)
    return start, max(start, end)


def static_scene_events(record) -> list:
    """No obstacle class is invented from a vehicle that simply stops."""
    if any(track["class"] == STATIC_OBSTACLE_CLASS for track in record["tracks"].values()):
        return []
    return []


def analyze_camera(camera: str, record: dict, boxes: dict) -> dict:
    observations = {int(track_id): track["observations"] for track_id, track in record["tracks"].items()}
    classes = {int(track_id): track["class"] for track_id, track in record["tracks"].items()}
    camera_boxes = boxes.get(camera, {})
    candidates = []
    for pair in record["pairs"]:
        for episode in episodes(pair["samples"]):
            item = score_episode(camera, pair, episode, observations, classes, camera_boxes)
            if item is not None:
                if item["collisionDetected"]:
                    item["event_id"] = (
                        f"{camera}-{item['track_ids_examined'][0]}-{item['track_ids_examined'][1]}-f{item['closest_frame']}"
                    )
                candidates.append(item)
    return {
        "pairs_evaluated": len(record["pairs"]),
        "candidate_interactions": len(candidates),
        "static_scene_events": static_scene_events(record),
        "events": [item for item in candidates if item["collisionDetected"]],
        "rejected_candidates": [item for item in candidates if not item["collisionDetected"]],
    }


def finite_numbers(value, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            finite_numbers(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            finite_numbers(item, f"{path}[{index}]")
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise SystemExit(f"Non-finite number at {path}")


def validate(results: dict) -> None:
    for camera, record in results["cameras"].items():
        for event in record["events"]:
            if event["collisionEvidenceScore"] <= 0 or event["failed_gates"] or not all(event["gates"].values()):
                raise SystemExit(f"{camera} surfaced an incomplete pair")
            if event["surfaced_at"] is None or event["surfaced_at"] + 1e-6 < event["closest_interaction_time"]:
                raise SystemExit(f"{camera} colors the pair before the interaction evidence exists")
            if set(event["participant_track_ids"]) != set(event["track_ids_examined"]):
                raise SystemExit(f"{camera} participants are not the interacting pair")
        for item in record["rejected_candidates"]:
            if item["collisionEvidenceScore"] != 0 or item["collisionDetected"] or item["participant_track_ids"]:
                raise SystemExit(f"{camera} rejected pair still carries a score or participants")
        finite_numbers(record, camera)


def gate_self_check() -> None:
    metrics = {name: 1.0 for name in PASSED_WEIGHTS}
    detected, score, label, failed = decision(
        {"approach": True, "interaction": True, "physical_response": False},
        metrics,
    )
    if detected or score != 0 or "physical_response" not in failed:
        raise SystemExit("A slowdown without the full pair sequence still scored")
    detected, score, _, _ = decision({name: True for name in ("approach", "interaction", "physical_response")}, metrics)
    if not detected or not 1 <= score <= 100:
        raise SystemExit("A complete pair sequence did not receive an evidence score")


def print_report(results: dict) -> None:
    print("Score stays 0 unless the pair approaches, meets, and then responds.")
    for camera, record in results["cameras"].items():
        print(f"\n{camera} pairs {record['pairs_evaluated']} candidates {record['candidate_interactions']} events {len(record['events'])}")
        if not record["events"]:
            print("  collisionDetected false  score 0")
        for event in record["events"]:
            diag = event["candidateDiagnostics"]
            print(
                f"  EVENT {event['participant_track_ids']} score {event['collisionEvidenceScore']} "
                f"closest {event['closest_interaction_time']} surfaced {event['surfaced_at']}"
            )
            print(
                f"    closing {diag['closing_speed_px_s']} relative {diag['relative_speed_px_s']} "
                f"sep {diag['minimum_separation_px']} norm {diag['minimum_normalized_separation']} "
                f"defl {diag['trajectory_deflection_deg']}"
            )
            print(f"    pre {diag['pre_speed_px_s']} post {diag['post_speed_px_s']} sync {diag['synchronized_response']}")
        interesting = sorted(record["rejected_candidates"], key=lambda item: item["closest_interaction_time"])
        shown = [item for item in interesting if set(item["track_ids_examined"]) in ({1, 14}, {2, 4}, {2, 14}, {4, 14}, {10, 12})]
        for item in shown:
            diag = item["candidateDiagnostics"]
            print(
                f"  pair {item['track_ids_examined']} score {item['collisionEvidenceScore']} failed {item['failed_gates']} "
                f"at {item['closest_interaction_time']} sep {diag['minimum_separation_px']} "
                f"norm {diag['minimum_normalized_separation']} closing {diag['closing_speed_px_s']}"
            )


def main() -> None:
    gate_self_check()
    motion = load_json(MOTION_PATH)
    boxes = box_index(load_json(TRACKS_PATH))
    results = {"method": method_notes(), "cameras": {}}
    for camera, record in motion["cameras"].items():
        print(f"Scoring {camera}...", flush=True)
        results["cameras"][camera] = analyze_camera(camera, record, boxes)
    validate(results)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print_report(results)
    print(f"\nWrote {OUTPUT_PATH}")
    print("View: python scripts/view_collision_results.py")


if __name__ == "__main__":
    main()
