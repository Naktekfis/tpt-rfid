"""
Check that the HW-VX6336 reader answers and reads tags. Read-only: sends only
Get Reader Info (0x21) and Inventory (0x01), never writes reader settings.
Stop the app first; only one program can hold the serial port.

  .venv/bin/python scripts/rfid_probe.py [port] [--addr 0x00] [--raw]

Prints the reader info, then one line per inventory round that sees tags.
Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Tuple

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("port", nargs="?", default="/dev/ttyUSB0")
    parser.add_argument("--addr", type=lambda s: int(s, 0), default=None)
    parser.add_argument("--raw", action="store_true", help="print raw frames")
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

        print("\nInventory loop. Tap a tag; Ctrl+C to stop.")
        rounds = empty = 0
        seen = {}
        try:
            while True:
                t0 = time.monotonic()
                responses, _ = transact(
                    ser, vx6336.inventory_command(addr), vx6336.CMD_INVENTORY, args.raw
                )
                ms = (time.monotonic() - t0) * 1000
                rounds += 1
                if not responses:
                    print(f"[{rounds}] no answer ({ms:.0f} ms)")
                    continue
                epcs: List[str] = []
                for r in responses:
                    epcs.extend(vx6336.inventory_epcs(r))
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
        print(f"\n{rounds} rounds. Tags seen:")
        for epc, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            print(f"  {epc}  x{n}")
        if not seen:
            print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
