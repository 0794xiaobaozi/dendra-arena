from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path
from typing import Any

import yaml


PROTOCOL_ID = re.compile(r"^[a-z0-9_]+$")


def _canonical_hash(value: dict[str, Any]) -> str:
    canonical = yaml.safe_dump(value, allow_unicode=True, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_protocol(document: dict[str, Any]) -> dict[str, Any]:
    raw = document.get("protocol", document)
    if not isinstance(raw, dict):
        raise ValueError("protocol must be an object")
    protocol_id = str(raw.get("id", "")).strip()
    name = str(raw.get("name", "")).strip()
    duration = float(raw.get("total_duration_sec", raw.get("totalDurationSec", 0)))
    shocks = []
    for index, item in enumerate(raw.get("shocks", [])):
        if not isinstance(item, dict):
            raise ValueError(f"shocks[{index}] must be an object")
        shocks.append({
            "id": str(item.get("id", f"shock-{index + 1}")),
            "timeSec": float(item.get("time_sec", item.get("timeSec", 0))),
            "durationSec": float(item.get("duration_sec", item.get("durationSec", item.get("duration", 0)))),
            "intensityMA": float(item.get("current_mA", item.get("current", item.get("intensityMA", 0)))),
            "notes": str(item.get("notes", item.get("label", ""))),
        })
    return {
        "schemaVersion": int(document.get("schema_version", document.get("schemaVersion", 1))),
        "id": protocol_id,
        "name": name,
        "version": str(raw.get("version", "1.0")),
        "description": str(raw.get("description", "")),
        "author": str(raw.get("author", "")),
        "totalDurationSec": duration,
        "shocks": shocks,
        "freezeDefaults": raw.get("freeze_defaults", raw.get("freezeDefaults", {"threshold": 0.65, "minDurationSec": 1.0, "exitThreshold": 0.85, "minMoveDurationSec": 0.2})),
        "phases": raw.get("phases", []),
    }


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not PROTOCOL_ID.fullmatch(str(protocol.get("id", ""))):
        errors.append("Protocol ID must contain only lowercase letters, numbers, and underscores")
    if not str(protocol.get("name", "")).strip():
        errors.append("Protocol name is required")
    total = float(protocol.get("totalDurationSec", 0))
    if total <= 0:
        errors.append("Total duration must be positive")
    previous_end = -1.0
    for index, shock in enumerate(protocol.get("shocks", []), start=1):
        time_sec = float(shock.get("timeSec", 0))
        duration = float(shock.get("durationSec", 0))
        intensity = float(shock.get("intensityMA", 0))
        if time_sec < 0 or time_sec + duration > total:
            errors.append(f"Shock #{index} is outside protocol duration")
        if duration <= 0:
            errors.append(f"Shock #{index} duration must be positive")
        if not 0 <= intensity <= 4:
            errors.append(f"Shock #{index} intensity must be between 0 and 4 mA")
        if time_sec < previous_end:
            errors.append(f"Shock #{index} overlaps the previous shock")
        previous_end = max(previous_end, time_sec + duration)
    freeze = protocol.get("freezeDefaults", {})
    threshold = float(freeze.get("threshold", 0.65))
    exit_threshold = float(freeze.get("exitThreshold", threshold))
    if threshold <= 0:
        errors.append("Freeze threshold must be positive")
    if exit_threshold < threshold:
        errors.append("Exit threshold must be greater than or equal to freeze threshold")
    if exit_threshold > 0.8:
        warnings.append(f"Exit threshold is high ({exit_threshold:.2f})")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "hash": _canonical_hash(protocol)}


class ProtocolRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, protocol_id: str) -> Path:
        if not PROTOCOL_ID.fullmatch(protocol_id):
            raise ValueError("invalid protocol id")
        return self.root / f"{protocol_id}.yml"

    def load_path(self, path: Path) -> dict[str, Any]:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"protocol file must contain an object: {path.name}")
        protocol = normalize_protocol(document)
        validation = validate_protocol(protocol)
        return {**protocol, "validation": validation, "path": str(path), "hash": validation["hash"]}

    def list(self) -> list[dict[str, Any]]:
        summaries = []
        if not self.root.exists():
            return summaries
        for path in sorted((*self.root.glob("*.yml"), *self.root.glob("*.yaml"))):
            try:
                protocol = self.load_path(path)
                summaries.append({key: protocol[key] for key in ("id", "name", "version", "totalDurationSec", "hash", "path")} | {"shockCount": len(protocol["shocks"]), "validationStatus": "valid" if protocol["validation"]["valid"] else "error", "warnings": protocol["validation"]["warnings"]})
            except Exception as exc:
                summaries.append({"id": path.stem, "name": path.stem, "version": "unknown", "totalDurationSec": 0, "shockCount": 0, "validationStatus": "error", "warnings": [], "error": str(exc), "path": str(path)})
        return summaries

    def load(self, protocol_id: str) -> dict[str, Any]:
        direct = self._path(protocol_id)
        candidates = [direct, direct.with_suffix(".yaml")]
        for path in candidates:
            if path.exists():
                return self.load_path(path)
        for summary in self.list():
            if summary["id"] == protocol_id:
                return self.load_path(Path(summary["path"]))
        raise FileNotFoundError(f"protocol not found: {protocol_id}")

    def save(self, protocol: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_protocol(protocol)
        validation = validate_protocol(normalized)
        if not validation["valid"]:
            raise ValueError("; ".join(validation["errors"]))
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(normalized["id"])
        document = {"schema_version": normalized["schemaVersion"], "protocol": {
            "id": normalized["id"], "name": normalized["name"], "version": normalized["version"],
            "description": normalized["description"], "author": normalized["author"], "total_duration_sec": normalized["totalDurationSec"],
            "freeze_defaults": normalized["freezeDefaults"], "phases": normalized["phases"],
            "shocks": [{"time_sec": item["timeSec"], "duration_sec": item["durationSec"], "current_mA": item["intensityMA"], "notes": item.get("notes", "")} for item in normalized["shocks"]],
        }}
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
        temporary.replace(path)
        return self.load_path(path)


def generate_schedule(config: dict[str, Any]) -> list[dict[str, Any]]:
    mode = str(config.get("mode", "fixed"))
    duration = float(config.get("durationSec", 2.0))
    intensity = float(config.get("intensityMA", 0.8))
    seed = int(config.get("seed", 42))
    rng = random.Random(seed)
    times: list[float]
    if mode == "fixed":
        start, end, interval, jitter = (float(config.get(key, default)) for key, default in (("startTimeSec", 0), ("endTimeSec", 0), ("intervalSec", 1), ("jitterSec", 0)))
        if interval <= 0 or end < start:
            raise ValueError("fixed interval configuration is invalid")
        times, current = [], start
        while current <= end + 1e-9:
            times.append(max(start, min(end, current + (rng.uniform(-jitter / 2, jitter / 2) if jitter else 0))))
            current += interval
    elif mode == "random":
        start, end = float(config["startTimeSec"]), float(config["endTimeSec"])
        count = int(config["numberOfEvents"])
        if count <= 0 or end <= start:
            raise ValueError("random interval configuration is invalid")
        times = sorted(rng.uniform(start, end) for _ in range(count))
    elif mode == "manual":
        times = [float(line.split(",")[0].strip()) for line in str(config.get("text", "")).splitlines() if line.strip()]
    else:
        raise ValueError(f"unknown schedule mode: {mode}")
    return [{"id": f"shock-{index + 1}", "timeSec": round(value, 3), "durationSec": duration, "intensityMA": intensity, "notes": ""} for index, value in enumerate(times)]


def dry_run_protocol(protocol: dict[str, Any]) -> list[str]:
    normalized = normalize_protocol(protocol)
    validation = validate_protocol(normalized)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    lines = ["0.000 Protocol started"]
    for index, shock in enumerate(normalized["shocks"], start=1):
        start = shock["timeSec"]
        end = start + shock["durationSec"]
        lines.extend((f"{start:.3f} Shock #{index} would trigger", f"{end:.3f} Shock #{index} would end"))
    lines.append(f"{normalized['totalDurationSec']:.3f} Protocol finished")
    return lines
