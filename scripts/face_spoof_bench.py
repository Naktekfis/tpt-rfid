"""
Compare the liveness models on the kiosk camera, to choose FACE_LIVENESS_MODELS.

Reads the running app's camera stream (no second camera user), finds the face
with YuNet, scores it with every liveness model and appends the scores (no
images) to a CSV. Run it once per sample type, then print the report:

  .venv/bin/python scripts/face_spoof_bench.py real     # a real face, move a bit
  .venv/bin/python scripts/face_spoof_bench.py print    # printed photo of a face
  .venv/bin/python scripts/face_spoof_bench.py screen   # photo/video on a phone
  .venv/bin/python scripts/face_spoof_bench.py --report

Options: --seconds N (default 15), --csv PATH (default ~/fas-bench.csv),
--url (default http://127.0.0.1:5000/camera/stream).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.face import YuNetSFaceEngine  # noqa: E402
from utils.liveness import MODELS  # noqa: E402

MODEL_DIR = str(Path(__file__).resolve().parents[1] / "models" / "face")


def frames(url: str, seconds: float):
    import cv2
    import numpy as np

    end = time.monotonic() + seconds
    buf = b""
    with urllib.request.urlopen(url, timeout=10) as resp:
        while time.monotonic() < end:
            buf += resp.read(16384)
            start = buf.find(b"\xff\xd8")
            stop = buf.find(b"\xff\xd9", start + 2)
            if start < 0 or stop < 0:
                continue
            jpg, buf = buf[start : stop + 2], buf[stop + 2 :]
            frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:
                yield frame


def record(label: str, args) -> None:
    engine = YuNetSFaceEngine(MODEL_DIR)
    models = {name: cls(MODEL_DIR) for name, cls in MODELS.items()}
    timing = defaultdict(float)
    rows, seen = [], 0
    for frame in frames(args.url, args.seconds):
        seen += 1
        faces = [f for f in engine.detect(frame) if min(f.box[2], f.box[3]) >= 100]
        if len(faces) != 1:
            continue
        for name, model in models.items():
            t = time.perf_counter()
            score = model.score(frame, faces[0])
            timing[name] += time.perf_counter() - t
            rows.append((label, name, round(score, 4)))
    new = not os.path.exists(args.csv)
    with open(args.csv, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["label", "model", "score"])
        w.writerows(rows)
    used = len(rows) // max(1, len(models))
    print(f"{label}: {seen} frames, {used} with one face -> {args.csv}")
    for name in models:
        vals = sorted(s for lab, m, s in rows if m == name)
        if vals:
            ms = 1000 * timing[name] / len(vals)
            print(
                f"  {name:11s} median {vals[len(vals) // 2]:.3f}  min {vals[0]:.3f}  max {vals[-1]:.3f}  {ms:.0f} ms"
            )


def report(path: str) -> None:
    data = defaultdict(lambda: defaultdict(list))
    with open(path) as fh:
        for row in csv.DictReader(fh):
            data[row["model"]][row["label"]].append(float(row["score"]))
    for model, by_label in sorted(data.items()):
        real = by_label.get("real", [])
        spoof = [v for lab, vals in by_label.items() if lab != "real" for v in vals]
        print(
            f"\n{model}: real n={len(real)}, spoof n={len(spoof)} ({', '.join(f'{k}={len(v)}' for k, v in by_label.items() if k != 'real')})"
        )
        if not real or not spoof:
            print("  need both real and spoof samples")
            continue
        print("  thr   real pass   spoof pass")
        best = None
        for i in range(1, 20):
            t = i / 20
            rp = sum(v >= t for v in real) / len(real)
            sp = sum(v >= t for v in spoof) / len(spoof)
            print(f"  {t:.2f}  {rp:9.0%}   {sp:9.0%}")
            if best is None or rp - sp > best[1] - best[2]:
                best = (t, rp, sp)
        print(
            f"  best split {best[0]:.2f}: real {best[1]:.0%} pass, spoof {best[2]:.0%} pass"
        )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("label", nargs="?", help="real | print | screen | any spoof name")
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--csv", default=os.path.expanduser("~/fas-bench.csv"))
    ap.add_argument("--url", default="http://127.0.0.1:5000/camera/stream")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.report:
        report(args.csv)
    elif args.label:
        record(args.label, args)
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
