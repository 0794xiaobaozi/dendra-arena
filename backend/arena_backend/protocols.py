from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

import yaml


PROTOCOL_ID = re.compile(r"^[a-z0-9_]+$")
_REGISTRY_FILE = "protocol_registry.json"
_SUMMARY_KEYS = ("id", "name", "version", "totalDurationSec", "hash", "path")


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
        self._registry: dict[str, dict[str, Any]] = {}
        self._load_registry()
        self._sync_filesystem()

    @property
    def _registry_path(self) -> Path:
        return self.root / _REGISTRY_FILE

    def _path(self, protocol_id: str) -> Path:
        if not PROTOCOL_ID.fullmatch(protocol_id):
            raise ValueError("invalid protocol id")
        return self.root / f"{protocol_id}.yml"

    def _read_registry_json(self) -> dict[str, Any]:
        if not self._registry_path.is_file():
            return {"registry_version": 1, "protocols": {}}
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("protocols"), dict):
                return data
        except Exception:
            pass
        return {"registry_version": 1, "protocols": {}}

    def _write_registry_json(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self._registry_path.with_suffix(self._registry_path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self._registry_path)

    def _load_registry(self) -> None:
        data = self._read_registry_json()
        self._registry = {}
        for entry in data.get("protocols", {}).values():
            if isinstance(entry, dict) and entry.get("id"):
                self._registry[entry["id"]] = entry

    def _make_summary(self, protocol: dict[str, Any], path: Path) -> dict[str, Any]:
        return {key: protocol[key] for key in _SUMMARY_KEYS} | {
            "shockCount": len(protocol["shocks"]),
            "validationStatus": "valid" if protocol["validation"]["valid"] else "error",
            "warnings": protocol["validation"]["warnings"],
        }

    def _load_path(self, path: Path) -> dict[str, Any]:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"protocol file must contain an object: {path.name}")
        protocol = normalize_protocol(document)
        validation = validate_protocol(protocol)
        return {**protocol, "validation": validation, "path": str(path), "hash": validation["hash"]}

    def load_path(self, path: Path) -> dict[str, Any]:
        return self._load_path(path)

    def _sync_filesystem(self) -> None:
        if not self.root.exists():
            self._registry.clear()
            return
        disk_stems: set[str] = set()
        for extension in ("*.yml", "*.yaml"):
            for path in self.root.glob(extension):
                disk_stems.add(path.stem)
        stale_ids = [pid for pid, entry in self._registry.items() if Path(entry["path"]).stem not in disk_stems]
        for pid in stale_ids:
            del self._registry[pid]
        known_stems = {Path(entry["path"]).stem for entry in self._registry.values()}
        new_stems = disk_stems - known_stems
        if not new_stems:
            return
        for stem in new_stems:
            yml_path = self.root / f"{stem}.yml"
            if not yml_path.exists():
                yml_path = self.root / f"{stem}.yaml"
            if not yml_path.exists():
                continue
            try:
                protocol = self._load_path(yml_path)
                pid = protocol["id"]
                self._registry[pid] = self._make_summary(protocol, yml_path)
            except Exception as exc:
                self._registry[stem] = {
                    "id": stem, "name": stem, "version": "unknown",
                    "totalDurationSec": 0, "shockCount": 0, "validationStatus": "error",
                    "warnings": [], "error": str(exc), "path": str(yml_path),
                }
        if stale_ids or new_stems:
            self._flush_registry()

    def _flush_registry(self) -> None:
        self._write_registry_json({"registry_version": 1, "protocols": self._registry})

    def list(self) -> list[dict[str, Any]]:
        self._sync_filesystem()
        return list(self._registry.values())

    def load(self, protocol_id: str) -> dict[str, Any]:
        self._sync_filesystem()
        entry = self._registry.get(protocol_id)
        if not entry:
            raise FileNotFoundError(f"protocol not found: {protocol_id}")
        path = Path(entry["path"])
        if not path.exists():
            del self._registry[protocol_id]
            self._flush_registry()
            raise FileNotFoundError(f"protocol file missing: {path}")
        return self._load_path(path)

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
        protocol = self._load_path(path)
        self._registry[normalized["id"]] = self._make_summary(protocol, path)
        self._flush_registry()
        return protocol


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
