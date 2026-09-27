"""Print a briefing for one TEST / DEMO record.

Does not read videos, run detection, or write an incident.

    python -m briefing.run_test
    python -m briefing.run_test --camera CAM-004
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from briefing.demo_event import demo_event  # noqa: E402
from briefing.service import create_briefing  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a TEST / DEMO responder briefing.")
    parser.add_argument("--camera", default="CAM-004", help="Camera id to place on the test record.")
    args = parser.parse_args(argv)
    event = demo_event(args.camera)
    print("TEST / DEMO EVENT")
    print("This record was not produced by a camera or by the CV pipeline.")
    if not os.environ.get("XAI_API_KEY", "").strip():
        print("XAI_API_KEY is not set. Printing the deterministic fallback.")
    briefing = create_briefing(event)
    print(json.dumps({"input": event, "briefing": briefing}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
