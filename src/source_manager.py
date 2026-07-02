"""
SourceManager: 视频源管理，枚举本机摄像头；文件和 RTSP 作为可扩展项。
"""
import json
import subprocess
import threading
from typing import List, Tuple

import cv2


class SourceManager:
    """视频源枚举与管理。第一版仅支持本机摄像头。"""

    # 可扩展：SOURCE_TYPE_CAMERA, SOURCE_TYPE_FILE, SOURCE_TYPE_RTSP
    SOURCE_TYPE_CAMERA = "camera"

    @staticmethod
    def enumerate_cameras(
        max_index: int = 10,
        probe_timeout_sec: float = 1.0,
        uvc_only: bool = True,
    ) -> List[Tuple[int, str]]:
        """
        枚举本机摄像头。返回 [(index, "Camera 0"), ...]。
        """
        if _is_windows() and uvc_only:
            return _enumerate_windows_uvc_cameras(max_index, probe_timeout_sec)
        result: List[Tuple[int, str]] = []
        for i in range(max_index):
            if _probe_camera_index(i, probe_timeout_sec):
                result.append((i, f"Camera {i}"))
        return result

    @staticmethod
    def get_source_display_name(source_type: str, source_id) -> str:
        """获取用于 UI 显示的源名称。"""
        if source_type == SourceManager.SOURCE_TYPE_CAMERA:
            return f"Camera {source_id}"
        # 可扩展：文件显示文件名，RTSP 显示 URL 片段
        return str(source_id)


def _is_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


def _probe_camera_index(index: int, timeout_sec: float) -> bool:
    backend = cv2.CAP_DSHOW if _is_windows() else cv2.CAP_ANY
    result = {"opened": False}

    def _target() -> None:
        cap = None
        try:
            cap = cv2.VideoCapture(index, backend)
            result["opened"] = bool(cap.isOpened())
        except Exception:
            result["opened"] = False
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_sec)
    if thread.is_alive():
        return False
    return bool(result["opened"])


def _enumerate_windows_uvc_cameras(
    max_index: int,
    probe_timeout_sec: float,
) -> List[Tuple[int, str]]:
    uvc_names = _get_windows_uvc_camera_names()
    if not uvc_names:
        return []

    opened_indices: List[int] = []
    for i in range(max_index):
        if _probe_camera_index(i, probe_timeout_sec):
            opened_indices.append(i)
            if len(opened_indices) >= len(uvc_names):
                break

    result: List[Tuple[int, str]] = []
    for pos, idx in enumerate(opened_indices):
        name = uvc_names[pos] if pos < len(uvc_names) else f"UVC Camera {idx}"
        result.append((idx, name))
    return result


def _get_windows_uvc_camera_names() -> List[str]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$items = Get-CimInstance Win32_PnPEntity | "
            "Where-Object { ($_.PNPClass -in @('Camera','Image')) -and $_.Service -eq 'usbvideo' } | "
            "Select-Object -ExpandProperty Name; "
            "if ($null -eq $items) { '[]' } else { $items | ConvertTo-Json -Compress }"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
            check=False,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    raw = completed.stdout.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    return []
