from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def validate_roi(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode", "rectangle")).lower().replace(" ", "_")
    image_width = int(payload.get("imageWidth", 0))
    image_height = int(payload.get("imageHeight", 0))
    errors: list[str] = []
    if image_width <= 0 or image_height <= 0:
        errors.append("Image dimensions must be positive")
    if mode == "full_frame":
        x, y, width, height = 0, 0, image_width, image_height
    elif mode == "rectangle":
        x, y = int(payload.get("x", 0)), int(payload.get("y", 0))
        width, height = int(payload.get("width", 0)), int(payload.get("height", 0))
        if x < 0 or y < 0:
            errors.append("ROI origin must be inside the image")
        if width <= 0 or height <= 0:
            errors.append("ROI width and height must be positive")
        if image_width > 0 and x + width > image_width:
            errors.append("ROI exceeds image width")
        if image_height > 0 and y + height > image_height:
            errors.append("ROI exceeds image height")
    else:
        errors.append(f"Unsupported ROI mode: {mode}")
        x = y = width = height = 0
    normalized = {
        "x": x / image_width if image_width else 0,
        "y": y / image_height if image_height else 0,
        "width": width / image_width if image_width else 0,
        "height": height / image_height if image_height else 0,
    }
    return {"valid": not errors, "errors": errors, "mode": mode, "x": x, "y": y, "width": width, "height": height, "imageWidth": image_width, "imageHeight": image_height, "normalized": normalized}


def inspect_directory(path_value: str, *, test_write: bool = True) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.exists():
        existing = Path.home()
    writable = False
    error: str | None = None
    if test_write:
        try:
            path.mkdir(parents=True, exist_ok=True)
            descriptor, probe = tempfile.mkstemp(prefix=".arena-write-probe-", dir=path)
            os.close(descriptor)
            Path(probe).unlink(missing_ok=True)
            writable = True
        except Exception as exc:
            error = str(exc)
    else:
        writable = os.access(existing, os.W_OK)
    usage = shutil.disk_usage(existing)
    return {"path": str(path), "exists": path.exists(), "writable": writable, "freeGB": usage.free / 1024**3, "error": error}


def _check(check_id: str, level: str, message: str, *, blocking: bool = False, detail: str | None = None) -> dict[str, Any]:
    return {"id": check_id, "level": level, "message": message, "blocking": blocking, "detail": detail}


def run_preflight(session: dict[str, Any], stimulator_status: dict[str, Any], detected_camera_ids: set[str] | None = None) -> dict[str, Any]:
    global_checks: list[dict[str, Any]] = []
    name = str(session.get("name", "")).strip()
    if not name:
        global_checks.append(_check("session-name", "error", "Experiment name is required", blocking=True))
    elif any(char in INVALID_FILENAME_CHARS for char in name):
        global_checks.append(_check("session-name", "error", "Experiment name contains invalid filename characters", blocking=True))
    else:
        global_checks.append(_check("session-name", "success", "Experiment name is valid"))

    save_dir = str(session.get("saveDir", "")).strip()
    if not save_dir:
        directory = {"path": "", "exists": False, "writable": False, "freeGB": 0, "error": "Save directory is required"}
    else:
        directory = inspect_directory(save_dir)
    global_checks.append(_check("output-directory", "success" if directory["writable"] else "error", "Output directory is writable" if directory["writable"] else "Output directory is not writable", blocking=not directory["writable"], detail=directory.get("error")))
    enough_space = float(directory["freeGB"]) >= float(session.get("minimumFreeGB", 5))
    global_checks.append(_check("disk-space", "success" if enough_space else "error", f"Disk space: {directory['freeGB']:.1f} GB free", blocking=not enough_space))

    boxes = session.get("boxes", [])
    if not isinstance(boxes, list) or not boxes:
        global_checks.append(_check("boxes", "error", "At least one box is required", blocking=True))
        boxes = []
    else:
        global_checks.append(_check("boxes", "success", f"{len(boxes)} boxes configured"))

    shock_required = any(bool(box.get("shockEnabled", False)) for box in boxes if isinstance(box, dict))
    if shock_required:
        connected = bool(stimulator_status.get("connected"))
        calibrated = bool(stimulator_status.get("calibrated"))
        if not connected:
            global_checks.append(_check("stimulator", "error", "Shock controller is not connected", blocking=True))
        elif not calibrated:
            global_checks.append(_check("stimulator-calibration", "error", "Shock duration is not calibrated", blocking=True))
        else:
            global_checks.append(_check("stimulator", "success", "Shock controller connected and calibrated"))
    else:
        global_checks.append(_check("stimulator", "info", "Shock controller not required"))

    box_checks: dict[str, list[dict[str, Any]]] = {}
    for index, box in enumerate(boxes):
        box_id = str(box.get("id", f"box-{index + 1}"))
        checks: list[dict[str, Any]] = []
        camera = str(box.get("cameraId", box.get("camera", ""))).strip()
        camera_assigned = bool(camera and camera.lower() != "unassigned")
        camera_detected = detected_camera_ids is None or camera in detected_camera_ids
        camera_valid = camera_assigned and camera_detected
        camera_message = "Camera assigned and detected" if camera_valid else "Camera is not assigned" if not camera_assigned else "Assigned camera is not currently detected"
        checks.append(_check("camera", "success" if camera_valid else "error", camera_message, blocking=not camera_valid))
        roi = box.get("roi")
        if isinstance(roi, dict):
            roi_result = validate_roi({**roi, "imageWidth": roi.get("imageWidth", 1920), "imageHeight": roi.get("imageHeight", 1080)})
            checks.append(_check("roi", "success" if roi_result["valid"] else "error", "ROI defined" if roi_result["valid"] else "; ".join(roi_result["errors"]), blocking=not roi_result["valid"]))
        else:
            checks.append(_check("roi", "error", "ROI is missing", blocking=True))
        protocol = str(box.get("protocolTemplateId", box.get("protocol", ""))).strip()
        checks.append(_check("protocol", "success" if protocol and protocol.lower() != "unassigned" else "error", "Protocol assigned" if protocol and protocol.lower() != "unassigned" else "Protocol is not assigned", blocking=not protocol or protocol.lower() == "unassigned"))
        freeze = box.get("freeze", {})
        threshold = float(freeze.get("threshold", 0.65))
        exit_threshold = float(freeze.get("exitThreshold", threshold))
        freeze_valid = threshold > 0 and exit_threshold >= threshold
        checks.append(_check("freeze", "success" if freeze_valid else "error", "Freeze settings valid" if freeze_valid else "Freeze settings are invalid", blocking=not freeze_valid))
        box_checks[box_id] = checks

    blocking_reasons = [item["message"] for item in global_checks if item["blocking"]]
    blocking_reasons.extend(item["message"] for checks in box_checks.values() for item in checks if item["blocking"])
    return {"global": global_checks, "boxes": box_checks, "canRun": not blocking_reasons, "blockingReasons": blocking_reasons, "directory": directory, "stimulator": stimulator_status}


def save_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
