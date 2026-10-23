"""Standalone one-tag placement probe; only 01, 0F and 21 may be transmitted.

No app/config/package imports. Identifiers exist only transiently in RAM.
ENTER at placement is a human marker, not an optical placement sensor.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import select
import statistics
import sys
import time
from pathlib import Path
from typing import NamedTuple


def load_protocol():
    spec = importlib.util.spec_from_file_location(
        "acquisition_protocol", Path(__file__).resolve().parents[1] / "utils/vx6336.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = load_protocol()
ALLOWED = frozenset((0x01, 0x0F, 0x21))


class Round(NamedTuple):
    start: float
    end: float
    hits: tuple  # (monotonic arrival time, ephemeral EPC) pairs
    statuses: tuple
    complete: bool
    damaged_bytes: int
    received_bytes: int = 0


class ProbeFault(RuntimeError):
    pass


def transact(port, cmd, timeout=27.0, tick=lambda: None, clock=time.monotonic):
    """One outstanding command; timeout is fatal to the session (no retry).

    Never flush unread input or send a subsequent command after partial/late
    responses. A response is timed at complete CRC-validated frame arrival.
    The port must have a short, bounded read timeout (CLI: 10 ms).
    """
    if cmd not in ALLOWED:
        raise ValueError("command outside acquisition allowlist")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    splitter = protocol.FrameSplitter()
    start = clock()
    command = protocol.build_command(cmd)
    if port.write(command) != len(command):
        raise ProbeFault("short serial write; stop session")
    hits, statuses = [], []
    received_bytes = 0
    while clock() - start < timeout:
        tick()
        chunk = port.read(min(port.in_waiting or 1, 256))
        received_bytes += len(chunk)
        now = clock()
        for response in splitter.feed(chunk):
            if response.cmd != cmd or response.addr != 0:
                raise ProbeFault(
                    f"Respons tidak sesuai: dikirim cmd={cmd:02X}/addr=00, "
                    f"diterima cmd={response.cmd:02X}/addr={response.addr:02X}."
                )
            statuses.append(response.status)
            if cmd in (0x01, 0x0F):
                if response.status not in protocol.INVENTORY_DATA_STATUSES | {0xFB}:
                    raise ProbeFault(
                        f"Reader menjawab status error {response.status:02X} pada cmd={cmd:02X}."
                    )
                if response.status in protocol.INVENTORY_DATA_STATUSES:
                    # Reject malformed/trailing/zero-length EPC payloads.
                    data = response.data
                    if not data:
                        raise ProbeFault(
                            f"Respons cmd={cmd:02X}, status={response.status:02X} tanpa byte jumlah tag."
                        )
                    pos = 1
                    for _ in range(data[0]):
                        if pos >= len(data) or not data[pos]:
                            raise ProbeFault(
                                f"Panjang tag tidak valid pada cmd={cmd:02X}, status={response.status:02X}."
                            )
                        pos += 1 + data[pos]
                    if pos != len(data):
                        raise ProbeFault(
                            f"Format inventory tidak sesuai: cmd={cmd:02X}, status={response.status:02X}, "
                            f"payload_bytes={len(data)}, parsed_bytes={pos}."
                        )
                    hits.extend((now, epc) for epc in protocol.inventory_epcs(response))
            else:
                info = protocol.parse_reader_info(response)
                return info
            if response.status != protocol.STATUS_INVENTORY_MORE:
                return Round(
                    start,
                    now,
                    tuple(hits),
                    tuple(statuses),
                    True,
                    splitter.dropped,
                    received_bytes,
                )
    return Round(
        start,
        clock(),
        tuple(hits),
        tuple(statuses),
        False,
        splitter.dropped,
        received_bytes,
    )


def round_diagnostic(r):
    statuses = ",".join(f"{s:02X}" for s in r.statuses) or "tidak ada"
    return (
        f"durasi={r.end - r.start:.3f}s, bytes_masuk={r.received_bytes}, "
        f"frame_valid={len(r.statuses)}, status={statuses}, "
        f"terminal_lengkap={r.complete}, bytes_rusak={r.damaged_bytes}"
    )


def summarize(rounds, marker, window, cmd, distance, trial, pre_marker_first_hit=None):
    """Include leading/trailing silence and censored no-hit attempts.

    Read-rate denominator includes every round overlapping the marked window,
    even no-hit and unfinished rounds. Boundary-spanning rounds are counted.
    """
    end = marker + window
    overlap = [r for r in rounds if r.end >= marker and r.start < end]
    hits = sorted({t for r in overlap for t, _ in r.hits if marker <= t <= end})
    seen = {epc for r in overlap for t, epc in r.hits if marker <= t <= end}
    hit_rounds = sum(any(marker <= t <= end for t, _ in r.hits) for r in overlap)
    boundaries = [marker] + hits + [end]
    return {
        "command": f"{cmd:02X}",
        "distance_cm": distance,
        "trial": trial,
        "window_s": window,
        "marker_monotonic_s": marker,
        "pre_marker_detected": pre_marker_first_hit is not None,
        "first_detection_relative_marker_ms": (
            (pre_marker_first_hit - marker) * 1000
            if pre_marker_first_hit is not None
            else (hits[0] - marker) * 1000
            if hits
            else None
        ),
        "first_hit_ms": (hits[0] - marker) * 1000
        if hits and pre_marker_first_hit is None
        else None,
        "censored": not hits and pre_marker_first_hit is None,
        "rounds": len(overlap),
        "hit_rounds": hit_rounds,
        "read_rate": hit_rounds / len(overlap) if overlap else None,
        "longest_silence_s": max(b - a for a, b in zip(boundaries, boundaries[1:])),
        "incomplete_rounds": sum(not r.complete for r in overlap),
        "damaged_bytes": sum(r.damaged_bytes for r in overlap),
        "single_tag_valid": len(seen) <= 1,
        "status_counts": {
            f"{s:02X}": sum(r.statuses.count(s) for r in overlap)
            for s in sorted({s for r in overlap for s in r.statuses})
        },
    }


def aggregate(results):
    groups = []
    for distance in sorted({r["distance_cm"] for r in results}):
        for cmd in ("01", "0F"):
            rows = [
                r
                for r in results
                if r["distance_cm"] == distance and r["command"] == cmd
            ]
            if not rows:
                continue
            valid = [
                r
                for r in rows
                if r["single_tag_valid"]
                and not r["incomplete_rounds"]
                and not r["damaged_bytes"]
            ]
            times = [r["first_hit_ms"] for r in valid if r["first_hit_ms"] is not None]
            rounds = sum(r["rounds"] for r in valid)
            groups.append(
                {
                    "distance_cm": distance,
                    "command": cmd,
                    "attempts": len(rows),
                    "valid_attempts": len(valid),
                    "invalid_attempts": len(rows) - len(valid),
                    "pre_marker_attempts": sum(r["pre_marker_detected"] for r in valid),
                    "acquisition_valid_attempts": sum(
                        not r["pre_marker_detected"] for r in valid
                    ),
                    "failed_acquisitions": sum(r["censored"] for r in valid),
                    "first_hit_median_ms_successes_only": statistics.median(times)
                    if times
                    else None,
                    "first_hit_max_ms_successes_only": max(times) if times else None,
                    "read_rate": sum(r["hit_rounds"] for r in valid) / rounds
                    if rounds
                    else None,
                    "longest_silence_s": max(
                        (r["longest_silence_s"] for r in valid), default=None
                    ),
                }
            )
    return groups


def placement_trial(port, cmd, distance, trial, window, timeout):
    print(
        f"\n=== KETINGGIAN {distance} cm | mode {cmd:02X} | pasangan ke-{trial} ===",
        flush=True,
    )
    input("1/3 JAUHKAN tag sekitar 1 meter. Setelah tag jauh, tekan ENTER: ")
    print("Memeriksa area kosong selama minimal 2 detik. Tag tetap jauh...", flush=True)
    empty_since = time.monotonic()
    baseline_deadline = empty_since + 30
    warned = False
    while time.monotonic() - empty_since < 2:
        if time.monotonic() >= baseline_deadline:
            raise ProbeFault(
                "Area belum kosong selama 2 detik berturut-turut dalam 30 detik. "
                "Masih ada tag di jangkauan; penempatan uji belum dimulai."
            )
        r = transact(port, cmd, timeout)
        if not r.complete or r.damaged_bytes:
            raise ProbeFault("Pemeriksaan area kosong gagal: " + round_diagnostic(r))
        if r.hits:
            empty_since = r.end
            if not warned:
                warned = True
                print(
                    "MASIH ADA TAG TERBACA. Jauhkan lagi tag uji dan tag lain dari reader.\n"
                    "Saya menunggu area kosong 2 detik; jangan tekan ENTER atau menempatkan tag dulu.",
                    flush=True,
                )
    print(
        f"2/3 SIAP: pindahkan tag langsung ke {distance} cm.\n"
        "Bila memungkinkan, geser dari samping pada ketinggian yang sama.\n"
        "Tekan ENTER saat tag sampai di posisi itu. Jika terbaca lebih awal, tes tetap lanjut.",
        flush=True,
    )
    marker = None
    last_remaining = None

    def tick():
        nonlocal marker, last_remaining
        if marker is None and select.select([sys.stdin], [], [], 0)[0]:
            if not sys.stdin.readline():
                raise ProbeFault("stdin closed")
            marker = time.monotonic()
            print(
                f"3/3 DIAMKAN tag di {distance} cm selama {window:g} detik. Jangan tekan ENTER lagi.\n"
                f"MARK {marker:.6f}",
                flush=True,
            )
        if marker is not None:
            remaining = max(0, math.ceil(marker + window - time.monotonic()))
            if remaining != last_remaining:
                last_remaining = remaining
                message = f"Tahan tag... sisa {remaining} detik."
                if remaining == 0:
                    message = "Waktu pengamatan habis; tunggu respons terakhir sebelum memindahkan tag."
                print(message, flush=True)

    rounds = []
    pre_marker_first_hit = None
    observed_epcs = set()
    while marker is None or time.monotonic() < marker + window:
        r = transact(port, cmd, timeout, tick)
        observed_epcs.update(epc for _, epc in r.hits)
        early = [t for t, _ in r.hits if marker is None or t < marker]
        if early and pre_marker_first_hit is None:
            pre_marker_first_hit = min(early)
            print(
                "Tag sudah terbaca saat dipindahkan. Tes tetap lanjut.\n"
                "Tempatkan pada ketinggian tujuan lalu tekan ENTER; tangkapan awal diberi label sebelum ENTER.",
                flush=True,
            )
        if marker is not None:
            rounds.append(r)
        if not r.complete or r.damaged_bytes:
            if marker is not None:
                print(
                    json.dumps(
                        summarize(
                            rounds,
                            marker,
                            window,
                            cmd,
                            distance,
                            trial,
                            pre_marker_first_hit,
                        )
                    ),
                    flush=True,
                )
            raise ProbeFault("Respons saat pengamatan gagal: " + round_diagnostic(r))
    result = summarize(
        rounds, marker, window, cmd, distance, trial, pre_marker_first_hit
    )
    result["single_tag_valid"] = len(observed_epcs) <= 1
    first = result["first_hit_ms"]
    outcome = (
        "sudah terbaca sebelum ENTER; waktu akuisisi di posisi tujuan belum dapat diukur"
        if result["pre_marker_detected"]
        else f"tangkapan pertama {first:.1f} ms"
        if first is not None
        else f"tidak terbaca dalam {window:g} detik"
    )
    print(
        f"SELESAI {distance} cm / {cmd:02X}: {outcome}. Tag sekarang boleh dijauhkan.",
        flush=True,
    )
    print(json.dumps(result), flush=True)
    if not result["single_tag_valid"]:
        raise ProbeFault("multiple tags detected; discard trial and restart")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/rfid-reader")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--window", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=27.0)
    args = parser.parse_args()
    if args.trials < 1 or not all(
        math.isfinite(x) and x > 0 for x in (args.window, args.timeout)
    ):
        parser.error("trials/window/timeout must be positive and finite")
    if args.timeout < 27:
        parser.error("timeout must be >=27 s for unknown ScanTime up to 25.5 s")
    if not sys.stdin.isatty():
        parser.error("interactive terminal required for placement marker")
    import serial  # lazy: tests/help never open hardware or import application

    results = []
    try:
        # TIOCEXCL-style ownership among cooperating processes; operator must
        # stop app and verify no existing owner before opening this port.
        with serial.Serial(
            args.port, 57600, timeout=0.01, write_timeout=1, exclusive=True
        ) as port:
            if port.in_waiting:
                raise ProbeFault("unexpected buffered input; stop, do not flush")
            info = transact(port, 0x21, args.timeout)
            if isinstance(info, Round):
                raise ProbeFault(
                    "Get Reader Info gagal; inventory tidak dikirim: "
                    + round_diagnostic(info)
                )
            print(
                json.dumps(
                    {
                        "firmware": list(info.version),
                        "power_dbm": info.power,
                        "scan_time_ms": info.scan_time * 100,
                        "frequency_raw": [info.max_freq, info.min_freq],
                        "marker": "human ENTER; includes placement/keyboard uncertainty",
                    }
                )
            )
            print(
                "\nUJI SATU TAG: 10, 20, lalu 30 cm. Gunakan tag dan orientasi yang sama.\n"
                f"Setiap ketinggian: {args.trials} pasangan mode 01/0F.\n"
                "ENTER pertama = tag sudah jauh. ENTER kedua = tag baru sampai di posisi uji.\n"
                "Ikuti langkah 1/3, 2/3, 3/3 pada setiap percobaan.",
                flush=True,
            )
            for distance in (10, 20, 30):
                for trial in range(1, args.trials + 1):
                    # AB / BA alternation limits order bias across paired attempts.
                    for cmd in (0x01, 0x0F) if trial % 2 else (0x0F, 0x01):
                        results.append(
                            placement_trial(
                                port, cmd, distance, trial, args.window, args.timeout
                            )
                        )
    except (ProbeFault, protocol.ProtocolError, serial.SerialException, OSError) as exc:
        print(
            f"UJI DIHENTIKAN [{type(exc).__name__}]: {exc}\n"
            "Tidak ada retry atau perintah berikutnya. Simpan pesan ini untuk diagnosis.",
            file=sys.stderr,
        )
        return 2
    except (KeyboardInterrupt, EOFError):
        print(
            "STOP: operator ended session; outstanding reply may still be pending.",
            file=sys.stderr,
        )
        return 130
    finally:
        print(json.dumps({"comparison": aggregate(results)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
