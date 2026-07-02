"""
VideoCaptureWorker: 独立线程中读取视频帧，通过 signal 将帧数据传回主线程。
可选：实时 freeze 检测，通过 freeze_result 信号回传。
"""
import sys
from typing import Optional, TYPE_CHECKING

import cv2
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QImage

if TYPE_CHECKING:
    from .freeze_detection import FreezeDetector


def _is_windows() -> bool:
    return sys.platform.startswith("win")


class VideoCaptureWorker(QObject):
    """在独立线程中从摄像头读取帧，通过信号传递 QImage 与元数据。"""

    # 每帧就绪：QImage, width, height, fps
    frame_ready = Signal(QImage, int, int, float)
    # 实时 freeze 检测结果（仅当启用检测时发射）：is_freezing, motion_level
    freeze_result = Signal(bool, float)
    # 处理图（运动二值图）供右侧显示，仅当启用检测且有图时发射
    processed_frame_ready = Signal(QImage)
    # 错误信息
    error_occurred = Signal(str)
    # 采集已停止（正常或异常）
    finished_signal = Signal()

    def __init__(self, source: int, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._source = source
        self._cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._thread: Optional[QThread] = None
        self._freeze_detector: Optional["FreezeDetector"] = None
        self._record_path: Optional[str] = None
        self._writer: Optional[cv2.VideoWriter] = None

    def set_source(self, source: int) -> None:
        self._source = source

    def set_freeze_detector(self, detector: Optional["FreezeDetector"]) -> None:
        self._freeze_detector = detector

    def update_freeze_params(self, threshold: float, duration_sec: float) -> None:
        """主线程可调：运行时更新检测阈值与持续时长，下一帧起生效。"""
        if self._freeze_detector is None:
            return
        self._freeze_detector.set_threshold(threshold)
        self._freeze_detector.set_duration_sec(duration_sec)

    def update_freeze_roi(
        self,
        area_type: Optional[str],
        area_points: Optional[list[list[int]]],
    ) -> None:
        """主线程可调：运行时更新检测 ROI，下一帧起生效。"""
        if self._freeze_detector is None:
            return
        self._freeze_detector.set_roi(area_type, area_points)

    def start_capture(self, record_path: Optional[str] = None) -> bool:
        """在调用线程中打开摄像头并启动采集线程。record_path 非空时同时写入视频文件。返回是否打开成功。"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._record_path: Optional[str] = str(record_path) if record_path else None
        self._writer: Optional[cv2.VideoWriter] = None
        backend = cv2.CAP_DSHOW if _is_windows() else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(self._source, backend)
        if not self._cap.isOpened():
            self.error_occurred.emit("无法打开摄像头")
            return False
        self._running = True
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run_loop)
        self._thread.start()
        return True

    def stop_capture(self) -> None:
        """请求停止采集并释放资源。"""
        self._running = False
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            # _run_loop 也会从采集线程自身进入这里。线程不能等待自身，
            # 否则设备断开/读帧失败时会出现 QThread::wait 自等待问题。
            if QThread.currentThread() is not self._thread:
                self._thread.wait(3000)
        if self._writer is not None:
            try:
                self._writer.release()
            except Exception:
                pass
            self._writer = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._thread = None
        self._record_path = None
        self.finished_signal.emit()

    def _run_loop(self) -> None:
        """在采集线程中执行：读帧 -> (可选写入视频) -> BGR 转 RGB -> QImage -> 发射信号。"""
        if self._cap is None or not self._cap.isOpened():
            self.error_occurred.emit("摄像头未打开")
            self.finished_signal.emit()
            return
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        if self._record_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(self._record_path, fourcc, fps, (w, h))
            if not self._writer.isOpened():
                self._writer = None
        if self._freeze_detector is not None:
            self._freeze_detector.fps = fps
            self._freeze_detector.over_th_frame_num = max(
                int(self._freeze_detector.duration_sec * fps), 1
            )
            self._freeze_detector.reset()
        while self._running and self._cap is not None:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                self.error_occurred.emit("读取帧失败或设备断开")
                break
            try:
                if self._writer is not None and self._writer.isOpened():
                    self._writer.write(frame)
                if self._freeze_detector is not None:
                    is_freeze, motion, thresh_img = self._freeze_detector.push_frame(frame)
                    self.freeze_result.emit(is_freeze, motion)
                    if thresh_img is not None and thresh_img.size > 0:
                        h, w = thresh_img.shape[:2]
                        if len(thresh_img.shape) == 2:
                            gray = np.ascontiguousarray(thresh_img)
                            qi_proc = QImage(
                                gray.data,
                                w,
                                h,
                                w,
                                QImage.Format.Format_Grayscale8,
                            )
                        else:
                            rgb = np.ascontiguousarray(
                                cv2.cvtColor(thresh_img, cv2.COLOR_GRAY2RGB)
                            )
                            qi_proc = QImage(
                                rgb.data,
                                w,
                                h,
                                w * 3,
                                QImage.Format.Format_RGB888,
                            )
                        self.processed_frame_ready.emit(qi_proc.copy())
                # BGR -> RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qi = QImage(
                    rgb.data,
                    w,
                    h,
                    bytes_per_line,
                    QImage.Format.Format_RGB888,
                )
                qi = qi.copy()
                self.frame_ready.emit(qi, w, h, fps)
            except Exception as e:
                self.error_occurred.emit(f"帧转换错误: {e}")
                break
        self.stop_capture()

    def get_current_frame_copy(self):  # -> Optional[np.ndarray]，预留扩展
        """供截图等使用：当前由 Controller 用最后一帧 QImage 保存。"""
        return None
