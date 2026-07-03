from pathlib import Path
import time
from unittest.mock import patch

import pytest

from arena_backend.application import BackendApplication
from arena_backend.camera import _BehaviorLatch, _fit_preview_size
from arena_backend.experiment import ExperimentRunner
from arena_backend.schemas import parse_session
from arena_backend.schemas import parse_camera


def test_ping_reports_protocol_runtime():
    app = BackendApplication(lambda *_args: None)
    result = app.execute("ping", {})
    assert result["ok"] is True
    assert result["pythonVersion"]


def test_session_requires_an_enabled_camera(tmp_path: Path):
    with pytest.raises(ValueError, match="enabled camera"):
        parse_session({"sessionId": "test", "saveDir": str(tmp_path), "cameras": []})


def test_unknown_command_is_rejected():
    app = BackendApplication(lambda *_args: None)
    with pytest.raises(ValueError, match="unknown command"):
        app.execute("dance", {})


def test_behavior_latch_emits_balanced_transition_events():
    latch = _BehaviorLatch(threshold=0.65, min_duration_sec=1.0)
    assert latch.update(0.0, 0.0) == ("candidate_freeze", [])
    assert latch.update(0.0, 1.1) == ("freeze", ["freeze_start"])
    assert latch.update(0.2, 2.0) == ("moving", [])
    assert latch.update(0.2, 3.1) == ("moving", ["freeze_end", "moving_start"])


@pytest.mark.parametrize(("source", "expected"), [
    ((1920, 1080), (640, 360)),
    ((640, 480), (480, 360)),
    ((1280, 720), (640, 360)),
    ((320, 240), (320, 240)),
])
def test_preview_size_preserves_source_aspect_ratio(source, expected):
    assert _fit_preview_size(*source) == expected


def test_completed_session_writes_atomic_manifest(tmp_path: Path):
    class FakeCamera:
        def __init__(self, *_args):
            pass

        def start(self, _path=None):
            pass

        def stop(self):
            pass

    events = []
    runner = ExperimentRunner(lambda kind, payload: events.append((kind, payload)))
    session = parse_session({
        "sessionId": "session-1",
        "saveDir": str(tmp_path),
        "cameras": [{"boxId": "box-1", "deviceIndex": 0}],
        "globalOptions": {"saveVideo": False},
    })
    with patch("arena_backend.experiment.CameraRuntime", FakeCamera):
        runner.start_experiment(session)
        runner.stop()
    manifest = (tmp_path / "session-1" / "session.json").read_text(encoding="utf-8")
    assert '"status": "completed"' in manifest
    assert not (tmp_path / "session-1" / "session.json.tmp").exists()


def test_camera_start_failure_marks_session_failed(tmp_path: Path):
    class FailingCamera:
        def __init__(self, *_args):
            pass

        def start(self, _path=None):
            raise RuntimeError("camera unavailable")

        def stop(self):
            pass

    runner = ExperimentRunner(lambda *_args: None)
    session = parse_session({
        "sessionId": "failed-session",
        "saveDir": str(tmp_path),
        "cameras": [{"boxId": "box-1", "deviceIndex": 0}],
        "globalOptions": {"saveVideo": False},
    })
    with patch("arena_backend.experiment.CameraRuntime", FailingCamera):
        with pytest.raises(RuntimeError, match="camera unavailable"):
            runner.start_experiment(session)
    manifest = (tmp_path / "failed-session" / "session.json").read_text(encoding="utf-8")
    assert '"status": "failed"' in manifest
    assert "camera unavailable" in manifest


def test_synthetic_camera_emits_frames_telemetry_and_snapshot(tmp_path: Path):
    events = []
    runner = ExperimentRunner(lambda kind, payload: events.append((kind, payload)))
    camera = parse_camera({
        "boxId": "box-synthetic",
        "deviceIndex": -1,
        "freezeStrategy": {"threshold": 0.65, "minDurationSec": 0.1},
    })
    runner.start_preview([camera])
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not {"camera_frame", "camera_telemetry"}.issubset({kind for kind, _ in events}):
        time.sleep(0.02)
    snapshot = runner.snapshot("box-synthetic", tmp_path)
    runner.stop()
    kinds = {kind for kind, _ in events}
    assert {"camera_frame", "camera_telemetry", "snapshot_saved"}.issubset(kinds)
    assert snapshot.exists()
    assert snapshot.stat().st_size > 1_000
    assert runner.state == "idle"


def test_synthetic_experiment_ticks_shock_once_and_auto_stops(tmp_path: Path):
    events = []
    runner = ExperimentRunner(lambda kind, payload: events.append((kind, payload)))
    session = parse_session({
        "sessionId": "synthetic-experiment",
        "saveDir": str(tmp_path),
        "totalDurationSec": 0.35,
        "cameras": [{
            "boxId": "box-synthetic",
            "deviceIndex": -1,
            "freezeStrategy": {"threshold": 0.65, "minDurationSec": 0.1},
        }],
        "shocks": [{"id": "shock-1", "timeSec": 0.1, "durationSec": 0.01, "intensityMA": 0.8}],
        "globalOptions": {"saveVideo": False, "enableStimulator": False},
    })
    runner.start_experiment(session)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and runner.state != "idle":
        time.sleep(0.02)
    shock_events = [payload for kind, payload in events if kind == "shock_event"]
    assert runner.state == "idle"
    assert len(shock_events) == 1
    assert shock_events[0]["status"] == "skipped_unarmed"
    assert any(kind == "experiment_tick" for kind, _ in events)
    manifest = (tmp_path / "synthetic-experiment" / "session.json").read_text(encoding="utf-8")
    assert '"status": "completed"' in manifest
