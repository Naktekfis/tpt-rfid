"""Read-only PN532 card identity, independent of UHF tool presence."""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable, Optional

from .rfid_reader import ScanDebouncer

logger = logging.getLogger(__name__)


def normalize_uid(uid) -> str:
    """Canonical ISO14443A UID; reject malformed values without echoing them."""
    if isinstance(uid, (bytes, bytearray)):
        value = bytes(uid).hex().upper()
    elif isinstance(uid, str):
        value = uid.strip().upper()
    else:
        raise ValueError("NFC UID must be hex text or bytes")
    if len(value) not in (8, 14, 20) or re.fullmatch(r"[0-9A-F]+", value) is None:
        raise ValueError("NFC UID must contain 4, 7 or 10 bytes")
    return value


class NFCReaderMock:
    """Thread-safe event source; simulate_scan represents one explicit tap."""

    mode = "mock"

    def __init__(
        self, absent_timeout: float = 1.0, clock: Callable[[], float] = time.monotonic
    ):
        if absent_timeout <= 0:
            raise ValueError("absent_timeout must be positive")
        self._clock = clock
        self._lock = threading.Lock()
        self._debouncer = ScanDebouncer(absent_timeout, clock)
        self._sequence = 0
        self._event: Optional[dict] = None
        self._listeners = []
        self._connected = True
        self._firmware = None

    def add_listener(self, callback: Callable[[dict], None]) -> None:
        """Callbacks run on the polling thread; they must return promptly."""
        with self._lock:
            self._listeners.append(callback)

    def latest_event(self, after_sequence: int = 0) -> Optional[dict]:
        with self._lock:
            if self._event is None or self._sequence <= after_sequence:
                return None
            return dict(self._event)

    def status(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "connected": self._connected,
                "sequence": self._sequence,
                "firmware": self._firmware,
            }

    def _publish(self, uid: str, debounce: bool = False) -> Optional[dict]:
        with self._lock:
            if debounce and not self._debouncer.update([uid]):
                return None
            self._sequence += 1
            event = {
                "sequence": self._sequence,
                "uid": uid,
                "observed_at": self._clock(),
            }
            self._event = event
            listeners = list(self._listeners)
        for callback in listeners:
            try:
                callback(dict(event))
            except Exception:  # listener boundary; never log card values
                logger.error("NFC event listener failed")
        return dict(event)

    def simulate_scan(self, uid) -> dict:
        return self._publish(normalize_uid(uid))

    def set_present(self, uid) -> Optional[dict]:
        """Feed one mock polling observation (None means no card)."""
        if uid is None:
            with self._lock:
                self._debouncer.update([])
            return None
        return self._publish(normalize_uid(uid), debounce=True)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class PN532Reader(NFCReaderMock):
    """Reconnectable I2C poller. Only firmware, SAM and passive UID commands."""

    mode = "pn532"

    def __init__(
        self,
        absent_timeout: float = 1.0,
        retry_delay: float = 3.0,
        poll_timeout: float = 0.5,
        device_factory: Optional[Callable] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        super().__init__(absent_timeout, clock)
        if retry_delay <= 0 or poll_timeout <= 0:
            raise ValueError("NFC polling and retry intervals must be positive")
        self.retry_delay = retry_delay
        self.poll_timeout = poll_timeout
        self._device_factory = device_factory or self._open_device
        self._connected = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()

    @staticmethod
    def _open_device():
        # Optional imports: mocks run without GPIO or CircuitPython libraries.
        import board
        import busio
        from adafruit_pn532.i2c import PN532_I2C

        bus = busio.I2C(board.SCL, board.SDA)
        try:
            return PN532_I2C(bus, address=0x24, debug=False), bus
        except Exception:  # resource boundary: construction may fail in driver
            bus.deinit()
            raise

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="pn532-reader", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop.set()
            if self._thread and self._thread is not threading.current_thread():
                self._thread.join(timeout=self.poll_timeout + 3)

    def poll_once(self, device) -> Optional[dict]:
        return self.set_present(device.read_passive_target(timeout=self.poll_timeout))

    def simulate_scan(self, uid) -> dict:
        raise RuntimeError("Mock scans are disabled for the real NFC reader")

    def _run(self) -> None:
        while not self._stop.is_set():
            bus = None
            try:
                device, bus = self._device_factory()
                firmware = tuple(device.firmware_version)
                if not firmware or firmware[0] != 0x32:
                    raise RuntimeError("Reader firmware is not PN532")
                device.SAM_configuration()
                with self._lock:
                    self._firmware = firmware
                    self._connected = True
                while not self._stop.is_set():
                    self.poll_once(device)
                    # Bound CPU use when the reader answers immediately.
                    self._stop.wait(0.02)
            except (OSError, RuntimeError, ValueError, ImportError) as error:
                logger.warning("NFC reader unavailable (%s)", type(error).__name__)
            except Exception:  # background thread boundary
                logger.error("Unexpected NFC reader failure")
            finally:
                with self._lock:
                    self._connected = False
                    self._firmware = None
                if bus is not None:
                    try:
                        bus.deinit()
                    except Exception:  # driver cleanup boundary
                        logger.error("NFC I2C cleanup failed")
            self._stop.wait(self.retry_delay)


def create_nfc_reader(enabled: bool = False, **kwargs):
    """Construct a reader without starting any hardware access."""
    if enabled:
        return PN532Reader(**kwargs)
    return NFCReaderMock(
        absent_timeout=kwargs.get("absent_timeout", 1.0),
        clock=kwargs.get("clock", time.monotonic),
    )
