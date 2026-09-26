#!/usr/bin/env python3
"""Download the public portions needed for the ten NotifYC demo clips.

Uses a normal yt-dlp request and FFmpeg. It does not try to bypass
authentication, Premium, DRM, or other access controls.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import prepare_demo_clips as clips

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = REPO_ROOT / "data" / "temp"
END_PAD_SECONDS = 3

SOURCES = (
    {
        "id": 1,
        "url": "https://www.youtube.com/watch?v=e5x4d9GhepM",
        "file": "source1.mp4",
    },
    {
        "id": 2,
        "url": "https://www.youtube.com/watch?v=Y1jTEyb3wiI",
        "file": "source2.mp4",
    },
    {
        "id": 3,
        "url": "https://www.youtube.com/watch?v=zOq2XdwHGT0",
        "file": "source3.mp4",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and cut the ten NotifYC demo camera clips.")
    parser.add_argument("--force", action="store_true", help="Replace clips that already validate.")
    return parser.parse_args()


def require_ytdlp() -> str:
    path = clips.shutil.which("yt-dlp")
    if path is None:
        local = REPO_ROOT / ".venv" / "bin" / "yt-dlp"
        if local.is_file():
            return str(local)
        raise SystemExit("yt-dlp is not installed. Install it in the project environment and run again.")
    return path


def hms(total_seconds: int) -> str:
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def source_end(source_id: int) -> int:
    return max(clip["end"] for clip in clips.CLIPS if clip["source"] == source_id)


def download_source(ytdlp: str, ffmpeg: str, source: dict, destination: Path) -> None:
    end = source_end(source["id"]) + END_PAD_SECONDS
    section = f"*00:00:00-{hms(end)}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ytdlp,
        "--no-playlist",
        "--no-progress",
        "--ffmpeg-location",
        str(Path(ffmpeg).parent),
        "--download-sections",
        section,
        "--force-keyframes-at-cuts",
        "-f",
        "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        str(destination),
        source["url"],
    ]
    print(f"Fetching source {source['id']} through {hms(end)}...", flush=True)
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
        raise SystemExit(
            f"yt-dlp stopped on source {source['id']} with exit code {result.returncode}. "
            "Not retrying or changing the request."
        )
    if not destination.is_file():
        raise SystemExit(f"yt-dlp finished but did not write {destination}")


def clips_for(source_id: int) -> tuple[dict, ...]:
    return tuple(clip for clip in clips.CLIPS if clip["source"] == source_id)


def needs_source(ffprobe: str, source_id: int, force: bool) -> bool:
    if force:
        return True
    for clip in clips_for(source_id):
        status, _info = clips.validate_clip(ffprobe, clip, clips.OUTPUT_DIR / clip["file"])
        if status != "OK":
            return True
    return False


def remove_temp_sources() -> None:
    if not TEMP_DIR.is_dir():
        return
    for path in TEMP_DIR.iterdir():
        if path.is_file():
            path.unlink()


def main() -> None:
    args = parse_args()
    ytdlp = require_ytdlp()
    ffmpeg = clips.require_tool("ffmpeg")
    ffprobe = clips.require_tool("ffprobe")
    clips.require_h264_encoder(ffmpeg)
    clips.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    for source in SOURCES:
        if not needs_source(ffprobe, source["id"], args.force):
            print(f"Source {source['id']} clips already validate. Skipping download.")
            continue
        temp_path = TEMP_DIR / source["file"]
        download_source(ytdlp, ffmpeg, source, temp_path)
        info = clips.probe(ffprobe, temp_path)
        needed = source_end(source["id"])
        if info["duration"] + 0.05 < needed:
            raise SystemExit(
                f"Source {source['id']} download is {info['duration']:.1f}s, "
                f"but a clip ends at {needed:.0f}s."
            )
        for clip in clips_for(source["id"]):
            destination = clips.OUTPUT_DIR / clip["file"]
            if not args.force:
                status, _existing = clips.validate_clip(ffprobe, clip, destination)
                if status == "OK":
                    continue
            print(f"Cutting {clip['camera']}...", flush=True)
            clips.cut_clip(ffmpeg, temp_path, clip, destination)

    rows = []
    for clip in clips.CLIPS:
        status, probed = clips.validate_clip(ffprobe, clip, clips.OUTPUT_DIR / clip["file"])
        rows.append((clip, status, probed))
    clips.print_report(rows)
    failed = [clip["camera"] for clip, status, _info in rows if status != "OK"]
    if failed:
        raise SystemExit("Clip validation failed: " + ", ".join(failed))

    remove_temp_sources()
    print(f"\nWrote {len(clips.CLIPS)} clips to {clips.OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
