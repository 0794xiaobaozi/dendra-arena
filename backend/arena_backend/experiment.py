from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .camera import CameraRuntime, EventSink
from .schemas import CameraConfig, SessionConfig
from .stimulator import StimulatorController


class ExperimentRunner:
    def __init__(self, event_sink: EventSink, stimulator: StimulatorController | None = None):
        self._event_sink = event_sink
        self._lock = threading.RLock()
        self._state = "idle"
        self._started_at: float | None = None
        self._cameras: dict[str, CameraRuntime] = {}
        self._session: SessionConfig | None = None
        self._clock_thread: threading.Thread | None = None
        self._clock_stop = threading.Event()
        self._stimulator = stimulator

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def elapsed(self) -> float:
        started = self._started_at
        return max(0.0, time.monotonic() - started) if started is not None else 0.0

    def start_preview(self, cameras: list[CameraConfig]) -> None:
        with self._lock:
            self.stop()
            self._started_at = time.monotonic()
            self._cameras = {item.box_id: CameraRuntime(item, self._event_sink, self.elapsed) for item in cameras if item.enabled}
            started: list[CameraRuntime] = []
            try:
                for runtime in self._cameras.values():
                    runtime.start()
                    started.append(runtime)
            except Exception:
                for runtime in started:
                    runtime.stop()
                self._cameras.clear()
                self._started_at = None
                self._state = "error"
                raise
            self._state = "previewing"
            self._event_sink("session_status", {"status": self._state})

    def start_experiment(self, session: SessionConfig) -> None:
        with self._lock:
            self.stop()
            session_dir = Path(session.save_dir) / session.session_id
            session_dir.mkdir(parents=True, exist_ok=False)
            self._session = session
            self._write_manifest(session_dir, "starting")
            self._started_at = time.monotonic()
            self._cameras = {item.box_id: CameraRuntime(item, self._event_sink, self.elapsed) for item in session.cameras}
            started: list[CameraRuntime] = []
            try:
                for item in session.cameras:
                    video = session_dir / f"{item.box_id}.mp4" if session.save_video else None
                    runtime = self._cameras[item.box_id]
                    runtime.start(video)
                    started.append(runtime)
            except Exception as exc:
                for runtime in started:
                    runtime.stop()
                self._cameras.clear()
                self._write_manifest(session_dir, "failed", [str(exc)])
                self._session = None
                self._started_at = None
                self._state = "error"
                raise
            self._state = "running"
            self._write_manifest(session_dir, "running")
            self._event_sink("session_status", {"status": self._state, "sessionId": session.session_id})
            self._clock_stop.clear()
            self._clock_thread = threading.Thread(target=self._clock_loop, name="experiment-clock", daemon=True)
            self._clock_thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._cameras:
                self._state = "idle"
                self._started_at = None
                return
            self._state = "stopping"
            self._event_sink("session_status", {"status": self._state})
            self._clock_stop.set()
            clock_thread = self._clock_thread
            if clock_thread and clock_thread is not threading.current_thread():
                clock_thread.join(2.0)
            self._clock_thread = None
            errors: list[str] = []
            for runtime in list(self._cameras.values()):
                try:
                    runtime.stop()
                except Exception as exc:
                    errors.append(str(exc))
            self._cameras.clear()
            if self._session is not None:
                session_dir = Path(self._session.save_dir) / self._session.session_id
                self._write_manifest(session_dir, "failed" if errors else "completed", errors)
                if self._session.enable_stimulator and self._stimulator is not None:
                    self._stimulator.disarm()
            self._session = None
            self._started_at = None
            self._state = "error" if errors else "idle"
            self._event_sink("session_status", {"status": self._state, "errors": errors})

    def snapshot(self, box_id: str, output_dir: Path) -> Path:
        with self._lock:
            try:
                runtime = self._cameras[box_id]
            except KeyError as exc:
                raise ValueError(f"camera is not active: {box_id}") from exc
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = output_dir / f"snapshot_{box_id}_{stamp}.jpg"
            runtime.snapshot(path)
            self._event_sink("snapshot_saved", {"boxId": box_id, "path": str(path)})
            return path

    def _clock_loop(self) -> None:
        session = self._session
        if session is None:
            return
        fired: set[str] = set()
        while not self._clock_stop.wait(0.1):
            elapsed = self.elapsed()
            self._event_sink("experiment_tick", {"elapsedSec": elapsed, "totalDurationSec": session.total_duration_sec})
            for shock in session.shocks:
                if shock.id in fired or elapsed < shock.time_sec:
                    continue
                fired.add(shock.id)
                status = "skipped_unarmed"
                result: dict[str, Any] | None = None
                error: str | None = None
                if session.enable_stimulator and self._stimulator is not None:
                    try:
                        result = self._stimulator.trigger(shock.intensity_ma, shock.duration_sec, confirmed=True)
                        status = "triggered"
                    except Exception as exc:
                        status = "failed"
                        error = str(exc)
                self._event_sink("shock_event", {"id": shock.id, "scheduledTimeSec": shock.time_sec, "actualTimeSec": elapsed, "status": status, "result": result, "error": error})
            if session.total_duration_sec > 0 and elapsed >= session.total_duration_sec:
                self._event_sink("experiment_duration_reached", {"elapsedSec": elapsed})
                threading.Thread(target=self.stop, name="experiment-auto-stop", daemon=True).start()
                return

    def _write_manifest(self, session_dir: Path, status: str, errors: list[str] | None = None) -> None:
        if self._session is None:
            return
        target = session_dir / "session.json"
        temporary = session_dir / "session.json.tmp"
        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "sessionId": self._session.session_id,
            "status": status,
            "elapsedSec": self.elapsed(),
            "cameraIds": [item.box_id for item in self._session.cameras],
            "errors": errors or [],
        }
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(target)
