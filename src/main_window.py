"""
MainWindow: 主窗口 — 顶部工具栏、中央视频区域、底部状态栏。
主线程只负责 GUI；采集线程通过 signal/slot 更新画面与状态。
支持实验方案选择与 Freeze 触发电刺激。
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QPoint, QRect, Signal, QObject, QThread
from PySide6.QtGui import (
    QPixmap,
    QImage,
    QResizeEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QColor,
    QCloseEvent,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QLabel,
    QStatusBar,
    QMessageBox,
    QSizePolicy,
    QCheckBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QDockWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from .app_icon import create_app_icon
from .config_service import ConfigService
from .experiment_protocol import get_protocol_list, ExperimentProtocol
from .source_manager import SourceManager
from .video_controller import VideoController
from .shock_service import ShockService


# 与视频区域一致的深色背景，避免 matplotlib 默认白底与系统主题不符
_PLOT_BG = "#2d2d2d"
_PLOT_TEXT = "#b0b0b0"
_PLOT_SPINE = "#555555"


class FreezeRasterWidget(QWidget):
    """简单的冻结 raster 图：x 为时间，y 为 0/1；深色背景与 GUI 一致。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._figure = Figure(figsize=(6, 0.65), facecolor=_PLOT_BG)
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setStyleSheet(f"background-color: {_PLOT_BG};")
        layout.addWidget(self._canvas)

        self._ax = self._figure.add_subplot(111, facecolor=_PLOT_BG)
        self._ax.set_ylabel("Freeze", color=_PLOT_TEXT)
        self._ax.set_xlabel("Time (s)", color=_PLOT_TEXT)
        self._ax.set_ylim(-0.2, 1.2)
        self._ax.set_yticks([0, 1])
        self._ax.set_yticklabels(["No", "Yes"], color=_PLOT_TEXT)
        self._ax.tick_params(axis="x", colors=_PLOT_TEXT)
        self._ax.grid(True, axis="x", linestyle="--", alpha=0.35, color=_PLOT_SPINE)
        for spine in self._ax.spines.values():
            spine.set_color(_PLOT_SPINE)

        self._times: list[float] = []
        self._values: list[float] = []
        self._shock_times: list[float] = []
        self._shock_values: list[float] = []
        (self._line,) = self._ax.plot([], [], drawstyle="steps-post", color="#d55e00")
        (self._shock_line,) = self._ax.plot(
            [],
            [],
            drawstyle="steps-post",
            color="#4fc3f7",
            linewidth=3.2,
        )
        self._canvas.draw_idle()

    def reset(self) -> None:
        self._times.clear()
        self._values.clear()
        self._shock_times.clear()
        self._shock_values.clear()
        self._line.set_data([], [])
        self._shock_line.set_data([], [])
        self._ax.set_xlim(0, 1)
        self._canvas.draw_idle()

    def append_point(self, t: float, is_freeze: bool) -> None:
        self._times.append(t)
        self._values.append(1.0 if is_freeze else 0.0)
        self._line.set_data(self._times, self._values)
        self._update_xlim()
        self._canvas.draw_idle()

    def add_shock_interval(self, start_t: float, end_t: float) -> None:
        start = max(0.0, float(start_t))
        end = max(start, float(end_t))
        if end == start:
            end = start + 0.05
        if not self._shock_times:
            self._shock_times.extend([0.0, start])
            self._shock_values.extend([0.0, 0.0])
        elif self._shock_times[-1] < start:
            self._shock_times.append(start)
            self._shock_values.append(self._shock_values[-1])
        self._shock_times.extend([start, end, end])
        self._shock_values.extend([0.5, 0.5, 0.0])
        self._shock_line.set_data(self._shock_times, self._shock_values)
        self._update_xlim()
        self._canvas.draw_idle()

    def _update_xlim(self) -> None:
        xs = self._times + self._shock_times
        if xs:
            t_max = max(xs)
            self._ax.set_xlim(0, max(1.0, t_max * 1.05))


