"""
Interactive face benchmark on a local camera. Nothing is written to disk:
frames and embeddings live in memory only.

    .venv/bin/python scripts/face_bench.py --engine both --frames 100
    .venv/bin/python scripts/face_bench.py --engine yunet_sface --frames 100 --spoof

Per engine: "enroll" collects 5 good frames of you, then "test" runs N frames
and reports detect/embed/liveness timing, genuine distance vs the threshold,
liveness scores and quality issue counts. --spoof only labels the run: enroll
with your real face, then hold a phone photo in front of the camera during the
test phase (liveness scores should drop and distances may still be low).
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.face import (  # noqa: E402
    FaceModelsMissing,
    create_face_engine,
    quality_issues,
)
from utils.liveness import LivenessUnavailable, PassiveLiveness  # noqa: E402

MODEL_DIR = os.path.join(ROOT, "models", "face")


def pct(values, q):
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def med(values):
    return statistics.median(values) if values else float("nan")


def read_frame(cap):
    ok, frame = cap.read()
    return frame if ok else None


def run_engine(name, cap, liveness, n_frames, enroll_frames, spoof, timeout):
    engine = create_face_engine(name, MODEL_DIR)
    label = "SPOOF" if spoof else "genuine"
    print(f"\n=== {name} ({label}) threshold={engine.threshold:.3f} ===")

    print("Enroll: Lihat ke kamera, diam sebentar...")
    enrolled = []
    idle_ms = []
    deadline = time.monotonic() + timeout
    while len(enrolled) < enroll_frames and time.monotonic() < deadline:
        frame = read_frame(cap)
        if frame is None:
            continue
        t0 = time.perf_counter()
        faces = engine.detect(frame)
        idle_ms.append((time.perf_counter() - t0) * 1000)
        if quality_issues(frame, faces):
            continue
        enrolled.append(engine.embed(frame, faces[0]))
        time.sleep(0.25)
    if len(enrolled) < enroll_frames:
        print("Enroll gagal: wajah bagus tidak cukup (jarak, cahaya, fokus).")
        print(
            f"  detect tanpa wajah bagus: {len(idle_ms)} frame, "
            f"median {med(idle_ms):.1f} ms, p95 {pct(idle_ms, 0.95):.1f} ms"
        )
        return None

    if spoof:
        print("Test: arahkan FOTO di ponsel ke kamera sekarang...")
    else:
        print("Test: Lihat ke kamera, gerakkan kepala sedikit...")
    time.sleep(1.5)

    detect_ms, embed_ms, live_ms, dists, scores = [], [], [], [], []
    issues = {}
    live_pass = 0
    for _ in range(n_frames):
        frame = read_frame(cap)
        if frame is None:
            issues["no_frame"] = issues.get("no_frame", 0) + 1
            continue
        t0 = time.perf_counter()
        faces = engine.detect(frame)
        detect_ms.append((time.perf_counter() - t0) * 1000)
        bad = quality_issues(frame, faces)
        for code in bad:
            issues[code] = issues.get(code, 0) + 1
        if bad:
            continue
        t0 = time.perf_counter()
        is_live, score = liveness.check(frame, faces[0])
        live_ms.append((time.perf_counter() - t0) * 1000)
        scores.append(score)
        live_pass += 1 if is_live else 0
        t0 = time.perf_counter()
        vec = engine.embed(frame, faces[0])
        embed_ms.append((time.perf_counter() - t0) * 1000)
        dists.append(min(engine.distance(vec, e) for e in enrolled))

    return {
        "engine": name,
        "label": label,
        "threshold": engine.threshold,
        "frames": n_frames,
        "good": len(dists),
        "detect": (med(detect_ms), pct(detect_ms, 0.95)),
        "embed": (med(embed_ms), pct(embed_ms, 0.95)),
        "live_ms": (med(live_ms), pct(live_ms, 0.95)),
        "dist": (med(dists), max(dists) if dists else float("nan")),
        "dist_over": sum(1 for d in dists if d > engine.threshold),
        "live_score": (med(scores), min(scores) if scores else float("nan")),
        "live_pass": live_pass,
        "issues": issues,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--engine", choices=["yunet_sface", "dlib", "both"], default="both")
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--enroll-frames", type=int, default=5)
    ap.add_argument("--enroll-timeout", type=float, default=60.0)
    ap.add_argument("--spoof", action="store_true", help="label the run as a spoof attempt")
    args = ap.parse_args()

    try:
        import cv2
    except ImportError:
        print("OpenCV is not installed.")
        return 2
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Kamera {args.camera} tidak bisa dibuka.")
        return 2
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        liveness = PassiveLiveness(MODEL_DIR)
    except LivenessUnavailable as exc:
        print(f"{exc}")
        return 2

    names = ["yunet_sface", "dlib"] if args.engine == "both" else [args.engine]
    results = []
    try:
        for name in names:
            try:
                res = run_engine(
                    name, cap, liveness, args.frames, args.enroll_frames, args.spoof,
                    args.enroll_timeout,
                )
            except FaceModelsMissing as exc:
                print(f"{name}: {exc}")
                continue
            if res:
                results.append(res)
    finally:
        cap.release()

    print("\n=== Ringkasan (ms: median / p95) ===")
    print(
        f"{'engine':12} {'run':8} {'good':>9} {'detect':>13} {'embed':>13} "
        f"{'liveness':>13} {'dist med/max':>14} {'thr':>6} {'>thr':>5} "
        f"{'live med/min':>14} {'live ok':>8}"
    )
    for r in results:
        print(
            f"{r['engine']:12} {r['label']:8} {r['good']:>4}/{r['frames']:<4} "
            f"{r['detect'][0]:>6.1f}/{r['detect'][1]:<6.1f} "
            f"{r['embed'][0]:>6.1f}/{r['embed'][1]:<6.1f} "
            f"{r['live_ms'][0]:>6.1f}/{r['live_ms'][1]:<6.1f} "
            f"{r['dist'][0]:>6.3f}/{r['dist'][1]:<7.3f} {r['threshold']:>6.3f} "
            f"{r['dist_over']:>5} {r['live_score'][0]:>6.2f}/{r['live_score'][1]:<7.2f} "
            f"{r['live_pass']:>8}"
        )
        print(f"  quality issues: {r['issues'] or 'none'}")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
