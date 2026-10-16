"""
Serial protocol for the HW-VX6336 USB UHF reader (protocol manual v1.2).

Pure functions only: no serial port, no threads. See
.claude/knowledge/RFID_VX6336.md and docs/hardware/vx6336/.

Command frame:  Len Adr Cmd Data[] CRC-LSB CRC-MSB   (Len = len(Data) + 4)
Response frame: Len Adr reCmd Status Data[] CRC-LSB CRC-MSB   (Len = len(Data) + 5)
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

BAUDRATE = 57600
BROADCAST_ADDR = 0xFF
DEFAULT_ADDR = 0x00

CMD_INVENTORY = 0x01
CMD_INVENTORY_SINGLE = 0x0F
CMD_GET_READER_INFO = 0x21
CMD_SET_SCAN_TIME = 0x25
CMD_ACOUSTO_OPTIC = 0x33
CMD_BEEP_MODE = 0x35  # undocumented in manual v1.2, see RFID_VX6336.md

# Only these commands may be built. Everything else (tag writes, kill, lock,
# reader config) can be permanent and is gated, see GATES.md.
SAFE_COMMANDS = frozenset(
    {
        CMD_INVENTORY,
        CMD_INVENTORY_SINGLE,
        CMD_GET_READER_INFO,
        CMD_SET_SCAN_TIME,
        CMD_ACOUSTO_OPTIC,
        CMD_BEEP_MODE,
    }
)

STATUS_SUCCESS = 0x00
STATUS_INVENTORY_DONE = 0x01
STATUS_INVENTORY_TIMEOUT = 0x02
STATUS_INVENTORY_MORE = 0x03
STATUS_INVENTORY_BUFFER_FULL = 0x04
STATUS_NO_TAG = 0xFB

# Statuses whose Data[] carries an inventory result (Num + EPCs).
INVENTORY_DATA_STATUSES = frozenset(
    {
        STATUS_SUCCESS,
        STATUS_INVENTORY_DONE,
        STATUS_INVENTORY_TIMEOUT,
        STATUS_INVENTORY_MORE,
        STATUS_INVENTORY_BUFFER_FULL,
    }
)

BEEP_MODE_READ = 0x00
BEEP_MODE_OFF = 0x80  # write, beep on tag read off (stored in the reader)
BEEP_MODE_ON = 0x81  # write, factory setting
BEEP_MODE_VALUES = frozenset({BEEP_MODE_READ, BEEP_MODE_OFF, BEEP_MODE_ON})

MIN_RESPONSE_LEN = 5  # Len byte value for a response with empty Data[]


class ProtocolError(ValueError):
    """Malformed frame or payload."""


class Response(NamedTuple):
    addr: int
    cmd: int
    status: int
    data: bytes


class ReaderInfo(NamedTuple):
    version: Tuple[int, int]
    reader_type: int
    protocols: int
    max_freq: int
    min_freq: int
    power: int
    scan_time: int  # units of 100 ms


def crc16(data: bytes) -> int:
    """CRC-16, preset 0xFFFF, reflected polynomial 0x8408."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def _with_crc(body: bytes) -> bytes:
    crc = crc16(body)
    return body + bytes((crc & 0xFF, crc >> 8))


def build_command(cmd: int, data: bytes = b"", addr: int = DEFAULT_ADDR) -> bytes:
    """Build a command frame. Refuses commands outside SAFE_COMMANDS."""
    if cmd not in SAFE_COMMANDS:
        raise ValueError(f"Command 0x{cmd:02X} is not allowed")
    if not 0 <= addr <= 0xFF:
        raise ValueError(f"Invalid reader address: {addr}")
    length = len(data) + 4
    if length > 0xFF:
        raise ValueError("Command data too long")
    return _with_crc(bytes((length, addr, cmd)) + bytes(data))


def inventory_command(addr: int = DEFAULT_ADDR) -> bytes:
    return build_command(CMD_INVENTORY, addr=addr)


def inventory_single_command(addr: int = DEFAULT_ADDR) -> bytes:
    return build_command(CMD_INVENTORY_SINGLE, addr=addr)


def reader_info_command(addr: int = DEFAULT_ADDR) -> bytes:
    return build_command(CMD_GET_READER_INFO, addr=addr)


def set_scan_time_command(scan_time: int, addr: int = DEFAULT_ADDR) -> bytes:
    """ScanTime in units of 100 ms, 3..255. The reader stores it persistently."""
    if not 3 <= scan_time <= 255:
        raise ValueError("scan_time must be 3..255 (x100 ms)")
    return build_command(CMD_SET_SCAN_TIME, bytes((scan_time,)), addr=addr)


def buzzer_command(
    active: int, silent: int, times: int, addr: int = DEFAULT_ADDR
) -> bytes:
    """Beep and flash the LED `times` times: on `active` x 50 ms, off `silent` x 50 ms.

    One-shot (protocol 8.4.7), not a stored setting. Each value is 0..255.
    """
    for value in (active, silent, times):
        if not 0 <= value <= 255:
            raise ValueError("buzzer values must be 0..255")
    return build_command(CMD_ACOUSTO_OPTIC, bytes((active, silent, times)), addr=addr)


