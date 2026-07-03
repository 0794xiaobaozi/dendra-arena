from __future__ import annotations

import platform
import shutil
from pathlib import Path
from typing import Any

from .camera import discover_cameras
from .experiment import ExperimentRunner
from .schemas import parse_camera, parse_session


class BackendApplication:
    def __init__(self, event_sink):
        self._event_sink = event_sink
        self._runner = ExperimentRunner(event_sink)

    def execute(self, command_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "ping": self._ping,
            "discover_cameras": self._discover,
            "get_state": self._get_state,
            "start_preview": self._start_preview,
            "stop_preview": self._stop,
            "start_experiment": self._start_experiment,
            "stop_experiment": self._stop,
            "capture_snapshot": self._snapshot,
        }
        try:
            handler = handlers[command_type]
        except KeyError as exc:
            raise ValueError(f"unknown command: {command_type}") from exc
        return handler(payload)

    def _ping(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "pythonVersion": platform.python_version()}

    def _discover(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"cameras": discover_cameras(int(payload.get("maxIndex", 10)))}

    def _get_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        save_dir = Path(payload.get("saveDir", Path.home()))
        probe = save_dir
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        usage = shutil.disk_usage(probe if probe.exists() else Path.home())
        return {"state": self._runner.state, "elapsedSec": self._runner.elapsed(), "diskFreeGB": usage.free / 1024**3, "pythonVersion": platform.python_version()}

    def _start_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        cameras = [parse_camera(item) for item in payload.get("cameras", [])]
        if not cameras:
            raise ValueError("start_preview requires cameras")
        self._runner.start_preview(cameras)
        return {"status": self._runner.state}

    def _start_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = parse_session(payload["sessionConfig"])
        self._runner.start_experiment(session)
        return {"status": self._runner.state, "sessionId": session.session_id}

    def _stop(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self._runner.stop()
        return {"status": self._runner.state}

    def _snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        output_dir = Path(str(payload.get("outputDir", Path.home() / "Pictures" / "arena")))
        path = self._runner.snapshot(str(payload["boxId"]), output_dir)
        return {"path": str(path)}

    def shutdown(self) -> None:
        self._runner.stop()
