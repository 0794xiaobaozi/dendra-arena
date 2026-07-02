"""
实验方案：从 protocols/*.yml 扫描加载。

仅支持一种严格 YAML 结构：

schema_version: 1
protocol:
  id: xxx
  name: xxx
  total_duration_sec: 0
  shocks:
    - time_sec: 240
      current_mA: 0.9
      duration: 3
"""
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, List

from .paths import get_protocols_dir

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


SUPPORTED_SCHEMA_VERSION = 1


@dataclass
class ScheduledShock:
    """单次定时电击：从实验开始起 time_sec 秒时触发。"""

    time_sec: float
    current_mA: float
    duration: int


@dataclass
class ExperimentProtocol:
    """单个实验方案。"""

    id: str
    name: str
    total_duration_sec: float = 0.0
    shocks: List[ScheduledShock] = field(default_factory=list)

    def summary(self) -> str:
        if not self.shocks:
            return "无定时刺激事件"
        times = [f"{s.time_sec / 60:.1f}min" for s in self.shocks]
        return f"定时电击 @ {', '.join(times)} | {self.shocks[0].current_mA}mA"


def _protocols_dir() -> Path:
    return get_protocols_dir()


def _require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} 必须是对象")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} 必须是非空字符串")
    return value.strip()


def _require_float(value: Any, path: str, *, min_value: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} 必须是数字") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{path} 必须是有限数字")
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{path} 必须 >= {min_value}")
    return parsed


def _require_int(value: Any, path: str, *, min_value: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{path} 必须是整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} 必须是整数") from exc
    # 避免 1.5 被 int() 静默截断为 1。
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{path} 必须是整数")
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{path} 必须 >= {min_value}")
    return parsed


def _parse_shocks(raw: Any, path: str) -> List[ScheduledShock]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{path} 必须是列表")
    out: List[ScheduledShock] = []
    for i, item in enumerate(raw):
        obj = _require_dict(item, f"{path}[{i}]")
        current = _require_float(
            obj.get("current_mA"), f"{path}[{i}].current_mA", min_value=0.01
        )
        if current > 4.0:
            raise ValueError(f"{path}[{i}].current_mA 必须 <= 4.0")
        if abs(current * 100 - round(current * 100)) > 1e-9:
            raise ValueError(f"{path}[{i}].current_mA 最多保留两位小数")
        out.append(
            ScheduledShock(
                time_sec=_require_float(obj.get("time_sec"), f"{path}[{i}].time_sec", min_value=0.0),
                current_mA=current,
                duration=_require_int(obj.get("duration"), f"{path}[{i}].duration", min_value=1),
            )
        )
        if out[-1].duration > 65535:
            raise ValueError(f"{path}[{i}].duration 必须 <= 65535")
    return sorted(out, key=lambda s: s.time_sec)


def _parse_one(data: Any, source_id: str) -> ExperimentProtocol:
    root = _require_dict(data, source_id)
    schema_version = _require_int(root.get("schema_version"), f"{source_id}.schema_version", min_value=1)
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"{source_id}.schema_version={schema_version} 不支持，当前仅支持 {SUPPORTED_SCHEMA_VERSION}"
        )

    protocol = _require_dict(root.get("protocol"), f"{source_id}.protocol")
    parsed = ExperimentProtocol(
        id=_require_str(protocol.get("id"), f"{source_id}.protocol.id"),
        name=_require_str(protocol.get("name"), f"{source_id}.protocol.name"),
        total_duration_sec=_require_float(
            protocol.get("total_duration_sec", 0.0),
            f"{source_id}.protocol.total_duration_sec",
            min_value=0.0,
        ),
        shocks=_parse_shocks(protocol.get("shocks", []), f"{source_id}.protocol.shocks"),
    )
    if not parsed.shocks:
        raise ValueError(f"{source_id}.protocol.shocks 不能为空")
    if parsed.total_duration_sec > 0:
        for i, shock in enumerate(parsed.shocks):
            if shock.time_sec > parsed.total_duration_sec:
                raise ValueError(
                    f"{source_id}.protocol.shocks[{i}].time_sec 不得超过 total_duration_sec"
                )
    return parsed


def _load_protocols_from_dir(dir_path: Path) -> List[ExperimentProtocol]:
    out: List[ExperimentProtocol] = []
    if not dir_path.is_dir() or yaml is None:
        return out
    for ext in ("*.yml", "*.yaml"):
        for f in sorted(dir_path.glob(ext)):
            try:
                with open(f, encoding="utf-8") as fp:
                    data = yaml.safe_load(fp)
                if data is None:
                    continue
                out.append(_parse_one(data, f.stem))
            except Exception as e:
                print(f"[protocol] 跳过 {f.name}: {e}")
                continue
    return out


def _default_fallback() -> List[ExperimentProtocol]:
    return [
        ExperimentProtocol(
            id="default",
            name="默认（示例）",
            total_duration_sec=0.0,
            shocks=[ScheduledShock(time_sec=60.0, current_mA=0.40, duration=50)],
        )
    ]


def get_protocol_list() -> List[ExperimentProtocol]:
    loaded = _load_protocols_from_dir(_protocols_dir())
    if not loaded:
        return _default_fallback()
    unique: List[ExperimentProtocol] = []
    seen_ids: set[str] = set()
    for protocol in loaded:
        if protocol.id in seen_ids:
            print(f"[protocol] 跳过重复 id: {protocol.id}")
            continue
        seen_ids.add(protocol.id)
        unique.append(protocol)
    return unique if unique else _default_fallback()


def get_protocol_by_id(protocol_id: str) -> ExperimentProtocol | None:
    for p in get_protocol_list():
        if p.id == protocol_id:
            return p
    return None