def beep_mode_command(value: int, addr: int = DEFAULT_ADDR) -> bytes:
    """Read (0x00) or write (0x80 off, 0x81 on) the beep-on-tag-read mode.

    Not in protocol manual v1.2; taken from the UHFReader09-family SDK and
    tested on firmware 2.32. Other values are refused.
    """
    if value not in BEEP_MODE_VALUES:
        raise ValueError("beep mode must be 0x00, 0x80 or 0x81")
    return build_command(CMD_BEEP_MODE, bytes((value,)), addr=addr)


def parse_beep_mode(response: Response) -> bool:
    """True if beep-on-read is on, from the reply to a 0x00 read."""
    if response.cmd != CMD_BEEP_MODE or response.status != STATUS_SUCCESS:
        raise ProtocolError("not a successful beep mode reply")
    if not response.data:
        raise ProtocolError("beep mode reply carries no mode")
    return bool(response.data[0] & 0x01)


def parse_response(frame: bytes) -> Response:
    """Parse one complete response frame (Len byte included) and check its CRC."""
    if len(frame) < MIN_RESPONSE_LEN + 1:
        raise ProtocolError("Frame too short")
    if frame[0] != len(frame) - 1:
        raise ProtocolError(
            f"Len byte {frame[0]} does not match frame size {len(frame)}"
        )
    body, crc_bytes = frame[:-2], frame[-2:]
    expected = crc16(body)
    got = crc_bytes[0] | (crc_bytes[1] << 8)
    if got != expected:
        raise ProtocolError(f"CRC mismatch: got 0x{got:04X}, expected 0x{expected:04X}")
    return Response(
        addr=frame[1], cmd=frame[2], status=frame[3], data=bytes(frame[4:-2])
    )


def parse_epcs(data: bytes) -> List[str]:
    """Parse inventory Data[] (Num, then EPCLen + EPC per tag) into uppercase hex EPCs."""
    if not data:
        return []
    count = data[0]
    epcs = []
    pos = 1
    for _ in range(count):
        if pos >= len(data):
            raise ProtocolError("Inventory data ends before Num tags")
        epc_len = data[pos]
        pos += 1
        epc = data[pos : pos + epc_len]
        if len(epc) != epc_len:
            raise ProtocolError("Inventory data ends inside an EPC")
        epcs.append(epc.hex().upper())
        pos += epc_len
    return epcs


def inventory_epcs(response: Response) -> List[str]:
    """EPCs carried by an inventory response; [] for no tag or other statuses."""
    if response.cmd not in (CMD_INVENTORY, CMD_INVENTORY_SINGLE):
        raise ProtocolError(f"Not an inventory response: cmd 0x{response.cmd:02X}")
    if response.status not in INVENTORY_DATA_STATUSES:
        return []
    return parse_epcs(response.data)


def parse_reader_info(response: Response) -> ReaderInfo:
    if response.cmd != CMD_GET_READER_INFO or response.status != STATUS_SUCCESS:
        raise ProtocolError("Not a successful Get Reader Information response")
    d = response.data
    if len(d) != 8:
        raise ProtocolError(f"Reader info needs 8 data bytes, got {len(d)}")
    return ReaderInfo((d[0], d[1]), d[2], d[3], d[4], d[5], d[6], d[7])


class FrameSplitter:
    """
    Reassemble response frames from a serial byte stream.

    feed() returns every complete frame seen so far. A frame with a bad CRC is
    dropped one byte at a time so the splitter can resync on the next frame.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.dropped = 0

    def feed(self, chunk: bytes) -> List[Response]:
        self._buf.extend(chunk)
        out = []
        while True:
            frame = self._next_frame()
            if frame is None:
                return out
            out.append(frame)

    def reset(self) -> None:
        self._buf.clear()

    def _next_frame(self) -> Optional[Response]:
        while self._buf:
            length = self._buf[0]
            if length < MIN_RESPONSE_LEN:
                del self._buf[0]
                self.dropped += 1
                continue
            if len(self._buf) < length + 1:
                # The head may be garbage claiming a long frame; resync on a
                # complete valid frame further in instead of waiting for it.
                return self._resync()
            raw = bytes(self._buf[: length + 1])
            try:
                response = parse_response(raw)
            except ProtocolError:
                del self._buf[0]
                self.dropped += 1
                continue
            del self._buf[: length + 1]
            return response
        return None

    def _resync(self) -> Optional[Response]:
        for start in range(1, len(self._buf)):
            length = self._buf[start]
            end = start + length + 1
            if length < MIN_RESPONSE_LEN or end > len(self._buf):
                continue
            try:
                response = parse_response(bytes(self._buf[start:end]))
            except ProtocolError:
                continue
            self.dropped += start
            del self._buf[:end]
            return response
        return None
