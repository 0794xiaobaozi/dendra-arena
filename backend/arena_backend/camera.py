from __future__ import annotations

import base64
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import CameraConfig, CameraTelemetry


EventSink = Callable[[str, dict[str, Any]], None]


def discover_cameras(max_index: int = 10) -> list[dict[str, Any]]:
    """Probe camera indices without retaining device handles."""
    import cv2

    cameras: list[dict[str, Any]] = []
    backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
    for index in range(max_index):
        capture = cv2.VideoCapture(index, backend)
        try:
            if capture.isOpened():
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
                fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
                cameras.append({
                    "deviceId": f"camera-{index}",
                    "deviceIndex": index,
                    "deviceName": f"USB Camera {index + 1:02d}",
                    "displayName": f"Camera {index + 1} (USB)",
                    "status": "available",
                    "resolutionOptions": [{"width": width, "height": height, "fps": fps}],
                })
        finally:
            capture.release()
    return cameras


class _SyntheticCapture:
    """Deterministic 30 FPS source used only when device_index is -1."""

    def __init__(self, width: int = 640, height: int = 360, fps: float = 30.0):
        self.width = width
        self.height = height
        self.fps = fps
        self._opened = True
        self._frame_index = 0
        self._next_frame_at = time.monotonic()

    def isOpened(self) -> bool:
        return self._opened

    def get(self, prop: int) -> float:
        import cv2

        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.height)
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        return 0.0

    def read(self):
        import cv2
        import numpy as np

        delay = self._next_frame_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._next_frame_at += 1.0 / self.fps
        if not self._opened:
            return False, None
        frame = np.full((self.height, self.width, 3), 202, dtype=np.uint8)
        cv2.rectangle(frame, (16, 16), (self.width - 16, self.height - 16), (55, 58, 58), 14)
        for y in range(36, self.height - 30, 18):
            cv2.line(frame, (35, y), (self.width - 35, y + 12), (185, 183, 176), 1)
        phase = self._frame_index % 180
        # Pause for one second each cycle so Freeze transitions are exercised.
        x = 180 + (phase if phase < 120 else 120) * 2
        y = self.height // 2 + int(30 * math.sin(self._frame_index / 13))
        cv2.ellipse(frame, (min(x, self.width - 70), y), (38, 22), 8, 0, 360, (30, 30, 28), -1)
        cv2.circle(frame, (min(x + 27, self.width - 43), y - 14), 7, (20, 20, 18), -1)
        self._frame_index += 1
        return True, frame

    def release(self) -> None:
        self._opened = False


@dataclass
class _BehaviorLatch:
    threshold: float
    min_duration_sec: float
    state: str = "unknown"
    candidate_since: float | None = None

    def update(self, motion: float, now: float) -> tuple[str, list[str]]:
        motion_cutoff = max(self.threshold, 0.001)
        low_motion = motion <= motion_cutoff
        target = "freeze" if low_motion else "moving"
        if self.state == target:
            self.candidate_since = None
            return self.state, []
        if self.candidate_since is None:
            self.candidate_since = now
            return ("candidate_freeze" if low_motion else "moving"), []
        if now - self.candidate_since < self.min_duration_sec:
            return ("candidate_freeze" if low_motion else "moving"), []
        previous = self.state
        self.state = target
        self.candidate_since = None
        events = [f"{target}_start"]
        if previous != "unknown":
            events.insert(0, f"{previous}_end")
        return self.state, events


