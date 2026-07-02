"""
VideoController: 协调 VideoCaptureWorker 与视频源，提供开始/停止/截图接口。
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QImage

from .config_service import ConfigService
from .freeze_detection import FreezeDetector
from .source_manager import SourceManager
from .video_capture_worker import VideoCaptureWorker


class VideoController:
    """协调采集线程与业务逻辑，主线程仅通过 Controller 与 Worker 交互。"""

    def __init__(self, config: ConfigService):
        self._config = config
        self._worker: Optional[VideoCaptureWorker] = None
        self._last_image: Optional[QImage] = None
        self._last_width = 0
        self._last_height = 0
        self._last_fps = 0.0

    @property
    def worker(self) -> Optional[VideoCaptureWorker]:
        return self._worker

    def start_preview(
        self,
        source: int,
        enable_freeze_detection: bool = True,
        freeze_threshold: float = 0.0003,
        freeze_duration_sec: float = 0.5,
        record_path: Optional[Path] = None,
        roi_area_type: Optional[str] = None,
        roi_area_points: Optional[list[list[int]]] = None,
    ) -> bool:
        """开始预览。enable_freeze_detection 为 True 时启用 freeze 检测；record_path 非空时同时录制视频。"""
        self.stop_preview()
        self._worker = VideoCaptureWorker(source)
        if enable_freeze_detection:
            self._worker.set_freeze_detector(
                FreezeDetector(
                    fps=30.0,
                    threshold=str(freeze_threshold),
                    duration_str=f"{freeze_duration_sec}s",
                    delay=0.0,
                    duration=0.0,
                    area_type=roi_area_type,
                    area_points=roi_area_points,
                )
            )
        path_str = str(record_path) if record_path else None
        if not self._worker.start_capture(record_path=path_str):
            return False
        return True

    def update_freeze_params(self, threshold: float, duration_sec: float) -> None:
        """运行时更新冻结检测参数，仅当正在预览且启用了检测时生效。"""
        if self._worker is not None:
            self._worker.update_freeze_params(threshold, duration_sec)

    def update_freeze_roi(
        self,
        area_type: Optional[str],
        area_points: Optional[list[list[int]]],
    ) -> None:
        """运行时更新冻结检测 ROI，仅当正在预览且启用了检测时生效。"""
        if self._worker is not None:
            self._worker.update_freeze_roi(area_type, area_points)

    def stop_preview(self) -> None:
        """安全停止并释放 VideoCapture。"""
        if self._worker is not None:
            self._worker.stop_capture()
            self._worker = None
        self._last_image = None

    def on_frame_ready(self, image: QImage, width: int, height: int, fps: float) -> None:
        """由主线程连接 worker.frame_ready 调用，缓存最后一帧供截图与显示。"""
        self._last_image = image
        self._last_width = width
        self._last_height = height
        self._last_fps = fps

    def get_last_image_copy(self) -> Optional[QImage]:
        """返回最后一帧的拷贝，供 ROI 选择等用途。"""
        if self._last_image is None or self._last_image.isNull():
            return None
        return self._last_image.copy()

    def take_snapshot(self) -> Optional[Path]:
        """
        保存当前帧为截图。返回保存后的文件路径，失败返回 None。
        """
        if self._last_image is None or self._last_image.isNull():
            return None
        dir_path = self._config.ensure_screenshot_dir()
        name = f"livefreeze_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = dir_path / name
        if self._last_image.save(str(path)):
            return path
        return None

    def last_frame_info(self) -> tuple[int, int, float]:
        """返回 (width, height, fps)。"""
        return self._last_width, self._last_height, self._last_fps
