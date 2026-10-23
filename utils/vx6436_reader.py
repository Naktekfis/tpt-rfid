"""Separate VX6436 driver candidate, restricted to injected test transports.

No production serial opener until physical/firmware acceptance is recorded.
Never inherit VX6336Reader: it writes persistent beep settings at startup.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from . import vx6436
from .rfid_diagnostics import RoundDiagnostics
from .rfid_reader import ScanDebouncer, _ScanState

logger = logging.getLogger(__name__)


class VX6436Reader(_ScanState):
    mode = "vx6436"

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        addr: int = 0,
        absent_timeout: float = 2.5,
        scan_duration: float = 30.0,
        retry_delay: float = 3.0,
        serial_factory: Optional[Callable[[], object]] = None,
    ):
        super().__init__(scan_duration)
        vx6436.reader_info_command(addr)  # validate before any transport access
        self.port, self.addr = port, addr
        self.retry_delay = retry_delay
        self._serial_factory = serial_factory
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.debouncer = ScanDebouncer(absent_timeout)
        self.reader_info: Optional[vx6436.ReaderInfo] = None
        self.connected = False
        self.response_timeout = 26.0  # accommodate maximum stored scan time
        self._diagnostics = RoundDiagnostics()

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "port": self.port,
            "connected": self.connected,
            "hardware_validated": False,
            "buzzer_supported": False,
            "transport": "test" if self._serial_factory else "blocked",
            "scan_time_ms": self.reader_info.scan_time * 100
            if self.reader_info
            else None,
        }

    def diagnostics(self) -> dict:
        return {
            **self.status(),
            "response_timeout_s": self.response_timeout,
            **self._diagnostics.snapshot(),
        }

    def start(self) -> None:
        if self._serial_factory is None:
            raise RuntimeError(
                "VX6436 hardware is not validated; only injected test transport "
                "is supported. See docs/hardware/vx6436/README.md"
            )
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="vx6436-test", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.response_timeout + 1)

    def beep(self, active: int = 2, silent: int = 2, times: int = 3) -> None:
        logger.warning("VX6436 alarm buzzer unavailable; no command sent")

    def _run(self) -> None:
        while not self._stop.is_set():
            ser = None
            try:
                ser = self._serial_factory()
                responses = self._transact(ser, vx6436.reader_info_command(self.addr))
                if len(responses) != 1:
                    raise vx6436.ProtocolError("Missing VX6436 reader info")
                self.reader_info = vx6436.parse_reader_info(responses[0])
                self.response_timeout = self.reader_info.scan_time / 10 + 0.5
                self.connected = True
                while not self._stop.is_set():
                    self.poll_once(ser)
            except (OSError, vx6436.ProtocolError):
                logger.warning("VX6436 test transport unavailable", exc_info=True)
            except Exception:
                logger.exception("VX6436 reader thread error")
            finally:
                self.connected = False
                if ser is not None:
                    try:
                        ser.close()
                    except OSError:
                        logger.warning("VX6436 transport close failed", exc_info=True)
            self._stop.wait(self.retry_delay)

    def _transact(self, ser, command: bytes) -> list:
        splitter = vx6436.FrameSplitter()
        ser.reset_input_buffer()
        if ser.write(command) != len(command):
            raise OSError("Short VX6436 command write")
        responses = []
        deadline = time.monotonic() + self.response_timeout
        while time.monotonic() < deadline and not self._stop.is_set():
            chunk = ser.read(ser.in_waiting or 1)
            for response in splitter.feed(chunk):
                if response.addr != self.addr or response.cmd != command[2]:
                    continue
                responses.append(response)
                if response.status != vx6436.STATUS_MORE:
                    # Dropped bytes could hide one of the inventory fragments.
                    if splitter.dropped:
                        raise vx6436.ProtocolError("Corrupt VX6436 transaction")
                    return responses
        return responses  # poll_once rejects an unterminated continuation

    def poll_once(self, ser) -> list:
        started = time.monotonic()
        sample = dict(
            started=started,
            inventory=0.0,
            listeners=0.0,
            queued_commands=0.0,
            listener_errors=0,
            error=True,
            no_response=False,
            incomplete=False,
            skipped_presence=True,
        )
        try:
            responses = self._transact(ser, vx6436.inventory_command(self.addr))
            sample["inventory"] = time.monotonic() - started
            sample["no_response"] = not responses
            complete = bool(responses) and (
                all(r.status == vx6436.STATUS_MORE for r in responses[:-1])
                and responses[-1].status == vx6436.STATUS_DONE
                or len(responses) == 1
                and responses[0].status == vx6436.STATUS_NO_TAG
            )
            if not complete:
                sample["incomplete"] = bool(responses)
                return []
            tags = [tag for r in responses for tag in vx6436.inventory_tags(r)]
            epcs = list(dict.fromkeys(tag.epc for tag in tags))
            listener_start = time.monotonic()
            sample["listener_errors"] = self._emit_round(epcs)
            sample["listeners"] = time.monotonic() - listener_start
            sample["skipped_presence"] = False
            new = self.debouncer.update(epcs)
            for epc in new:
                self.report(epc)
            sample["error"] = False
            return new
        finally:
            sample["finished"] = time.monotonic()
            sample["total"] = sample["finished"] - started
            self._diagnostics.record(sample)
