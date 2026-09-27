#!/usr/bin/env python3
"""Cut ten local demo-camera clips from three source videos the user supplies.

This script does not download anything. It only reads the files passed as
--source1, --source2, and --source3, and writes new files under data/cameras/.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data" / "cameras"
DURATION_TOLERANCE_SECONDS = 0.45

# Start and end times are in seconds, measured from the beginning of the local file.
CLIPS = (
    {"camera": "CAM-001", "file": "cam_001.mp4", "source": 1, "start": 0, "end": 10, "expected": 10},
    {"camera": "CAM-002", "file": "cam_002.mp4", "source": 1, "start": 3 * 60 + 44, "end": 3 * 60 + 50, "expected": 6},
    {"camera": "CAM-003", "file": "cam_003.mp4", "source": 1, "start": 7 * 60 + 47, "end": 7 * 60 + 54, "expected": 7},
    {"camera": "CAM-004", "file": "cam_004.mp4", "source": 2, "start": 6, "end": 11, "expected": 5},
    {"camera": "CAM-005", "file": "cam_005.mp4", "source": 2, "start": 11, "end": 15, "expected": 4},
    {"camera": "CAM-006", "file": "cam_006.mp4", "source": 2, "start": 15, "end": 20, "expected": 5},
    {"camera": "CAM-007", "file": "cam_007.mp4", "source": 3, "start": 0, "end": 6, "expected": 6},
    {"camera": "CAM-008", "file": "cam_008.mp4", "source": 3, "start": 8, "end": 13, "expected": 5},
    {"camera": "CAM-009", "file": "cam_009.mp4", "source": 3, "start": 18, "end": 24, "expected": 6},
    {"camera": "CAM-010", "file": "cam_010.mp4", "source": 3, "start": 25, "end": 30, "expected": 5},
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut ten demo camera MP4s from three local source videos."
    )
    parser.add_argument("--source1", required=True, type=Path, help="Local file for CAM-001 through CAM-003.")
    parser.add_argument("--source2", required=True, type=Path, help="Local file for CAM-004 through CAM-006.")
    parser.add_argument("--source3", required=True, type=Path, help="Local file for CAM-007 through CAM-010.")
    return parser.parse_args()


def require_tool(name: str) -> str:
    local = REPO_ROOT / ".tools" / "bin" / name
    if local.is_file():
        return str(local)
    path = shutil.which(name)
    if path is None:
        raise SystemExit(
            f"{name} was not found. Expected {local}, or {name} on PATH."
        )
    return path


def require_h264_encoder(ffmpeg: str) -> None:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or "libx264" not in result.stdout:
        raise SystemExit(
            "FFmpeg is installed, but the libx264 encoder is missing. "
            "Install an FFmpeg build that includes libx264."
        )


def probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-select_streams",
            "v:0",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"ffprobe failed for {path}")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    if not streams:
        raise RuntimeError(f"No video stream in {path}")
    stream = streams[0]
    format_info = payload.get("format") or {}
    duration = float(stream.get("duration") or format_info.get("duration") or 0)
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    fps = _ratio(rate)
    return {
        "duration": duration,
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": fps,
    }


def _ratio(value: str) -> float:
    if "/" in str(value):
        numerator, denominator = str(value).split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            return 0.0
        return float(numerator) / denominator_value
    return float(value)


def check_sources(ffprobe: str, sources: dict[int, Path]) -> None:
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise SystemExit("Source video not found:\n" + "\n".join(missing))

    for source_number, path in sources.items():
        info = probe(ffprobe, path)
        needed = max(clip["end"] for clip in CLIPS if clip["source"] == source_number)
        if info["duration"] + 0.05 < needed:
            raise SystemExit(
                f"--source{source_number} is {info['duration']:.1f}s long, "
                f"but a clip ends at {needed:.0f}s: {path}"
            )


def cut_clip(ffmpeg: str, source: Path, clip: dict, destination: Path) -> None:
    duration = clip["end"] - clip["start"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-ss",
        f"{clip['start']:.3f}",
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        str(destination),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or "ffmpeg failed"
        raise RuntimeError(f"{clip['camera']}: {detail}")


def opencv_can_read(path: Path) -> str | None:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return "OpenCV could not open the file"
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        return "OpenCV opened the file but could not read a frame"
    return None


def validate_clip(ffprobe: str, clip: dict, path: Path) -> tuple[str, dict]:
    if not path.is_file():
        return "MISSING", {}
    try:
        info = probe(ffprobe, path)
    except RuntimeError as error:
        return str(error), {}
    read_error = opencv_can_read(path)
    if read_error:
        return read_error, info
    if info["width"] <= 0 or info["height"] <= 0:
        return "missing resolution", info
    if abs(info["duration"] - clip["expected"]) > DURATION_TOLERANCE_SECONDS:
        return f"duration {info['duration']:.2f}s, expected {clip['expected']:.0f}s", info
    return "OK", info


def print_report(rows: list[tuple[dict, str, dict]]) -> None:
    print(f"\n{'CAMERA':<10} {'DURATION':>10} {'RESOLUTION':>14} {'FPS':>8}  STATUS")
    for clip, status, info in rows:
        if info:
            duration = f"{info['duration']:.1f}s"
            resolution = f"{info['width']}x{info['height']}"
            fps = f"{info['fps']:.2f}"
        else:
            duration = "-"
            resolution = "-"
            fps = "-"
        print(f"{clip['camera']:<10} {duration:>10} {resolution:>14} {fps:>8}  {status}")


def main() -> None:
    args = parse_args()
    ffmpeg = require_tool("ffmpeg")
    ffprobe = require_tool("ffprobe")
    require_h264_encoder(ffmpeg)

    sources = {1: args.source1, 2: args.source2, 3: args.source3}
    check_sources(ffprobe, sources)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for clip in CLIPS:
        destination = OUTPUT_DIR / clip["file"]
        print(f"Cutting {clip['camera']} from source {clip['source']}...", flush=True)
        try:
            cut_clip(ffmpeg, sources[clip["source"]], clip, destination)
        except RuntimeError as error:
            rows.append((clip, str(error), {}))
            continue
        status, info = validate_clip(ffprobe, clip, destination)
        rows.append((clip, status, info))

    print_report(rows)
    failed = [clip["camera"] for clip, status, _info in rows if status != "OK"]
    if failed:
        raise SystemExit("Clip validation failed: " + ", ".join(failed))
    print(f"\nWrote {len(CLIPS)} clips to {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
