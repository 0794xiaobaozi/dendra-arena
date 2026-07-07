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
            for runtime in self._cameras.values():
                runtime.start_async()
            started: list[CameraRuntime] = []
            for runtime in self._cameras.values():
                for attempt in range(3 if runtime.config.device_index >= 0 else 1):
                    try:
                        runtime.wait_ready()
                        started.append(runtime)
                        break
                    except Exception as exc:
                        if attempt == 2 or runtime.config.device_index < 0:
                            self._event_sink("camera_error", {"boxId": runtime.config.box_id, "message": str(exc)})
                            break
                        runtime.stop()
                        time.sleep(0.5)
                        runtime.start_async()
            if not started:
                self._cameras.clear()
                self._started_at = None
                self._state = "error"
                raise RuntimeError("no cameras could be started")
            self._state = "previewing"
            self._event_sink("session_status", {"status": self._state})

    def start_experiment(self, session: SessionConfig) -> None:
        with self._lock:
            if self._state == "previewing" and self._cameras:
                self._start_recording(session)
            else:
                self._restart_experiment(session)

    def _start_recording(self, session: SessionConfig) -> None:
        session_dir = Path(session.save_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        batch_suffix = f"_batch{session.batch_number}"
        self._session = session
        self._write_manifest(session_dir, "starting")
        for item in session.cameras:
            video = session_dir / f"{item.box_id}{batch_suffix}.mp4" if session.save_video else None
            self._cameras[item.box_id].set_recording(video)
        self._started_at = time.monotonic()
        self._state = "running"
        self._write_manifest(session_dir, "running")
        self._event_sink("session_status", {"status": self._state, "sessionId": session.session_id})
        self._clock_stop.clear()
        self._clock_thread = threading.Thread(target=self._clock_loop, name="experiment-clock", daemon=True)
        self._clock_thread.start()

    def _restart_experiment(self, session: SessionConfig) -> None:
        self.stop()
        session_dir = Path(session.save_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        batch_suffix = f"_batch{session.batch_number}"
        self._session = session
        self._write_manifest(session_dir, "starting")
        self._cameras = {item.box_id: CameraRuntime(item, self._event_sink, self.elapsed) for item in session.cameras}
        for item in session.cameras:
            video = session_dir / f"{item.box_id}{batch_suffix}.mp4" if session.save_video else None
            self._cameras[item.box_id].start_async(video)
        started: list[CameraRuntime] = []
        errors: list[str] = []
        for item in session.cameras:
            runtime = self._cameras[item.box_id]
            max_attempts = 3 if item.device_index >= 0 else 1
            for attempt in range(max_attempts):
                try:
                    runtime.wait_ready()
                    started.append(runtime)
                    break
                except Exception as exc:
                    if attempt == max_attempts - 1 or max_attempts == 1:
                        errors.append(f"{item.box_id}: {exc}")
                        self._event_sink("camera_error", {"boxId": item.box_id, "message": str(exc)})
                    else:
                        runtime.stop()
                        time.sleep(0.5)
                        video = session_dir / f"{item.box_id}{batch_suffix}.mp4" if session.save_video else None
                        runtime.start_async(video)
        if not started:
            self._cameras.clear()
            self._write_manifest(session_dir, "failed", errors)
            self._session = None
            self._started_at = None
            self._state = "error"
            raise RuntimeError("no cameras could be started")
        self._started_at = time.monotonic()
        self._state = "running"
        if errors:
            self._write_manifest(session_dir, "running", errors)
        else:
            self._write_manifest(session_dir, "running")
        self._event_sink("session_status", {"status": self._state, "sessionId": session.session_id})
        self._clock_stop.clear()
        self._clock_thread = threading.Thread(target=self._clock_loop, name="experiment-clock", daemon=True)
        self._clock_thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_recording(clear_cameras=True)
            self._state = "idle"
            self._event_sink("session_status", {"status": self._state})

    def stop_recording(self) -> None:
        with self._lock:
            self._stop_recording(clear_cameras=False)
            self._state = "previewing"
            self._event_sink("session_status", {"status": self._state})

    def _stop_recording(self, *, clear_cameras: bool) -> None:
        if not self._cameras:
            self._state = "idle" if clear_cameras else "previewing"
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
        if not clear_cameras:
            for runtime in self._cameras.values():
                runtime.set_recording(None)
        elif clear_cameras:
            for runtime in list(self._cameras.values()):
                try:
                    runtime.stop()
                except Exception as exc:
                    errors.append(str(exc))
            self._cameras.clear()
        if self._session is not None:
            session_dir = Path(self._session.save_dir)
            self._write_manifest(session_dir, "failed" if errors else "completed", errors)
            if self._session.enable_stimulator and self._stimulator is not None and not getattr(self._stimulator, "_mock", False):
                self._stimulator.disarm()
        self._session = None
        self._started_at = None

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
        batch = self._session.batch_number
        batch_data = {
            "batch": batch,
            "sessionId": self._session.session_id,
            "status": status,
            "elapsedSec": self.elapsed(),
            "cameraIds": [item.box_id for item in self._session.cameras],
            "errors": errors or [],
        }
        existing: dict[str, Any] = {}
        if target.is_file():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                pass
        batches = existing.get("batches", []) if isinstance(existing.get("batches"), list) else []
        batches = [b for b in batches if isinstance(b, dict) and b.get("batch") != batch]
        batches.append(batch_data)
        payload = {"schemaVersion": 1, "sessionId": self._session.session_id, "batches": batches}
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(target)
