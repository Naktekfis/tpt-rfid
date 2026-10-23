#!/usr/bin/env python3
"""Read-only PN532 probe. Never print or persist the actual card UID."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.nfc_reader import PN532Reader  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=30.0)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("duration must be positive")
    reader = PN532Reader()
    count = 0

    def detected(event):
        nonlocal count
        count += 1
        print(
            "CARD: count={} UID_length={}".format(count, len(event["uid"]) // 2),
            flush=True,
        )

    reader.add_listener(detected)
    reader.start()
    previous = None
    connected_once = False
    try:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            status = reader.status()
            state = (status["connected"], status["firmware"])
            connected_once |= status["connected"]
            if state != previous:
                print("STATUS: connected={} firmware={}".format(*state), flush=True)
                previous = state
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()
    print("STOPPED: detections={}".format(count), flush=True)
    return 0 if connected_once else 1


if __name__ == "__main__":
    raise SystemExit(main())
