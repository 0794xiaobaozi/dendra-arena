from __future__ import annotations

import json
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .camera import discover_cameras
from .experiment import ExperimentRunner
from .protocols import ProtocolRegistry, dry_run_protocol, generate_schedule, normalize_protocol, validate_protocol
from .schemas import parse_camera, parse_session
from .setup_services import run_preflight, save_json_atomic, validate_roi
from .stimulator import StimulatorController


class BackendApplication:
    def __init__(self, event_sink, project_root: Path | None = None, stimulator: StimulatorController | None = None):
        self._event_sink = event_sink
        self._stimulator = stimulator or StimulatorController()
        self._runner = ExperimentRunner(event_sink, self._stimulator)
        self._project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
        self._protocols = ProtocolRegistry(self._project_root / "protocols")
        self._last_cameras: list[dict[str, Any]] = []

    def execute(self, command_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "ping": self._ping,
            "discover_cameras": self._discover,
            "list_cameras": self._discover,
            "validate_roi": self._validate_roi,
            "run_preflight_check": self._preflight,
            "save_session_draft": self._save_session_draft,
            "load_session_draft": self._load_session_draft,
            "lock_session_for_run": self._lock_session,
            "list_protocol_templates": self._list_protocols,
            "load_protocol_template": self._load_protocol,
            "import_protocol_yaml": self._import_protocol,
            "validate_protocol": self._validate_protocol,
            "save_protocol_template": self._save_protocol,
            "generate_shock_schedule": self._generate_schedule,
            "dry_run_protocol": self._dry_run,
            "get_stimulator_status": self._stimulator_status,
            "connect_stimulator": self._connect_stimulator,
            "arm_stimulator": self._arm_stimulator,
            "disarm_stimulator": self._disarm_stimulator,
            "stimulator_test": self._stimulator_test,
            "send_raw_packet": self._send_raw_packet,
            "send_raw_ctrl": self._send_raw_ctrl,
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
        self._last_cameras = discover_cameras(int(payload.get("maxIndex", 10)))
        return {"cameras": self._last_cameras}

    def _validate_roi(self, payload: dict[str, Any]) -> dict[str, Any]:
        return validate_roi(payload)

    def _preflight(self, payload: dict[str, Any]) -> dict[str, Any]:
        detected = {str(item["deviceId"]) for item in self._last_cameras} if self._last_cameras else None
        return run_preflight(payload.get("sessionDraft", payload), self._stimulator.status().to_payload(), detected)

    def _save_session_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = payload.get("sessionDraft", payload)
        directory = Path(str(draft["saveDir"]))
        path = directory / f"{draft.get('name', 'session')}.arena.json"
        save_json_atomic(path, {"schemaVersion": 1, "status": "draft", "session": draft})
        return {"path": str(path)}

    def _load_session_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(payload["path"]))
        if not path.is_file():
            raise ValueError(f"Session file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        session = data.get("session", data)
        return {"path": str(path), "session": session}

    def _lock_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = payload.get("sessionDraft", payload)
        result = run_preflight(draft, self._stimulator.status().to_payload())
        if not result["canRun"]:
            raise ValueError("; ".join(result["blockingReasons"]))
        directory = Path(str(draft["saveDir"]))
        locked = {"schemaVersion": 1, "status": "locked", "lockedAt": datetime.now(timezone.utc).isoformat(), "session": draft}
        path = directory / f"{draft.get('name', 'session')}.locked.arena.json"
        save_json_atomic(path, locked)
        return {"path": str(path), "lockedConfig": locked, "preflight": result}

    def _list_protocols(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"protocols": self._protocols.list()}

    def _load_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"protocol": self._protocols.load(str(payload["protocolId"]))}

    def _import_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        imported = self._protocols.load_path(Path(str(payload["path"])))
        return {"protocol": self._protocols.save(imported)}

    def _validate_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        return validate_protocol(normalize_protocol(payload.get("protocolDraft", payload)))

    def _save_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"protocol": self._protocols.save(payload.get("protocolDraft", payload))}

    def _generate_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"events": generate_schedule(payload.get("generatorConfig", payload))}

    def _dry_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"lines": dry_run_protocol(payload.get("protocolDraft", payload))}

    def _stimulator_status(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.status().to_payload()

    def _connect_stimulator(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.connect().to_payload()

    def _arm_stimulator(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.arm(bool(payload.get("confirmed", False))).to_payload()

    def _disarm_stimulator(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.disarm().to_payload()

    def _stimulator_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.trigger(float(payload["currentMA"]), float(payload["durationSeconds"]), confirmed=bool(payload.get("confirmed", False)))

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
        if session.enable_stimulator:
            status = self._stimulator.status()
            if not status.connected or not status.calibrated or not status.armed:
                raise RuntimeError("stimulator must be connected, calibrated, and armed before starting")
        self._runner.start_experiment(session)
        return {"status": self._runner.state, "sessionId": session.session_id}

    def _stop(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self._runner.stop()
        return {"status": self._runner.state}

    def _snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        output_dir = Path(str(payload.get("outputDir", Path.home() / "Pictures" / "arena")))
        path = self._runner.snapshot(str(payload["boxId"]), output_dir)
        return {"path": str(path)}

    def _send_raw_packet(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.send_raw_packet(str(payload["packetHex"]))

    def _send_raw_ctrl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._stimulator.send_raw_ctrl(
            str(payload.get("requestType", "40")),
            str(payload.get("request", "00")),
            str(payload.get("value", "0000")),
            str(payload.get("index", "0000")),
        )

    def shutdown(self) -> None:
        self._runner.stop()
        self._stimulator.close()
