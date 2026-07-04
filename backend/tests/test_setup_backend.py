from pathlib import Path
import time

import pytest

from arena_backend.application import BackendApplication
from arena_backend.experiment import ExperimentRunner
from arena_backend.protocols import ProtocolRegistry, dry_run_protocol, generate_schedule, validate_protocol
from arena_backend.setup_services import run_preflight, validate_roi
from arena_backend.schemas import parse_session
from arena_backend.stimulator import StimulatorController, build_reset_packet, build_stimulus_packet


class FakeShockDevice:
    sent: list[tuple[float, int]] = []

    @staticmethod
    def probe() -> bool:
        return True

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def send(self, current_ma: float, duration_units: int):
        self.sent.append((current_ma, duration_units))
        return {"resetAck": "aa", "stimulusAck": "bb", "sentAt": 1.0}


def valid_protocol(protocol_id: str = "fear_conditioning_v2"):
    return {
        "schemaVersion": 1,
        "id": protocol_id,
        "name": "Fear Conditioning v2",
        "version": "2.1",
        "totalDurationSec": 180,
        "freezeDefaults": {"threshold": 0.65, "exitThreshold": 0.85},
        "shocks": [{"id": "shock-1", "timeSec": 120, "durationSec": 2, "intensityMA": 0.8}],
        "phases": [],
    }


def valid_session(save_dir: Path):
    return {
        "name": "session_001",
        "saveDir": str(save_dir),
        "boxes": [{
            "id": "box-1",
            "camera": "camera-0",
            "protocol": "fear_conditioning_v2",
            "roi": {"mode": "rectangle", "x": 120, "y": 80, "width": 1280, "height": 720, "imageWidth": 1920, "imageHeight": 1080},
            "freeze": {"threshold": 0.65, "exitThreshold": 0.85},
            "shockEnabled": False,
        }],
    }


def test_stimulator_packets_preserve_known_usb_protocol():
    assert build_reset_packet().hex() == "f0000000000000000000000000"
    assert build_stimulus_packet(0.8, 2).hex() == "ff0301500002000000dc050000"


def test_stimulator_is_fail_closed_and_uses_explicit_calibration():
    FakeShockDevice.sent.clear()
    controller = StimulatorController(FakeShockDevice, duration_units_per_second=10)
    with pytest.raises(PermissionError, match="not armed"):
        controller.trigger(0.8, 0.5, confirmed=True)
    with pytest.raises(PermissionError, match="confirmation"):
        controller.arm(False)
    assert controller.arm(True).armed is True
    with pytest.raises(PermissionError, match="confirmation"):
        controller.trigger(0.8, 0.5)
    result = controller.trigger(0.8, 0.5, confirmed=True)
    assert result["durationUnits"] == 5
    assert FakeShockDevice.sent == [(0.8, 5)]


def test_uncalibrated_stimulator_refuses_seconds_conversion():
    controller = StimulatorController(FakeShockDevice)
    controller.arm(True)
    with pytest.raises(RuntimeError, match="not calibrated"):
        controller.trigger(0.8, 2.0, confirmed=True)


def test_roi_validation_uses_source_image_coordinates():
    valid = validate_roi({"mode": "rectangle", "x": 120, "y": 80, "width": 1280, "height": 720, "imageWidth": 1920, "imageHeight": 1080})
    assert valid["valid"] is True
    assert valid["normalized"]["width"] == pytest.approx(2 / 3)
    invalid = validate_roi({"mode": "rectangle", "x": 1800, "y": 0, "width": 200, "height": 100, "imageWidth": 1920, "imageHeight": 1080})
    assert invalid["valid"] is False
    assert "exceeds image width" in invalid["errors"][0]


def test_preflight_writes_probe_and_reports_box_failures(tmp_path: Path):
    session = valid_session(tmp_path / "output")
    status = {"connected": False, "armed": False, "calibrated": False}
    result = run_preflight(session, status)
    assert result["canRun"] is True
    session["boxes"][0]["roi"] = None
    failed = run_preflight(session, status)
    assert failed["canRun"] is False
    assert "ROI is missing" in failed["blockingReasons"]


def test_protocol_registry_round_trip_and_schedule_tools(tmp_path: Path):
    registry = ProtocolRegistry(tmp_path / "protocols")
    saved = registry.save(valid_protocol())
    assert saved["hash"]
    assert registry.list()[0]["shockCount"] == 1
    assert registry.load("fear_conditioning_v2")["name"] == "Fear Conditioning v2"
    validation = validate_protocol(valid_protocol())
    assert validation["valid"] is True
    generated = generate_schedule({"mode": "fixed", "startTimeSec": 120, "endTimeSec": 360, "intervalSec": 120, "durationSec": 2, "intensityMA": 0.8, "seed": 42})
    assert [item["timeSec"] for item in generated] == [120, 240, 360]
    assert dry_run_protocol(valid_protocol())[-1] == "180.000 Protocol finished"


def test_application_saves_and_locks_valid_session(tmp_path: Path):
    controller = StimulatorController(FakeShockDevice, duration_units_per_second=10)
    app = BackendApplication(lambda *_args: None, project_root=tmp_path, stimulator=controller)
    session = valid_session(tmp_path / "sessions")
    draft = app.execute("save_session_draft", {"sessionDraft": session})
    locked = app.execute("lock_session_for_run", {"sessionDraft": session})
    assert Path(draft["path"]).exists()
    assert Path(locked["path"]).exists()
    assert locked["lockedConfig"]["status"] == "locked"


def test_application_stimulator_test_requires_arm_and_confirm(tmp_path: Path):
    FakeShockDevice.sent.clear()
    app = BackendApplication(lambda *_args: None, project_root=tmp_path, stimulator=StimulatorController(FakeShockDevice, duration_units_per_second=10))
    with pytest.raises(PermissionError):
        app.execute("stimulator_test", {"currentMA": 0.2, "durationSeconds": 0.5, "confirmed": True})
    app.execute("arm_stimulator", {"confirmed": True})
    result = app.execute("stimulator_test", {"currentMA": 0.2, "durationSeconds": 0.5, "confirmed": True})
    assert result["durationUnits"] == 5


def test_experiment_scheduler_uses_armed_stimulator_and_disarms(tmp_path: Path):
    FakeShockDevice.sent.clear()
    controller = StimulatorController(FakeShockDevice, duration_units_per_second=10)
    controller.arm(True)
    events = []
    runner = ExperimentRunner(lambda kind, payload: events.append((kind, payload)), controller)
    session = parse_session({
        "sessionId": "stimulated-session",
        "saveDir": str(tmp_path),
        "totalDurationSec": 0.25,
        "cameras": [{"boxId": "box-synthetic", "deviceIndex": -1}],
        "shocks": [{"id": "shock-1", "timeSec": 0.05, "durationSec": 0.2, "intensityMA": 0.8}],
        "globalOptions": {"saveVideo": False, "enableStimulator": True},
    })
    runner.start_experiment(session)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and runner.state != "idle":
        time.sleep(0.02)
    shock_events = [payload for kind, payload in events if kind == "shock_event"]
    assert shock_events[0]["status"] == "triggered"
    assert FakeShockDevice.sent == [(0.8, 2)]
    assert controller.armed is False
