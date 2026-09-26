# NotifYC

NotifYC analyzes fixed-camera urban traffic video and surfaces potential vehicle-pedestrian and vehicle-cyclist conflicts for human review.

Phase 1 detects and tracks road users, then writes an annotated video. It does not score conflicts yet.

## What Phase 1 does

`cv/process_video.py` loads the pretrained YOLO11n weights, tracks objects with ByteTrack, and saves an annotated copy of the video.

The output draws:

- a bounding box
- the class name
- a persistent track ID
- a trail of the last 20 center points

Detected classes are limited to person, bicycle, car, motorcycle, bus, and truck.

## Setup

Use Python 3.11. PyTorch, which Ultralytics installs, does not support the system Python 3.14 interpreter.

```bash
brew install python@3.11
cd NearMiss
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Put the source clip here:

```text
data/input/intersection.mp4
```

The first run downloads `yolo11n.pt` into the project directory. That file is the pretrained COCO model. Nothing is trained locally.

## Run

From the repository root, with the virtual environment activated:

```bash
python cv/process_video.py --input data/input/intersection.mp4
```

## Expected output

The command writes:

```text
outputs/processed/intersection_processed.mp4
```

The terminal then prints the frame size, source FPS, frames written, elapsed time, processing speed, boxes drawn, and unique track IDs overall and by class. A progress line is printed every 100 frames.

`outputs/events/` is unused in Phase 1.

## Common errors

**`Input video not found`**

The path is resolved from the current directory. Run the command from the repository root, and confirm `data/input/intersection.mp4` exists.

**`No module named 'ultralytics'` or `No module named 'cv2'`**

The virtual environment is not active, or the install did not finish. Run `source .venv/bin/activate` and then `pip install -r requirements.txt`.

**Torch or Ultralytics fails to install**

The active interpreter is not Python 3.11. Recreate the environment with `python3.11 -m venv .venv`.

**First run fails while fetching weights**

`yolo11n.pt` has to download once. Retry on a network connection. If a partial file was saved, delete `yolo11n.pt` and run the command again.

**The output file exists but will not play**

The writer uses the `mp4v` codec so OpenCV can save the video without an extra H.264 plugin. Open it in VLC if QuickTime rejects it.

**Boxes appear, but every label is missing `#id`**

ByteTrack did not return IDs for those detections, often because the confidence cutoff removed the track. Rerun with a lower cutoff, for example `--conf 0.15`.
