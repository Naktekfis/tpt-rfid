"""HW-VX6436 v1.10, read-only EPC inventory subset. No hardware IO.

Source/provenance and SDK discrepancies: docs/hardware/vx6436/README.md.
The framing matches VX6336, but inventory and reader-info payloads do not.
"""

from __future__ import annotations

from typing import List, NamedTuple

# These framing primitives are independently confirmed in manual sections 1–3.
# Never reuse VX6336 command builders or payload parsers here.
from .vx6336 import FrameSplitter as FrameSplitter
from .vx6336 import ProtocolError, Response, crc16

BAUDRATE = 57600
DEFAULT_ADDR = 0
CMD_INVENTORY = 0x01
CMD_GET_READER_INFO = 0x21
STATUS_DONE = 0x01
STATUS_MORE = 0x03
STATUS_NO_TAG = 0xFB


class Tag(NamedTuple):
    epc: str
    rssi_raw: int  # Do not claim calibrated dBm; manual gives no conversion.


class ReaderInfo(NamedTuple):
    version: tuple
    reader_type: int
    protocols: int
    max_freq: int
    min_freq: int
    power: int
    scan_time: int
    antenna: int
    beep_enabled: int


def build_command(cmd: int, data: bytes = b"", addr: int = DEFAULT_ADDR) -> bytes:
    """Only two read-only commands; arbitrary payloads are refused as well."""
    if not 0 <= addr <= 0xFE:
        raise ValueError("VX6436 requires an explicit address, 0..254")
    if cmd == CMD_GET_READER_INFO:
        valid = not data
    elif cmd == CMD_INVENTORY:
        valid = len(data) == 2 and 0 <= data[0] <= 15 and 0 <= data[1] <= 3
    else:
        valid = False
    if not valid:
        raise ValueError("Unsupported VX6436 command or payload")
    body = bytes((len(data) + 4, addr, cmd)) + data
    checksum = crc16(body)
    return body + bytes((checksum & 0xFF, checksum >> 8))


def inventory_command(addr: int = DEFAULT_ADDR) -> bytes:
    # §8.2.1: Q=4, Session=S0; omit mask, TID and optional runtime settings.
    return build_command(CMD_INVENTORY, b"\x04\x00", addr)


def reader_info_command(addr: int = DEFAULT_ADDR) -> bytes:
    return build_command(CMD_GET_READER_INFO, addr=addr)


def parse_reader_info(response: Response) -> ReaderInfo:
    d = response.data
    if response.cmd != CMD_GET_READER_INFO or response.status != 0 or len(d) != 12:
        raise ProtocolError("VX6436 reader info requires 12 bytes and success")
    if d[2] != 0x0F or not d[3] & 2 or not 3 <= d[7] <= 255:
        raise ProtocolError("Unexpected VX6436 type, EPC capability or scan time")
    return ReaderInfo((d[0], d[1]), *d[2:10])


def inventory_tags(response: Response) -> List[Tag]:
    if response.cmd != CMD_INVENTORY:
        raise ProtocolError("Not a VX6436 inventory response")
    if response.status == STATUS_NO_TAG and not response.data:
        return []
    if response.status not in (STATUS_DONE, 0x02, STATUS_MORE, 0x04):
        raise ProtocolError("Invalid VX6436 inventory status")
    d = response.data
    if len(d) < 2 or d[0] != 1:
        raise ProtocolError("VX6436 inventory needs antenna 1 and count")
    tags = []
    pos = 2
    for _ in range(d[1]):
        if pos >= len(d):
            raise ProtocolError("Missing EPC length")
        length = d[pos]
        pos += 1
        if length == 0 or length % 2 or pos + length >= len(d):
            raise ProtocolError("Invalid/truncated EPC or missing RSSI")
        tags.append(Tag(d[pos : pos + length].hex().upper(), d[pos + length]))
        pos += length + 1
    if pos != len(d):
        raise ProtocolError("Trailing inventory bytes")
    return tags
