"""
ConfigService: 应用配置（截图路径、默认源等），便于后续扩展。
"""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings


class ConfigService:
    """应用配置服务。"""

    def __init__(self):
        self._screenshot_dir: Path = Path.home() / "Pictures" / "LiveFreeze"
        self._default_source: Optional[int] = None  # 本机摄像头索引，如 0
        self._settings = QSettings("LiveFreeze", "LiveFreeze")

    @property
    def screenshot_dir(self) -> Path:
        return self._screenshot_dir

    @screenshot_dir.setter
    def screenshot_dir(self, value: Path) -> None:
        self._screenshot_dir = Path(value)

    @property
    def default_source(self) -> Optional[int]:
        return self._default_source

    @default_source.setter
    def default_source(self, value: Optional[int]) -> None:
        self._default_source = value

    def ensure_screenshot_dir(self) -> Path:
        """确保截图目录存在，返回目录路径。"""
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        return self._screenshot_dir

    def camera_label(self, device_name: str, default: str) -> str:
        """按设备名称读取用户定义的实验箱标签。"""
        value = self._settings.value(f"camera_labels/{device_name}", default)
        return str(value).strip() or default

    def set_camera_label(self, device_name: str, label: str) -> None:
        """持久化摄像头标签，供下次枚举时恢复。"""
        self._settings.setValue(f"camera_labels/{device_name}", label.strip())

    def language(self) -> str:
        value = str(self._settings.value("ui/language", "en"))
        return value if value in ("en", "zh") else "en"

    def set_language(self, language: str) -> None:
        if language in ("en", "zh"):
            self._settings.setValue("ui/language", language)
