"""
Check that the HW-VX6336 reader answers and reads tags. Read-only: sends only
Get Reader Info (0x21), Inventory (0x01/0x0F), and on request the one-shot
buzzer (0x33) or the beep mode (0x35, the only stored setting it can write). Stop the app first; only one program can
hold the serial port.

  .venv/bin/python scripts/rfid_probe.py [port] [--addr 0x00] [--raw]
      [--beep ACTIVE,SILENT,TIMES] [--beep-mode read|off|on] [--single] [--duration S] [--stats] [--quiet]

Prints the reader info, then one line per inventory round that sees tags.
Ctrl+C or --duration stops. --stats adds, per EPC, the read rate and the
longest gap between reads (sets RFID_MISSING_AFTER), plus tags and frames
per round. --beep sends one 0x33 (units of 50 ms) and exits. --single polls
with Inventory (Single) 0x0F instead of 0x01. --beep-mode reads or sets
whether the reader beeps on every tag read (stored; factory = on) and exits.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import vx6336  # noqa: E402

TIMEOUT = 1.5  # s; an inventory round lasts up to ScanTime (default 1 s)


def transact(
    ser, command: bytes, expect_cmd: int, raw: bool
) -> Tuple[List[vx6336.Response], bytes]:
    splitter = vx6336.FrameSplitter()
    ser.reset_input_buffer()
    if raw:
        print(f"  -> {command.hex(' ')}")
    ser.write(command)
    responses: List[vx6336.Response] = []
    received = b""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue
        received += chunk
        for r in splitter.feed(chunk):
            if r.cmd != expect_cmd:
                continue
            responses.append(r)
            if r.status != vx6336.STATUS_INVENTORY_MORE:
                if raw:
                    print(f"  <- {received.hex(' ')}")
                return responses, received
    if raw and received:
        print(f"  <- {received.hex(' ')} (incomplete)")
    return responses, received


def probe_info(ser, addr: int, raw: bool) -> bool:
    print(f"Get Reader Info (addr 0x{addr:02X})...")
    responses, received = transact(
        ser, vx6336.reader_info_command(addr), vx6336.CMD_GET_READER_INFO, raw
    )
    if not responses:
        if received:
            print(f"  Bytes arrived but no valid frame: {received.hex(' ')}")
            print("  Wrong baud rate? This reader talks 57600 8N1.")
        else:
            print("  No answer.")
        return False
    r = responses[0]
    if r.status != vx6336.STATUS_SUCCESS:
        print(f"  Reader answered with status 0x{r.status:02X}")
        return True
    info = vx6336.parse_reader_info(r)
    print(f"  Reader address : 0x{r.addr:02X}")
    print(f"  Firmware       : {info.version[0]}.{info.version[1]}")
    print(f"  Type           : 0x{info.reader_type:02X}")
    print(f"  Protocols      : 0x{info.protocols:02X}")
    print(f"  Freq (raw)     : max 0x{info.max_freq:02X}, min 0x{info.min_freq:02X}")
    print(f"  Power          : {info.power} dBm")
    print(f"  ScanTime       : {info.scan_time * 100} ms")
    return True


class Stats:
    def __init__(self) -> None:
        self.start = time.monotonic()
        self.rounds = 0
        self.round_ms: List[float] = []
        self.frames: Dict[int, int] = {}  # frames per round -> rounds
        self.tags: Dict[int, int] = {}  # tags per round -> rounds
        self.statuses: Dict[int, int] = {}
        self.count: Dict[str, int] = {}
        self.first_round: Dict[str, int] = {}
        self.last: Dict[str, float] = {}
        self.gap: Dict[str, float] = {}

    def add(self, now: float, ms: float, responses, epcs: List[str]) -> None:
        self.rounds += 1
        self.round_ms.append(ms)
        self.frames[len(responses)] = self.frames.get(len(responses), 0) + 1
        for r in responses:
            self.statuses[r.status] = self.statuses.get(r.status, 0) + 1
        unique = set(epcs)
        self.tags[len(unique)] = self.tags.get(len(unique), 0) + 1
        for epc in unique:
            self.count[epc] = self.count.get(epc, 0) + 1
            if epc in self.last:
                self.gap[epc] = max(self.gap.get(epc, 0.0), now - self.last[epc])
            else:
                self.first_round[epc] = self.rounds
            self.last[epc] = now

    def report(self) -> None:
        now = time.monotonic()
        secs = now - self.start
        ms = sorted(self.round_ms) or [0.0]
        print(f"\n--- stats: {self.rounds} rounds in {secs:.1f} s")
        print(
            f"round ms: median {ms[len(ms) // 2]:.0f}, max {ms[-1]:.0f}; "
            f"rounds/s {self.rounds / secs if secs else 0:.1f}"
        )
        fmt = ", ".join
        print(
            "frames/round: " + fmt(f"{k}:{v}" for k, v in sorted(self.frames.items()))
        )
        print("tags/round:   " + fmt(f"{k}:{v}" for k, v in sorted(self.tags.items())))
        print(
            "statuses:     "
            + fmt(f"0x{k:02X}:{v}" for k, v in sorted(self.statuses.items()))
        )
        print(f"{len(self.count)} EPCs (rate = rounds seen / rounds since first seen):")
        for epc in sorted(self.count, key=lambda e: self.count[e]):
            since = self.rounds - self.first_round[epc] + 1
            gap = max(self.gap.get(epc, 0.0), now - self.last[epc])
            print(
                f"  {epc}  x{self.count[epc]:<5} rate {self.count[epc] / since:5.1%}"
                f"  longest gap {gap:5.2f} s"
            )


def beep_mode(ser, addr: int, mode: str, raw: bool) -> int:
    if mode != "read":
        value = vx6336.BEEP_MODE_OFF if mode == "off" else vx6336.BEEP_MODE_ON
        responses, _ = transact(
            ser, vx6336.beep_mode_command(value, addr), vx6336.CMD_BEEP_MODE, raw
        )
        if not responses or responses[0].status != vx6336.STATUS_SUCCESS:
            print(f"\nSet beep mode {mode}: failed")
            return 1
    responses, _ = transact(
        ser,
        vx6336.beep_mode_command(vx6336.BEEP_MODE_READ, addr),
        vx6336.CMD_BEEP_MODE,
        raw,
    )
    try:
        on = vx6336.parse_beep_mode(responses[0]) if responses else None
    except vx6336.ProtocolError as e:
        print(f"\nBeep mode: {e}")
        return 1
    if on is None:
        print("\nBeep mode: no answer")
        return 1
    print(f"\nBeep on tag read: {'on' if on else 'off'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("port", nargs="?", default="/dev/ttyUSB0")
    parser.add_argument("--addr", type=lambda s: int(s, 0), default=None)
    parser.add_argument("--raw", action="store_true", help="print raw frames")
    parser.add_argument("--beep", help="send 0x33 ACTIVE,SILENT,TIMES once and exit")
    parser.add_argument(
        "--beep-mode", choices=("read", "off", "on"), help="beep on tag read (0x35)"
    )
    parser.add_argument("--single", action="store_true", help="poll with 0x0F")
    parser.add_argument("--duration", type=float, help="stop after S seconds")
    parser.add_argument("--stats", action="store_true", help="print read statistics")
    parser.add_argument("--quiet", action="store_true", help="no per-round lines")
    args = parser.parse_args()

    try:
        ser = serial.Serial(args.port, vx6336.BAUDRATE, timeout=0.05)
    except serial.SerialException as e:
        print(f"Cannot open {args.port}: {e}")
        print("Check: ls -l /dev/ttyUSB*, user in group dialout, app stopped.")
        return 2

    with ser:
        addrs = (
            [args.addr]
            if args.addr is not None
            else [
                vx6336.DEFAULT_ADDR,
                vx6336.BROADCAST_ADDR,
            ]
        )
        addr = None
        for a in addrs:
            if probe_info(ser, a, args.raw):
                addr = a
                break
        if addr is None:
            print("\nReader does not answer: check the cable, the port, and power.")
            return 1

        if args.beep:
            active, silent, times = (int(v) for v in args.beep.split(","))
            responses, _ = transact(
                ser,
                vx6336.buzzer_command(active, silent, times, addr),
                vx6336.CMD_ACOUSTO_OPTIC,
                args.raw,
            )
            status = f"0x{responses[0].status:02X}" if responses else "no answer"
            print(f"\nBuzzer {active},{silent},{times}: {status}")
            return 0 if responses else 1

        if args.beep_mode:
            return beep_mode(ser, addr, args.beep_mode, args.raw)

        print("\nInventory loop. Tap a tag; Ctrl+C to stop.")
        rounds = empty = 0
        seen = {}
        stats = Stats()
        if args.single:
            inventory = vx6336.inventory_single_command(addr)
            inventory_cmd = vx6336.CMD_INVENTORY_SINGLE
        else:
            inventory = vx6336.inventory_command(addr)
            inventory_cmd = vx6336.CMD_INVENTORY
        end = time.monotonic() + args.duration if args.duration else None
        try:
            while end is None or time.monotonic() < end:
                t0 = time.monotonic()
                responses, _ = transact(ser, inventory, inventory_cmd, args.raw)
                ms = (time.monotonic() - t0) * 1000
                rounds += 1
                if not responses:
                    print(f"[{rounds}] no answer ({ms:.0f} ms)")
                    continue
                epcs: List[str] = []
                for r in responses:
                    epcs.extend(vx6336.inventory_epcs(r))
                stats.add(time.monotonic(), ms, responses, epcs)
                if args.quiet:
                    continue
                if not epcs:
                    empty += 1
                    status = responses[-1].status
                    if empty == 1 or empty % 10 == 0:
                        print(f"[{rounds}] no tag (status 0x{status:02X}, {ms:.0f} ms)")
                    continue
                empty = 0
                for epc in epcs:
                    seen[epc] = seen.get(epc, 0) + 1
                print(f"[{rounds}] {len(epcs)} tag ({ms:.0f} ms): {', '.join(epcs)}")
        except KeyboardInterrupt:
            pass
        if args.stats:
            stats.report()
            return 0
        print(f"\n{rounds} rounds. Tags seen:")
        for epc, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            print(f"  {epc}  x{n}")
        if not seen:
            print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
