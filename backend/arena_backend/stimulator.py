from __future__ import annotations

import os
import struct
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol


VID = 0x10C4
PID = 0xEA61
EP_OUT = 0x02
EP_IN = 0x82


def build_reset_packet() -> bytes:
    return bytes.fromhex("f0000000000000000000000000")


def validate_stimulus(current_ma: float, duration_units: int) -> None:
    if not 0.0 <= current_ma <= 4.0:
        raise ValueError("current must be between 0.00 and 4.00 mA")
    if abs(current_ma * 100 - round(current_ma * 100)) > 1e-9:
        raise ValueError("current must use 0.01 mA increments")
    if isinstance(duration_units, bool) or not 0 <= duration_units <= 65535:
        raise ValueError("duration units must be an integer between 0 and 65535")


def build_stimulus_packet(current_ma: float, duration_units: int) -> bytes:
    validate_stimulus(current_ma, duration_units)
    current_units = int(round(current_ma * 100))
    return bytes([0xFF, 0x03, 0x01]) + struct.pack("<H", current_units) + struct.pack("<H", duration_units) + bytes.fromhex("0000dc050000")


class StimulatorDevice(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def send(self, current_ma: float, duration_units: int) -> dict[str, Any]: ...


class UsbShockDevice:
    def __init__(self, settle_seconds: float = 0.05):
        self.settle_seconds = settle_seconds
        self._device: Any | None = None
        self._initialized = False

    @staticmethod
    def _usb_backend():
        try:
            import libusb_package
            return libusb_package.get_libusb1_backend()
        except ImportError:
            return None

    @staticmethod
    def probe() -> bool:
        import usb.core
        return usb.core.find(idVendor=VID, idProduct=PID, backend=UsbShockDevice._usb_backend()) is not None

    def open(self) -> None:
        import usb.core
        if self._device is None:
            self._device = usb.core.find(idVendor=VID, idProduct=PID, backend=self._usb_backend())
            if self._device is None:
                raise RuntimeError(f"stimulator not found ({VID:04X}:{PID:04X})")
            self._device.set_configuration()

    def close(self) -> None:
        if self._device is not None:
            import usb.util
            usb.util.dispose_resources(self._device)
        self._device = None
        self._initialized = False

    def _read_ack(self, timeout_ms: int) -> str | None:
        import usb.core
        try:
            return bytes(self._device.read(EP_IN, 64, timeout=timeout_ms)).hex()
        except (usb.core.USBTimeoutError, usb.core.USBError):
            return None

    def _initialize(self) -> None:
        if self._initialized:
            return
        self.open()
        for endpoint in (EP_OUT, EP_IN):
            try:
                self._device.clear_halt(endpoint)
            except Exception:
                pass
        while True:
            try:
                self._device.read(EP_IN, 64, timeout=50)
            except Exception:
                break
        for request_type, request, value, index in ((0x40, 0x00, 0xFFFF, 0), (0x40, 0x02, 0x0002, 0), (0x40, 0x02, 0x0001, 0)):
            try:
                self._device.ctrl_transfer(request_type, request, value, index, None, timeout=1000)
            except Exception:
                pass
            time.sleep(self.settle_seconds)
        self._initialized = True

    def send(self, current_ma: float, duration_units: int) -> dict[str, Any]:
        validate_stimulus(current_ma, duration_units)
        self._initialize()
        reset_packet = build_reset_packet()
        stimulus_packet = build_stimulus_packet(current_ma, duration_units)
        self._device.write(EP_OUT, reset_packet, timeout=2000)
        reset_ack = self._read_ack(500)
        time.sleep(self.settle_seconds)
        self._device.write(EP_OUT, stimulus_packet, timeout=2000)
        stimulus_ack = self._read_ack(300)
        return {"resetAck": reset_ack, "stimulusAck": stimulus_ack, "sentAt": time.time()}

    def send_raw(self, packet_hex: str) -> dict[str, Any]:
        self._initialize()
        packet = bytes.fromhex(packet_hex)
        self._device.write(EP_OUT, packet, timeout=2000)
        ack = self._read_ack(300)
        return {"packet": packet_hex, "ack": ack, "sentAt": time.time()}


@dataclass(frozen=True)
class StimulatorStatus:
    connected: bool
    armed: bool
    calibrated: bool
    duration_units_per_second: float | None
    device_id: str = f"{VID:04X}:{PID:04X}"
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class StimulatorController:
    """Thread-safe, fail-closed facade used by the arena backend and UI."""

    def __init__(self, device_factory: Callable[[], StimulatorDevice] = UsbShockDevice, duration_units_per_second: float | None = None):
        configured = os.environ.get("ARENA_SHOCK_DURATION_UNITS_PER_SECOND")
        self._duration_units_per_second = duration_units_per_second if duration_units_per_second is not None else (float(configured) if configured else None)
        self._device_factory = device_factory
        self._device: StimulatorDevice | None = None
        self._armed = False
        self._last_error: str | None = None
        self._lock = threading.RLock()
        self._mock = False

    @property
    def armed(self) -> bool:
        with self._lock:
            return self._armed

    def _probe(self) -> bool:
        if self._mock:
            return True
        if self._device is not None:
            return True
        probe = getattr(self._device_factory, "probe", None)
        return bool(probe()) if callable(probe) else False

    def status(self) -> StimulatorStatus:
        with self._lock:
            try:
                connected = self._probe()
                self._last_error = None
            except Exception as exc:
                connected = False
                self._last_error = str(exc)
            calibrated = self._mock or self._duration_units_per_second is not None
            device_id = "mock" if self._mock else f"{VID:04X}:{PID:04X}"
            return StimulatorStatus(connected, self._armed, calibrated, self._duration_units_per_second if not self._mock else 100.0, device_id=device_id, error=self._last_error)

    def mock_connect(self) -> StimulatorStatus:
        with self._lock:
            self._mock = True
            self._armed = True
            self._duration_units_per_second = 100.0
            self._last_error = None
            return self.status()

    def disconnect_mock(self) -> StimulatorStatus:
        with self._lock:
            self._mock = False
            self._armed = False
            self._last_error = None
            return self.status()

    def connect(self) -> StimulatorStatus:
        with self._lock:
            if self._mock:
                return self.status()
            if self._device is None:
                self._device = self._device_factory()
                try:
                    self._device.open()
                    self._last_error = None
                except Exception as exc:
                    self._device = None
                    self._last_error = str(exc)
                    raise
            return self.status()

    def arm(self, confirmed: bool) -> StimulatorStatus:
        if not confirmed:
            raise PermissionError("arming requires explicit confirmation")
        with self._lock:
            if not self._mock:
                self.connect()
            self._armed = True
            return self.status()

    def disarm(self) -> StimulatorStatus:
        with self._lock:
            self._armed = False
            return self.status()

    def disconnect(self) -> StimulatorStatus:
        with self._lock:
            self._armed = False
            if self._mock:
                self._mock = False
                return self.status()
            if self._device is not None:
                self._device.close()
                self._device = None
            return self.status()

    def duration_seconds_to_units(self, duration_seconds: float) -> int:
        if duration_seconds <= 0:
            raise ValueError("duration seconds must be positive")
        if self._duration_units_per_second is None:
            raise RuntimeError("stimulator duration is not calibrated; set ARENA_SHOCK_DURATION_UNITS_PER_SECOND")
        units = int(round(duration_seconds * self._duration_units_per_second))
        validate_stimulus(0, units)
        return units

    def trigger(self, current_ma: float, duration_seconds: float, *, confirmed: bool = False) -> dict[str, Any]:
        with self._lock:
            if not self._armed:
                raise PermissionError("stimulator is not armed")
            if not confirmed:
                raise PermissionError("real stimulation requires explicit confirmation")
            duration_units = self.duration_seconds_to_units(duration_seconds)
            if self._mock:
                return {"mock": True, "currentMA": current_ma, "durationSeconds": duration_seconds, "durationUnits": duration_units}
            self.connect()
            result = self._device.send(current_ma, duration_units)
            return {**result, "currentMA": current_ma, "durationSeconds": duration_seconds, "durationUnits": duration_units}

    def send_raw_packet(self, packet_hex: str) -> dict[str, Any]:
        with self._lock:
            self.connect()
            return self._device.send_raw(packet_hex)

    def send_raw_ctrl(self, request_type_hex: str, request_hex: str, value_hex: str, index_hex: str) -> dict[str, Any]:
        with self._lock:
            self.connect()
            self._device._initialize()
            import usb.core
            bm = int(request_type_hex, 16)
            b_req = int(request_hex, 16)
            w_val = int(value_hex, 16)
            w_idx = int(index_hex, 16)
            try:
                self._device._device.ctrl_transfer(bm, b_req, w_val, w_idx, None, timeout=1000)
                return {"ok": True, "bmRequestType": hex(bm), "bRequest": hex(b_req), "wValue": hex(w_val), "wIndex": hex(w_idx)}
            except usb.core.USBError as e:
                return {"ok": False, "error": str(e)}

    def close(self) -> None:
        self.disconnect()