class VideoDisplayLabel(QLabel):
    """视频显示区域，resize 时保持画面比例。"""
    roi_selected = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None, placeholder: str = "无视频源"):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #1e1e1e; color: #888;")
        self._placeholder = placeholder
        self.setText(placeholder)
        self._current_pixmap: Optional[QPixmap] = None
        self._source_size: Optional[QSize] = None  # 原始宽高，用于比例
        self._roi_points: Optional[list[list[int]]] = None
        self._roi_edit_mode = False
        self._drag_origin: Optional[QPoint] = None
        self._drag_rect: QRect = QRect()

    def set_frame(self, image: QImage) -> None:
        """主线程通过 slot 调用：更新当前帧并按当前 label 大小缩放显示。"""
        if image.isNull():
            self._current_pixmap = None
            self._source_size = None
            self.clear()
            self.setText(self._placeholder)
            return
        self._current_pixmap = QPixmap.fromImage(image)
        self._source_size = QSize(image.width(), image.height())
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        scaled = self._current_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()
    def set_roi_points(self, points: Optional[list[list[int]]]) -> None:
        self._roi_points = points
        self.update()

    def set_roi_edit_mode(self, enabled: bool) -> None:
        self._roi_edit_mode = enabled
        self._drag_origin = None
        self._drag_rect = QRect()
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def _display_rect(self) -> Optional[QRect]:
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return None
        x = (self.width() - pm.width()) // 2
        y = (self.height() - pm.height()) // 2
        return QRect(x, y, pm.width(), pm.height())

    def _widget_rect_to_source_polygon(self, rect: QRect) -> Optional[list[list[int]]]:
        disp = self._display_rect()
        if disp is None or self._source_size is None:
            return None
        src_w, src_h = self._source_size.width(), self._source_size.height()
        if src_w <= 0 or src_h <= 0:
            return None
        rx1 = max(disp.left(), min(rect.left(), disp.right()))
        ry1 = max(disp.top(), min(rect.top(), disp.bottom()))
        rx2 = max(disp.left(), min(rect.right(), disp.right()))
        ry2 = max(disp.top(), min(rect.bottom(), disp.bottom()))
        if abs(rx2 - rx1) < 5 or abs(ry2 - ry1) < 5:
            return None
        x1 = int((rx1 - disp.left()) / max(disp.width(), 1) * src_w)
        y1 = int((ry1 - disp.top()) / max(disp.height(), 1) * src_h)
        x2 = int((rx2 - disp.left()) / max(disp.width(), 1) * src_w)
        y2 = int((ry2 - disp.top()) / max(disp.height(), 1) * src_h)
        x1, x2 = sorted((max(0, x1), min(src_w - 1, x2)))
        y1, y2 = sorted((max(0, y1), min(src_h - 1, y2)))
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

    def _source_polygon_to_widget_rect(self, points: list[list[int]]) -> Optional[QRect]:
        disp = self._display_rect()
        if disp is None or self._source_size is None or len(points) < 4:
            return None
        src_w, src_h = self._source_size.width(), self._source_size.height()
        if src_w <= 0 or src_h <= 0:
            return None
        x1, y1 = points[0]
        x2, y2 = points[2]
        wx1 = int(disp.left() + (x1 / src_w) * disp.width())
        wy1 = int(disp.top() + (y1 / src_h) * disp.height())
        wx2 = int(disp.left() + (x2 / src_w) * disp.width())
        wy2 = int(disp.top() + (y2 / src_h) * disp.height())
        return QRect(QPoint(wx1, wy1), QPoint(wx2, wy2)).normalized()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._roi_edit_mode or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        disp = self._display_rect()
        if disp is None:
            return
        p = event.position().toPoint()
        if not disp.contains(p):
            return
        self._drag_origin = p
        self._drag_rect = QRect(p, p)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._roi_edit_mode or self._drag_origin is None:
            return super().mouseMoveEvent(event)
        self._drag_rect = QRect(self._drag_origin, event.position().toPoint()).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._roi_edit_mode or event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        if self._drag_origin is None:
            return
        poly = self._widget_rect_to_source_polygon(self._drag_rect.normalized())
        self._drag_origin = None
        self._drag_rect = QRect()
        self._roi_edit_mode = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if poly:
            self._roi_points = poly
            self.roi_selected.emit(poly)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor("#00e5ff"), 2)
        painter.setPen(pen)
        if self._roi_points:
            rect = self._source_polygon_to_widget_rect(self._roi_points)
            if rect:
                painter.drawRect(rect)
        if self._roi_edit_mode and not self._drag_rect.isNull():
            pen2 = QPen(QColor("#ffee58"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen2)
            painter.drawRect(self._drag_rect.normalized())


class CameraRefreshWorker(QObject):
    finished = Signal(object)

    def __init__(self, source_manager: SourceManager):
        super().__init__()
        self._source_manager = source_manager

    def run(self) -> None:
        cameras = self._source_manager.enumerate_cameras()
        self.finished.emit(cameras)


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigService):
        super().__init__()
        self._config = config
        self._source_manager = SourceManager()
        self._controller = VideoController(config)
        self._shock_service = ShockService(self)

        self.setWindowTitle("LiveFreeze — 视频预览")
        self.setWindowIcon(create_app_icon())
        self.setMinimumSize(800, 520)
        self.resize(960, 640)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ——— 顶部：视频源 + 刷新 + 开始 + 停止 + 截图 ———
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)

        toolbar_layout.addWidget(QLabel("视频源:"))
        self._source_combo = QComboBox()
        self._source_combo.setMinimumWidth(180)
        toolbar_layout.addWidget(self._source_combo)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.clicked.connect(self._on_refresh_sources)
        toolbar_layout.addWidget(self._refresh_btn)

        self._preview_btn = QPushButton("开始预览")
        self._preview_btn.clicked.connect(self._on_start_preview)
        toolbar_layout.addWidget(self._preview_btn)

        self._experiment_btn = QPushButton("开始实验")
        self._experiment_btn.clicked.connect(self._on_start_experiment)
        toolbar_layout.addWidget(self._experiment_btn)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        toolbar_layout.addWidget(self._stop_btn)

        self._snapshot_btn = QPushButton("截图")
        self._snapshot_btn.clicked.connect(self._on_snapshot)
        toolbar_layout.addWidget(self._snapshot_btn)

        self._roi_btn = QPushButton("设置ROI")
        self._roi_btn.clicked.connect(self._on_set_roi)
        toolbar_layout.addWidget(self._roi_btn)

        toolbar_layout.addSpacing(16)
        toolbar_layout.addWidget(QLabel("冻结阈值:"))
        self._freeze_threshold_spin = QDoubleSpinBox()
        self._freeze_threshold_spin.setRange(0.00001, 0.1)
        self._freeze_threshold_spin.setSingleStep(0.00001)
        self._freeze_threshold_spin.setDecimals(5)
        self._freeze_threshold_spin.setValue(0.0003)
        self._freeze_threshold_spin.setToolTip("运动面积比低于此值且持续指定秒数则判为冻结；越小越易判为冻结")
        self._freeze_threshold_spin.setMinimumWidth(70)
        toolbar_layout.addWidget(self._freeze_threshold_spin)
        toolbar_layout.addWidget(QLabel("持续(s):"))
        self._freeze_duration_spin = QDoubleSpinBox()
        self._freeze_duration_spin.setRange(0.1, 5.0)
        self._freeze_duration_spin.setSingleStep(0.1)
        self._freeze_duration_spin.setDecimals(1)
        self._freeze_duration_spin.setValue(0.5)
        self._freeze_duration_spin.setToolTip("连续满足阈值的最短时长(秒)，超过才判定为一次冻结")
        self._freeze_duration_spin.setMinimumWidth(60)
        toolbar_layout.addWidget(self._freeze_duration_spin)

        toolbar_layout.addSpacing(24)
        toolbar_layout.addWidget(QLabel("实验方案:"))
        self._protocol_combo = QComboBox()
        self._protocol_combo.setMinimumWidth(200)
        self._refresh_protocols_btn = QPushButton("刷新方案")
        self._refresh_protocols_btn.clicked.connect(self._on_refresh_protocols)
        self._fill_protocol_combo()
        toolbar_layout.addWidget(self._protocol_combo)
        toolbar_layout.addWidget(self._refresh_protocols_btn)

        self._save_video_check = QCheckBox("保存视频")
        self._save_video_check.setChecked(False)
        self._save_video_check.setToolTip("开始实验前勾选，会立即弹出选择保存目录；每次开始实验都需重新勾选并选择位置")
        self._save_video_check.stateChanged.connect(self._on_save_video_changed)
        toolbar_layout.addWidget(self._save_video_check)

        self._shock_enable_check = QCheckBox("启用电刺激")
        self._shock_enable_check.setChecked(False)
        toolbar_layout.addWidget(self._shock_enable_check)

        self._video_save_dir: Optional[Path] = None
        self._freeze_log_path: Optional[Path] = None
        self._roi_area_type: Optional[str] = None
        self._roi_area_points: Optional[list[list[int]]] = None
        self._refresh_thread: Optional[QThread] = None
        self._refresh_worker: Optional[CameraRefreshWorker] = None

        self._freeze_threshold_spin.valueChanged.connect(self._on_freeze_params_changed)
        self._freeze_duration_spin.valueChanged.connect(self._on_freeze_params_changed)

        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        # ——— 中央：双路显示（左：原始，右：处理） ———
        video_panel = QWidget()
        video_panel_layout = QHBoxLayout(video_panel)
        video_panel_layout.setContentsMargins(0, 0, 0, 0)
        video_panel_layout.setSpacing(8)
        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.addWidget(QLabel("原始"))
        self._video_label = VideoDisplayLabel(placeholder="原始")
        self._video_label.roi_selected.connect(self._on_roi_selected)
        left_col.addWidget(self._video_label, 1)
        video_panel_layout.addLayout(left_col, 1)
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.addWidget(QLabel("处理（运动检测）"))
        self._processed_label = VideoDisplayLabel(placeholder="处理")
        right_col.addWidget(self._processed_label, 1)
        video_panel_layout.addLayout(right_col, 1)
        layout.addWidget(video_panel, 2)

        # ——— 可移动停靠区：冻结 raster + 事件表 ———
        chart_panel = QWidget()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(4)

        self._freeze_raster = FreezeRasterWidget(self)
        self._freeze_raster.setMinimumHeight(72)
        chart_layout.addWidget(self._freeze_raster)

        self._freeze_table = QTableWidget(0, 4, self)
        self._freeze_table.setHorizontalHeaderLabels(
            ["#", "Start (s)", "End (s)", "Duration (s)"]
        )
        header = self._freeze_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._freeze_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._freeze_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._freeze_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        chart_layout.addWidget(self._freeze_table)

        self._chart_dock = QDockWidget("冻结时间 / 事件表", self)
        self._chart_dock.setObjectName("chart_dock")
        self._chart_dock.setWidget(chart_panel)
        self._chart_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._chart_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._chart_dock)

        # ——— 底部：状态栏 ———
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")
        self._preview_start_time: Optional[float] = None
        self._current_freeze_start_rel: Optional[float] = None
        self._last_freeze = False
        self._last_motion = 0.0
        self._scheduled_shocks_fired: set[int] = set()
        self._experiment_running = False

        self._scheduled_shock_timer = QTimer(self)
        self._scheduled_shock_timer.setInterval(500)
        self._scheduled_shock_timer.timeout.connect(self._on_scheduled_shock_tick)

        self._shock_service.shock_done.connect(self._on_shock_done)
        self._shock_service.shock_error.connect(self._on_shock_error)

        self._source_combo.addItem("点击“刷新”枚举摄像头", -1)
        self._status_bar.showMessage("启动完成，请点击“刷新”枚举摄像头")

    def _fill_protocol_combo(self) -> None:
        """从 protocols/*.yml 扫描并填充实验方案下拉框。"""
        self._protocol_combo.clear()
        for p in get_protocol_list():
            self._protocol_combo.addItem(p.name, p)
            self._protocol_combo.setItemData(
                self._protocol_combo.count() - 1, p.summary(), Qt.ItemDataRole.ToolTipRole
            )
        if self._protocol_combo.count() > 0:
            self._protocol_combo.setCurrentIndex(0)

    def _on_refresh_protocols(self) -> None:
        """重新扫描 protocols 目录并刷新方案列表。"""
        self._fill_protocol_combo()
        self._status_bar.showMessage(f"已加载 {self._protocol_combo.count()} 个实验方案", 3000)

    def _on_freeze_params_changed(self) -> None:
        """工具栏中冻结阈值/持续时长变化时，若正在预览则立即生效。"""
        if self._controller.worker is not None:
            self._controller.update_freeze_params(
                self._freeze_threshold_spin.value(),
                self._freeze_duration_spin.value(),
            )

    def _on_refresh_sources(self) -> None:
        """刷新摄像头列表。"""
        if self._refresh_thread is not None:
            return
        self._refresh_btn.setEnabled(False)
        self._source_combo.clear()
        self._source_combo.addItem("正在枚举 UVC 摄像头…", -1)
        self._status_bar.showMessage("正在后台枚举 UVC 摄像头…")

        self._refresh_thread = QThread(self)
        self._refresh_worker = CameraRefreshWorker(self._source_manager)
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._on_refresh_sources_finished)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_thread.finished.connect(self._on_refresh_sources_cleanup)
        self._refresh_thread.start()

    def _on_refresh_sources_finished(self, cameras_obj: object) -> None:
        cameras = cameras_obj if isinstance(cameras_obj, list) else []
        self._source_combo.clear()
        for idx, name in cameras:
            self._source_combo.addItem(name, idx)
        if self._source_combo.count() == 0:
            self._source_combo.addItem("未检测到 UVC 免驱摄像头", -1)
            self._status_bar.showMessage("未检测到 UVC 免驱摄像头")
        else:
            self._status_bar.showMessage(f"已检测到 {self._source_combo.count()} 个 UVC 摄像头")

    def _on_refresh_sources_cleanup(self) -> None:
        self._refresh_btn.setEnabled(True)
        if self._refresh_worker is not None:
            self._refresh_worker.deleteLater()
            self._refresh_worker = None
        if self._refresh_thread is not None:
            self._refresh_thread.deleteLater()
            self._refresh_thread = None

    def _current_source(self) -> int:
        data = self._source_combo.currentData()
        return int(data) if data is not None else -1

    def _on_save_video_changed(self, state: int) -> None:
        """勾选「保存视频」时立即弹出选择目录；取消则取消勾选。"""
        if state == Qt.CheckState.Checked.value:
            path = QFileDialog.getExistingDirectory(self, "选择视频保存位置", str(Path.home()))
            if not path:
                self._save_video_check.setChecked(False)
                self._video_save_dir = None
                return
            self._video_save_dir = Path(path)
            self._status_bar.showMessage(f"视频将保存到: {self._video_save_dir}", 5000)
        else:
            self._video_save_dir = None

    def _on_set_roi(self) -> None:
        """在左侧原始图上进入 ROI 框选模式。"""
        if self._controller.worker is None:
            QMessageBox.information(self, "设置 ROI", "请先开始预览，再设置 ROI。")
            return
        if self._experiment_running:
            QMessageBox.information(self, "设置 ROI", "实验进行中不可修改 ROI，请先停止实验。")
            return
        frame = self._controller.get_last_image_copy()
        if frame is None:
            QMessageBox.information(self, "设置 ROI", "请先开始预览，获取一帧画面后再设置 ROI。")
            return
        self._video_label.set_roi_edit_mode(True)
        self._status_bar.showMessage("请在左侧原始图中拖拽框选 ROI（松开鼠标完成）", 5000)

    def _on_roi_selected(self, points_obj: object) -> None:
        points = points_obj if isinstance(points_obj, list) else None
        if not points:
            QMessageBox.warning(self, "设置 ROI", "ROI 太小或未选择，请重新框选。")
            return
        self._roi_area_type = "polygon"
        self._roi_area_points = points
        self._video_label.set_roi_points(points)
        self._processed_label.set_roi_points(points)
        self._status_bar.showMessage("ROI 已设置（实验将只分析 ROI 内区域）", 4000)
        # 仅预览阶段允许更新 ROI 到检测器；实验阶段锁定
        if self._controller.worker is not None and not self._experiment_running:
            self._controller.update_freeze_roi(self._roi_area_type, self._roi_area_points)

    def _start_impl(self, enable_freeze: bool, record_path: Optional[Path] = None) -> None:
        """共用：打开摄像头、可选 freeze 检测与录制，并连接信号。"""
        source = self._current_source()
        if source < 0:
            QMessageBox.warning(self, "提示", "请先选择有效的视频源。")
            return
        self._video_label.set_roi_edit_mode(False)
        self._experiment_running = enable_freeze
        self._preview_start_time = time.time()
        self._current_freeze_start_rel = None
        self._scheduled_shocks_fired.clear()
        self._freeze_raster.reset()
        self._freeze_table.setRowCount(0)
        # 如有录像文件，则在同一目录准备一个 freeze 结果 CSV
        if record_path is not None:
            base = record_path.with_suffix("")
            self._freeze_log_path = base.parent / f"{base.name}_freeze.csv"
            try:
                self._freeze_log_path.write_text("index,start_s,end_s,duration_s\n", encoding="utf-8")
            except Exception:
                self._freeze_log_path = None
        else:
            self._freeze_log_path = None
        th = self._freeze_threshold_spin.value()
        dur = self._freeze_duration_spin.value()
        if not self._controller.start_preview(
            source,
            enable_freeze_detection=enable_freeze,
            freeze_threshold=th,
            freeze_duration_sec=dur,
            record_path=record_path,
            roi_area_type=self._roi_area_type if enable_freeze else None,
            roi_area_points=self._roi_area_points if enable_freeze else None,
        ):
            QMessageBox.warning(self, "错误", "无法打开摄像头，请检查设备或权限。")
            self._update_status_idle()
            return
        worker = self._controller.worker
        if worker:
            worker.frame_ready.connect(self._on_frame_ready)
            worker.freeze_result.connect(self._on_freeze_result)
            worker.processed_frame_ready.connect(self._on_processed_frame_ready)
            worker.error_occurred.connect(self._on_capture_error)
            worker.finished_signal.connect(self._on_capture_finished)
        self._preview_btn.setEnabled(False)
        self._experiment_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._save_video_check.setEnabled(False)
        self._roi_btn.setEnabled(not enable_freeze)
        protocol = self._current_protocol()
        if enable_freeze and protocol and (
            protocol.total_duration_sec > 0
            or (self._shock_enable_check.isChecked() and protocol.shocks)
        ):
            self._scheduled_shock_timer.start()
        if record_path:
            self._status_bar.showMessage(f"实验中，视频保存: {record_path}", 5000)
        else:
            self._status_bar.showMessage("预览中…" if not enable_freeze else "实验中…")

    def _on_start_preview(self) -> None:
        """仅打开摄像头展示，不进行 freeze 检测与录制。"""
        self._start_impl(enable_freeze=False, record_path=None)

    def _on_start_experiment(self) -> None:
        """开始实验：freeze 检测、可选录制、电刺激。若勾选保存视频则必须先选好目录。"""
        if not self._roi_area_points:
            QMessageBox.warning(self, "提示", "开始实验前请先点击「设置ROI」，实验仅分析 ROI 内区域。")
            return
        if self._save_video_check.isChecked():
            if not self._video_save_dir:
                QMessageBox.warning(self, "提示", "请先勾选「保存视频」并选择保存位置。")
                return
            name = f"livefreeze_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            record_path = self._video_save_dir / name
        else:
            record_path = None
        self._start_impl(enable_freeze=True, record_path=record_path)
        if self._save_video_check.isChecked():
            self._save_video_check.setChecked(False)
            self._video_save_dir = None

    def _on_stop(self) -> None:
        self._scheduled_shock_timer.stop()
        self._experiment_running = False
        self._disconnect_worker()
        self._controller.stop_preview()
        self._preview_btn.setEnabled(True)
        self._experiment_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._save_video_check.setEnabled(True)
        self._roi_btn.setEnabled(True)
        self._save_video_check.setChecked(False)
        self._video_save_dir = None
        self._video_label.set_frame(QImage())
        self._processed_label.set_frame(QImage())
        self._last_freeze = False
        self._last_motion = 0.0
        self._update_status_idle()


    def _disconnect_worker(self) -> None:
        w = self._controller.worker
        if w:
            try:
                w.frame_ready.disconnect(self._on_frame_ready)
            except Exception:
                pass
            try:
                w.freeze_result.disconnect(self._on_freeze_result)
            except Exception:
                pass
            try:
                w.processed_frame_ready.disconnect(self._on_processed_frame_ready)
            except Exception:
                pass
            try:
                w.error_occurred.disconnect(self._on_capture_error)
            except Exception:
                pass
            try:
                w.finished_signal.disconnect(self._on_capture_finished)
            except Exception:
                pass

    def _current_protocol(self) -> Optional[ExperimentProtocol]:
        data = self._protocol_combo.currentData()
        return data if isinstance(data, ExperimentProtocol) else None

    def _on_scheduled_shock_tick(self) -> None:
        """定时检查：若当前方案有 shocks 且已到点，触发电击。"""
        if self._controller.worker is None or self._preview_start_time is None:
            return
        protocol = self._current_protocol()
        if not protocol or not protocol.shocks:
            return
        elapsed = time.time() - self._preview_start_time
        if protocol.total_duration_sec > 0 and elapsed >= protocol.total_duration_sec:
            self._on_stop()
            self._status_bar.showMessage(
                f"实验已按方案完成（{self._format_elapsed(int(protocol.total_duration_sec))}）",
                5000,
            )
            return
        if not self._shock_enable_check.isChecked() or self._shock_service.busy:
            return
        for i, s in enumerate(protocol.shocks):
            if i in self._scheduled_shocks_fired:
                continue
            if elapsed >= s.time_sec:
                if self._shock_service.trigger_shock(s.current_mA, s.duration):
                    self._scheduled_shocks_fired.add(i)
                    self._freeze_raster.add_shock_interval(elapsed, elapsed + float(s.duration))
                    self._status_bar.showMessage(
                        f"定时电击 @ {s.time_sec / 60:.1f} min | {s.current_mA} mA", 3000
                    )

    def _on_freeze_result(self, is_freeze: bool, motion_level: float) -> None:
        now = time.time()
        if self._preview_start_time is None:
            self._preview_start_time = now
        t_rel = now - self._preview_start_time

        prev_freeze = self._last_freeze
        self._last_freeze = is_freeze
        self._last_motion = motion_level

        # 更新 raster
        self._freeze_raster.append_point(t_rel, is_freeze)

        # 记录冻结区段到表格
        if is_freeze and not prev_freeze:
            self._current_freeze_start_rel = t_rel
        elif not is_freeze and prev_freeze:
            if self._current_freeze_start_rel is not None:
                self._append_freeze_bout(self._current_freeze_start_rel, t_rel)
                self._current_freeze_start_rel = None

        if not self._shock_enable_check.isChecked() or not is_freeze:
            return

    def _on_processed_frame_ready(self, image: QImage) -> None:
        self._processed_label.set_frame(image)

    def _on_frame_ready(self, image: QImage, width: int, height: int, fps: float) -> None:
        self._controller.on_frame_ready(image, width, height, fps)
        self._video_label.set_frame(image)
        self._video_label.setText("")
        w, h, f = self._controller.last_frame_info()
        msg = f"预览中 | {w}×{h} | {f:.1f} FPS | 运动: {self._last_motion:.4f}"
        if self._experiment_running and self._preview_start_time is not None:
            elapsed = max(0, int(time.time() - self._preview_start_time))
            msg += f" | 实验进度: {self._format_elapsed(elapsed)}"
        if self._last_freeze:
            msg += " | Freeze"
        self._status_bar.showMessage(msg)

    def _on_capture_error(self, message: str) -> None:
        QMessageBox.warning(self, "采集错误", message)
        self._on_stop()

    def _on_capture_finished(self) -> None:
        self._disconnect_worker()
        self._experiment_running = False
        self._preview_btn.setEnabled(True)
        self._experiment_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._save_video_check.setEnabled(True)
        self._roi_btn.setEnabled(True)
        self._save_video_check.setChecked(False)
        self._video_save_dir = None
        self._update_status_idle()

    def _on_snapshot(self) -> None:
        path = self._controller.take_snapshot()
        if path is None:
            QMessageBox.warning(self, "截图", "无可用画面或保存失败。")
            return
        self._status_bar.showMessage(f"已保存: {path}", 5000)

    def _on_shock_done(self) -> None:
        self._status_bar.showMessage("电刺激已执行", 3000)

    def _on_shock_error(self, message: str) -> None:
        QMessageBox.warning(self, "电刺激错误", message)
        self._status_bar.showMessage("电刺激失败", 3000)

    def _update_status_idle(self) -> None:
        self._status_bar.showMessage("就绪")

    @staticmethod
    def _format_elapsed(total_sec: int) -> str:
        minutes, seconds = divmod(total_sec, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _append_freeze_bout(self, start_s: float, end_s: float) -> None:
        """在表格中追加一段冻结事件，并可选写入 CSV。"""
        row = self._freeze_table.rowCount()
        self._freeze_table.insertRow(row)
        duration = max(end_s - start_s, 0.0)
        values = [str(row + 1), f"{start_s:.3f}", f"{end_s:.3f}", f"{duration:.3f}"]
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            self._freeze_table.setItem(row, col, item)
        self._freeze_table.scrollToBottom()
        if self._freeze_log_path is not None:
            try:
                with self._freeze_log_path.open("a", encoding="utf-8") as f:
                    f.write(",".join(values) + "\n")
            except Exception:
                # 写日志失败不影响主流程
                self._freeze_log_path = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口前停止采集、定时器并等待电刺激命令线程收尾。"""
        self._scheduled_shock_timer.stop()
        self._experiment_running = False
        self._disconnect_worker()
        self._controller.stop_preview()
        if not self._shock_service.shutdown():
            QMessageBox.warning(
                self,
                "正在关闭",
                "电刺激设备命令尚未结束，请稍后再关闭程序。",
            )
            event.ignore()
            return
        if self._refresh_thread is not None and self._refresh_thread.isRunning():
            self._refresh_thread.quit()
            if not self._refresh_thread.wait(5000):
                QMessageBox.warning(
                    self,
                    "正在关闭",
                    "摄像头枚举尚未结束，请稍后再关闭程序。",
                )
                event.ignore()
                return
        event.accept()