class CameraRuntime:
    """Owns one capture thread and releases all OpenCV resources on that thread."""

    def __init__(self, config: CameraConfig, event_sink: EventSink, clock: Callable[[], float]):
        self.config = config
        self._event_sink = event_sink
        self._clock = clock
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._record_path: Path | None = None
        self._recording = False
        self._frame_lock = threading.Lock()
        self._latest_frame: Any | None = None
        self._ready_event = threading.Event()
        self._start_error: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, record_path: Path | None = None) -> None:
        self.start_async(record_path)
        try:
            self.wait_ready()
        except Exception:
            self.stop()
            raise

    def start_async(self, record_path: Path | None = None) -> None:
        if self.running:
            return
        self._record_path = record_path
        self._recording = record_path is not None
        self._stop_event.clear()
        self._ready_event.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._capture_loop, name=f"camera-{self.config.box_id}", daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready_event.wait(timeout):
            raise TimeoutError(f"camera {self.config.box_id} did not become ready")
        if self._start_error:
            raise RuntimeError(self._start_error)

    def set_recording(self, record_path: Path | None) -> None:
        self._record_path = record_path
        self._recording = record_path is not None

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError(f"camera {self.config.box_id} did not stop within {timeout:.1f}s")
        self._thread = None

    def snapshot(self, path: Path) -> None:
        import cv2

        with self._frame_lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
        if frame is None:
            raise RuntimeError(f"camera {self.config.box_id} has not produced a frame")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError(f"unable to save snapshot: {path}")

    def _capture_loop(self) -> None:
        import cv2
        import numpy as np

        capture = _SyntheticCapture() if self.config.device_index == -1 else cv2.VideoCapture(self.config.device_index, cv2.CAP_DSHOW)
        writer: Any | None = None
        previous_gray: Any | None = None
        latch = _BehaviorLatch(self.config.freeze_strategy.threshold, self.config.freeze_strategy.min_duration_sec)
        frame_count = 0
        fps_window_started = time.monotonic()
        measured_fps = 0.0
        last_telemetry_at = 0.0
        last_preview_at = 0.0
        try:
            if not capture.isOpened():
                self._start_error = f"unable to open camera {self.config.box_id}"
                self._ready_event.set()
                self._event_sink("camera_error", {"boxId": self.config.box_id, "message": self._start_error})
                return
            if self.config.frame_width and self.config.frame_height:
                try:
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
                except Exception:
                    pass
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.config.frame_width or 640
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self.config.frame_height or 480
            source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
            writer: Any = None
            writer_initialized = False
            self._ready_event.set()
            while not self._stop_event.is_set():
                if not writer_initialized and self._recording and self._record_path:
                    self._record_path.parent.mkdir(parents=True, exist_ok=True)
                    writer = cv2.VideoWriter(str(self._record_path), cv2.VideoWriter_fourcc(*"mp4v"), source_fps, (width, height))
                    if not writer.isOpened():
                        self._event_sink("camera_error", {"boxId": self.config.box_id, "message": f"Unable to create video writer: {self._record_path}"})
                    writer_initialized = True
                if writer_initialized and not self._recording:
                    if writer is not None and writer.isOpened():
                        writer.release()
                    writer = None
                    writer_initialized = False
                ok, frame = capture.read()
                if not ok or frame is None:
                    self._event_sink("camera_error", {"boxId": self.config.box_id, "message": "Frame read failed"})
                    break
                with self._frame_lock:
                    self._latest_frame = frame.copy()
                if writer is not None and writer.isOpened():
                    writer.write(frame)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                motion = 0.0 if previous_gray is None else float(np.mean(cv2.absdiff(gray, previous_gray)) / 255.0)
                previous_gray = gray
                now = self._clock()
                behavior, behavior_events = latch.update(motion, now)
                frame_count += 1
                span = time.monotonic() - fps_window_started
                if span >= 1.0:
                    measured_fps = frame_count / span
                    frame_count = 0
                    fps_window_started = time.monotonic()
                monotonic_now = time.monotonic()
                if monotonic_now - last_telemetry_at >= 0.1:
                    telemetry = CameraTelemetry(
                        box_id=self.config.box_id,
                        experiment_time_sec=now,
                        actual_fps=measured_fps or source_fps,
                        motion_value=motion,
                        behavior_state=behavior,  # type: ignore[arg-type]
                        recording_state="recording" if self._recording else "preview",
                    )
                    self._event_sink("camera_telemetry", telemetry.to_payload())
                    last_telemetry_at = monotonic_now
                for behavior_event in behavior_events:
                    self._event_sink("behavior_event", {"boxId": self.config.box_id, "timeSec": now, "type": behavior_event})
                if monotonic_now - last_preview_at >= 1 / 12:
                    frame_height, frame_width = frame.shape[:2]
                    preview_width, preview_height = _fit_preview_size(frame_width, frame_height)
                    preview = frame if (preview_width, preview_height) == (frame_width, frame_height) else cv2.resize(
                        frame,
                        (preview_width, preview_height),
                        interpolation=cv2.INTER_AREA,
                    )
                    encoded, buffer = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    if encoded:
                        self._event_sink("camera_frame", {"boxId": self.config.box_id, "encoding": "jpeg-base64", "data": base64.b64encode(buffer).decode("ascii")})
                        last_preview_at = monotonic_now
        except Exception as exc:
            if not self._ready_event.is_set():
                self._start_error = str(exc)
                self._ready_event.set()
            self._event_sink("camera_error", {"boxId": self.config.box_id, "message": str(exc)})
        finally:
            self._ready_event.set()
            if writer is not None:
                writer.release()
            capture.release()
            with self._frame_lock:
                self._latest_frame = None
            self._event_sink("camera_stopped", {"boxId": self.config.box_id})

def _fit_preview_size(width: int, height: int, max_width: int = 640, max_height: int = 360) -> tuple[int, int]:
    """Fit a frame inside the preview bounds without changing its aspect ratio."""
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    scale = min(max_width / width, max_height / height, 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))
