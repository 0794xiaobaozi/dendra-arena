from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


BehaviorState = Literal["unknown", "moving", "freeze", "candidate_freeze"]
RuntimeState = Literal["idle", "previewing", "running", "stopping", "error"]


@dataclass(frozen=True)
class RoiConfig:
    shape: str = "rectangle"
    points: list[list[int]] = field(default_factory=list)


@dataclass(frozen=True)
class FreezeStrategy:
    threshold: float = 0.65
    min_duration_sec: float = 0.5


@dataclass(frozen=True)
class CameraConfig:
    box_id: str
    device_id: str
    device_index: int
    label: str
    enabled: bool = True
    roi: RoiConfig = field(default_factory=RoiConfig)
    freeze_strategy: FreezeStrategy = field(default_factory=FreezeStrategy)


@dataclass(frozen=True)
class ShockConfig:
    id: str
    time_sec: float
    duration_sec: float
    intensity_ma: float


@dataclass(frozen=True)
class SessionConfig:
    session_id: str
    save_dir: str
    cameras: list[CameraConfig]
    shocks: list[ShockConfig] = field(default_factory=list)
    total_duration_sec: float = 0.0
    save_video: bool = True
    enable_stimulator: bool = False


@dataclass
class CameraTelemetry:
    box_id: str
    experiment_time_sec: float
    actual_fps: float
    motion_value: float
    behavior_state: BehaviorState
    recording_state: str
    dropped_frames: int = 0

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _roi(value: dict[str, Any] | None) -> RoiConfig:
    value = value or {}
    return RoiConfig(shape=str(value.get("shape", "rectangle")), points=value.get("points", []))


def _strategy(value: dict[str, Any] | None) -> FreezeStrategy:
    value = value or {}
    threshold = float(value.get("threshold", 0.65))
    duration = float(value.get("minDurationSec", value.get("min_duration_sec", 0.5)))
    if threshold <= 0 or duration <= 0:
        raise ValueError("freeze threshold and duration must be positive")
    return FreezeStrategy(threshold=threshold, min_duration_sec=duration)


def parse_camera(value: dict[str, Any]) -> CameraConfig:
    return CameraConfig(
        box_id=str(value["boxId"]),
        device_id=str(value.get("deviceId", value["boxId"])),
        device_index=int(value.get("deviceIndex", 0)),
        label=str(value.get("label", value["boxId"])),
        enabled=bool(value.get("enabled", True)),
        roi=_roi(value.get("roi")),
        freeze_strategy=_strategy(value.get("freezeStrategy")),
    )


def parse_session(value: dict[str, Any]) -> SessionConfig:
    cameras = [parse_camera(item) for item in value.get("cameras", []) if item.get("enabled", True)]
    if not cameras:
        raise ValueError("at least one enabled camera is required")
    shocks = [
        ShockConfig(
            id=str(item.get("id", f"shock-{index + 1}")),
            time_sec=float(item["timeSec"]),
            duration_sec=float(item["durationSec"]),
            intensity_ma=float(item["intensityMA"]),
        )
        for index, item in enumerate(value.get("shocks", []))
    ]
    return SessionConfig(
        session_id=str(value["sessionId"]),
        save_dir=str(value["saveDir"]),
        cameras=cameras,
        shocks=sorted(shocks, key=lambda item: item.time_sec),
        total_duration_sec=float(value.get("totalDurationSec", 0)),
        save_video=bool(value.get("globalOptions", {}).get("saveVideo", True)),
        enable_stimulator=bool(value.get("globalOptions", {}).get("enableStimulator", False)),
    )
