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

--challenge runs the head-turn check instead (YuNet only), once per
direction, and prints the yaw range it saw. With --spoof, hold the phone photo
and try to pass it by tilting or turning the phone.
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
    sharpness,
)
from utils.liveness import (  # noqa: E402
    HeadTurnChallenge,
    LivenessUnavailable,
    PassiveLiveness,
)

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


# --show: a mirrored preview window with the faces and the current numbers.
SHOW = False
WINDOW = "face_bench (q = berhenti)"


class Quit(Exception):
    pass


def show(frame, faces=(), lines=(), color=(255, 255, 255)):
    """Draw on a mirrored copy (feels like a mirror); raw frame is untouched."""
    if not SHOW or frame is None:
        return
    import cv2

    img = cv2.flip(frame, 1)
    w = img.shape[1]
    for f in faces:
        x, y, bw, bh = f.box
        cv2.rectangle(img, (w - x - bw, y), (w - x, y + bh), (0, 200, 255), 2)
        for px, py in f.landmarks:
            cv2.circle(img, (int(w - px), int(py)), 3, (0, 255, 0), -1)
    for i, text in enumerate(lines):
        org = (10, 28 + 26 * i)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.imshow(WINDOW, img)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        raise Quit()


def pause(cap, seconds, text):
    """Like time.sleep, but keeps the preview live."""
    if not SHOW:
        time.sleep(seconds)
        return
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        show(read_frame(cap), lines=[text])


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
        bad = quality_issues(frame, faces)
        show(
            frame,
            faces,
            [f"ENROLL {name} {len(enrolled)}/{enroll_frames}", ", ".join(bad) or "ok"],
        )
        if bad:
            continue
        enrolled.append(engine.embed(frame, faces[0]))
        pause(cap, 0.25, f"ENROLL {name} {len(enrolled)}/{enroll_frames}")
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
    pause(cap, 1.5, "Siap-siap...")

    detect_ms, embed_ms, live_ms, dists, scores = [], [], [], [], []
    issues = {}
    sharp = []
    live_pass = 0
    for _ in range(n_frames):
        frame = read_frame(cap)
        if frame is None:
            issues["no_frame"] = issues.get("no_frame", 0) + 1
            continue
        t0 = time.perf_counter()
        faces = engine.detect(frame)
        detect_ms.append((time.perf_counter() - t0) * 1000)
        if len(faces) == 1:
            sharp.append(sharpness(frame, faces[0]))
        bad = quality_issues(frame, faces)
        for code in bad:
            issues[code] = issues.get(code, 0) + 1
        if bad:
            show(frame, faces, [f"TEST {name} {label}", ", ".join(bad)], (0, 0, 255))
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
        show(
            frame,
            faces,
            [
                f"TEST {name} {label}",
                f"jarak {dists[-1]:.3f} (batas {engine.threshold:.3f})",
                f"liveness {score:.2f} {'LIVE' if is_live else 'SPOOF'}",
                f"tajam {sharp[-1]:.0f}" if sharp else "",
            ],
            (0, 255, 0) if is_live else (0, 0, 255),
        )

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
        "sharp": (pct(sharp, 0.1), med(sharp)),
    }


# Prompt in the person's own terms; directions are in raw image coordinates
# (see HeadTurnChallenge).
TURN_PROMPT = {"left": "KANAN", "right": "KIRI"}


def run_challenge(cap, liveness, spoof, timeout):
    engine = create_face_engine("yunet_sface", MODEL_DIR)
    label = "SPOOF" if spoof else "genuine"
    results = []
    for direction in ("left", "right"):
        what = "Miringkan/putar FOTO di ponsel" if spoof else "Tengok"
        print(
            f"\n[{label}] Lihat lurus ke kamera, lalu {what} ke {TURN_PROMPT[direction]} Anda..."
        )
        pause(cap, 1.5, f"Lihat lurus, lalu ke {TURN_PROMPT[direction]} Anda")
        ch = HeadTurnChallenge(direction, timeout=timeout)
        yaws = []
        while ch.update(None) == "pending":
            frame = read_frame(cap)
            if frame is None:
                continue
            faces = engine.detect(frame)
            lm = faces[0].landmarks if len(faces) == 1 else None
            lines = [f"{label}: tengok ke {TURN_PROMPT[direction]} Anda"]
            if lm is not None:
                yaws.append(HeadTurnChallenge.yaw(lm))
                _, score = liveness.check(frame, faces[0])
                lines += [
                    f"yaw {yaws[-1]:+.2f} (perlu {'-' if direction == 'left' else '+'}{ch.yaw_threshold})",
                    f"liveness {score:.2f}",
                ]
            else:
                lines.append(f"wajah: {len(faces)}")
            state = ch.update(lm)
            lines.append(f"status: {state}")
            show(
                frame,
                faces,
                lines,
                (0, 255, 0) if state == "passed" else (255, 255, 255),
            )
        pause(cap, 1.5, f"hasil: {ch.state}")
        print(f"  hasil: {ch.state}")
        results.append((direction, ch.state, yaws))
    print("\n=== Head-turn (yaw = (nose_x - eyes_mid_x) / eye_dist) ===")
    for direction, state, yaws in results:
        lo = min(yaws) if yaws else float("nan")
        hi = max(yaws) if yaws else float("nan")
        print(
            f"{label:8} {direction:5} ({TURN_PROMPT[direction]:5}) {state:8} "
            f"frames={len(yaws):3} yaw min/max {lo:+.2f}/{hi:+.2f}"
        )
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--engine", choices=["yunet_sface", "dlib", "both"], default="both")
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--enroll-frames", type=int, default=5)
    ap.add_argument("--enroll-timeout", type=float, default=60.0)
    ap.add_argument(
        "--spoof", action="store_true", help="label the run as a spoof attempt"
    )
    ap.add_argument("--challenge", action="store_true", help="head-turn check instead")
    ap.add_argument("--challenge-timeout", type=float, default=8.0)
    ap.add_argument("--show", action="store_true", help="preview window (q = quit)")
    args = ap.parse_args()
    global SHOW
    SHOW = args.show

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

    if args.challenge:
        try:
            return run_challenge(cap, liveness, args.spoof, args.challenge_timeout)
        except Quit:
            return 1
        finally:
            cap.release()
            if SHOW:
                cv2.destroyAllWindows()

    names = ["yunet_sface", "dlib"] if args.engine == "both" else [args.engine]
    results = []
    try:
        for name in names:
            try:
                res = run_engine(
                    name,
                    cap,
                    liveness,
                    args.frames,
                    args.enroll_frames,
                    args.spoof,
                    args.enroll_timeout,
                )
            except FaceModelsMissing as exc:
                print(f"{name}: {exc}")
                continue
            if res:
                results.append(res)
    except Quit:
        print("Dihentikan (q).")
    finally:
        cap.release()
        if SHOW:
            import cv2

            cv2.destroyAllWindows()

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
        print(
            f"  sharpness p10/median: {r['sharp'][0]:.0f}/{r['sharp'][1]:.0f} (blurry < 60)"
        )
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
