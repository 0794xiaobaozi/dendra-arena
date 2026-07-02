"""多摄像头 LiveFreeze 主窗口。

设备选择、全局实验控制和单摄像头属性被拆分到不同区域；每个摄像头
拥有独立采集/检测/录像会话，实验协议与电刺激使用一个共享时钟。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QObject
from PySide6.QtGui import QCloseEvent, QImage, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .app_icon import create_app_icon
from .config_service import ConfigService
from .experiment_protocol import ExperimentProtocol, get_protocol_list
from .main_window import VideoDisplayLabel
from .shock_service import ShockService
from .source_manager import SourceManager
from .video_controller import VideoController


class CameraRefreshWorker(QObject):
    finished = Signal(object)

    def __init__(self, source_manager: SourceManager):
        super().__init__()
        self._source_manager = source_manager

    def run(self) -> None:
        self.finished.emit(self._source_manager.enumerate_cameras())


class ClickableVideoLabel(VideoDisplayLabel):
    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._roi_edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CameraTile(QWidget):
    selected = Signal(int)

    def __init__(self, source_id: int, name: str):
        super().__init__()
        self.source_id = source_id
        self.setObjectName("cameraTile")
        self.setProperty("selected", False)
        self.setStyleSheet(
            "#cameraTile { border: 1px solid #454545; border-radius: 6px; background: #252525; }"
            "#cameraTile[selected='true'] { border: 2px solid #42a5f5; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        head = QHBoxLayout()
        self.title = QLabel(name)
        self.title.setStyleSheet("font-weight: 600;")
        self.status = QLabel("未启动")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status.setStyleSheet("color: #9e9e9e;")
        head.addWidget(self.title, 1)
        head.addWidget(self.status)
        layout.addLayout(head)
        self.video = ClickableVideoLabel(placeholder="等待预览")
        self.video.setMinimumSize(280, 190)
        self.video.clicked.connect(lambda: self.selected.emit(self.source_id))
        layout.addWidget(self.video, 1)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)


@dataclass
class CameraSession:
    source_id: int
    name: str
    controller: VideoController
    tile: CameraTile
    threshold: float = 0.0003
    duration_sec: float = 0.5
    roi_type: Optional[str] = None
    roi_points: Optional[list[list[int]]] = None
    active: bool = False
    last_freeze: bool = False
    last_motion: float = 0.0
    freeze_start: Optional[float] = None
    last_processed: Optional[QImage] = None
    log_path: Optional[Path] = None
    bouts: list[tuple[float, float]] = field(default_factory=list)


class MultiCameraWindow(QMainWindow):
    """多路摄像头并行预览、检测与录像窗口。"""

    def __init__(self, config: ConfigService):
        super().__init__()
        self._config = config
        self._source_manager = SourceManager()
        self._shock_service = ShockService(self)
        self._sessions: dict[int, CameraSession] = {}
        self._items: dict[int, QListWidgetItem] = {}
        self._selected_camera: Optional[int] = None
        self._refresh_thread: Optional[QThread] = None
        self._refresh_worker: Optional[CameraRefreshWorker] = None
        self._experiment_running = False
        self._session_start: Optional[float] = None
        self._fired_shocks: set[int] = set()
        self._video_save_dir: Optional[Path] = None

        self.setWindowTitle("LiveFreeze — 多摄像头实验")
        self.setWindowIcon(create_app_icon())
        self.setMinimumSize(1100, 700)
        self.resize(1500, 900)

        self._build_top_bar()
        self._build_camera_grid()
        self._build_device_dock()
        self._build_settings_dock()
        self._build_events_dock()

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("点击左侧“刷新设备”，勾选参与预览的摄像头")

        self._experiment_timer = QTimer(self)
        self._experiment_timer.setInterval(250)
        self._experiment_timer.timeout.connect(self._on_experiment_tick)
        self._shock_service.shock_done.connect(
            lambda: self._status_bar.showMessage("电刺激已执行", 3000)
        )
        self._shock_service.shock_error.connect(self._on_shock_error)

    # ---------- UI ----------
    def _build_top_bar(self) -> None:
        bar = QWidget()
        self._legacy_top_bar = bar
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        self._preview_btn = QPushButton("预览所选摄像头")
        self._preview_btn.clicked.connect(self._start_preview)
        self._experiment_btn = QPushButton("开始实验")
        self._experiment_btn.clicked.connect(self._start_experiment)
        self._experiment_btn.setStyleSheet("font-weight: 600;")
        self._stop_btn = QPushButton("全部停止")
        self._stop_btn.clicked.connect(self._stop_all)
        self._stop_btn.setEnabled(False)
        self._snapshot_btn = QPushButton("截取当前画面")
        self._snapshot_btn.clicked.connect(self._snapshot_selected)
        layout.addWidget(self._preview_btn)
        layout.addWidget(self._experiment_btn)
        layout.addWidget(self._stop_btn)
        layout.addSpacing(12)
        layout.addWidget(self._snapshot_btn)
        layout.addStretch()
        hint = QLabel("左侧选设备 · 中间看画面 · 右侧改当前摄像头属性")
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)
        self.setMenuWidget(bar)

    def _build_camera_grid(self) -> None:
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)
        self._empty_label = QLabel("尚未选择摄像头")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #777; font-size: 18px;")
        self._grid.addWidget(self._empty_label, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._grid_host)
        self._camera_scroll = scroll
        self.setCentralWidget(scroll)

    def _build_device_dock(self) -> None:
        panel = QWidget()
        self._device_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        self._refresh_btn = QPushButton("刷新设备")
        self._refresh_btn.clicked.connect(self._refresh_sources)
        layout.addWidget(self._refresh_btn)
        note = QLabel("勾选需要同时预览或实验的摄像头")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        layout.addWidget(note)
        self._device_list = QListWidget()
        self._device_list.itemChanged.connect(self._on_device_checked)
        self._device_list.currentItemChanged.connect(self._on_device_item_selected)
        layout.addWidget(self._device_list, 1)
        self._device_summary = QLabel("0 台已选择")
        layout.addWidget(self._device_summary)
        dock = QDockWidget("摄像头", self)
        self._device_dock = dock
        dock.setObjectName("deviceDock")
        dock.setWidget(panel)
        dock.setMinimumWidth(230)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        if not getattr(self, "_console_mode", False):
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_settings_dock(self) -> None:
        panel = QWidget()
        self._settings_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        current_group = QGroupBox("当前摄像头")
        current_form = QFormLayout(current_group)
        self._current_camera_label = QLabel("未选择")
        current_form.addRow("设备", self._current_camera_label)
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.00001, 0.1)
        self._threshold_spin.setDecimals(5)
        self._threshold_spin.setSingleStep(0.00001)
        self._threshold_spin.setValue(0.0003)
        self._threshold_spin.valueChanged.connect(self._on_camera_params_changed)
        current_form.addRow("冻结阈值", self._threshold_spin)
        self._duration_spin = QDoubleSpinBox()
        self._duration_spin.setRange(0.1, 5.0)
        self._duration_spin.setDecimals(1)
        self._duration_spin.setSingleStep(0.1)
        self._duration_spin.setValue(0.5)
        self._duration_spin.valueChanged.connect(self._on_camera_params_changed)
        current_form.addRow("持续时间 (s)", self._duration_spin)
        self._roi_btn = QPushButton("在当前画面框选 ROI")
        self._roi_btn.clicked.connect(self._set_roi)
        current_form.addRow(self._roi_btn)
        self._roi_status = QLabel("未设置")
        current_form.addRow("ROI", self._roi_status)
        layout.addWidget(current_group)

        processed_group = QGroupBox("当前摄像头 · 运动检测")
        processed_layout = QVBoxLayout(processed_group)
        self._processed_view = VideoDisplayLabel(placeholder="实验开始后显示")
        self._processed_view.setMinimumSize(260, 170)
        processed_layout.addWidget(self._processed_view)
        layout.addWidget(processed_group)

        experiment_group = QGroupBox("全局实验")
        experiment_form = QFormLayout(experiment_group)
        self._protocol_combo = QComboBox()
        self._fill_protocols()
        experiment_form.addRow("实验方案", self._protocol_combo)
        self._refresh_protocol_btn = QPushButton("刷新方案")
        self._refresh_protocol_btn.clicked.connect(self._fill_protocols)
        experiment_form.addRow(self._refresh_protocol_btn)
        self._save_video_check = QCheckBox("分别保存每台摄像头录像")
        self._save_video_check.stateChanged.connect(self._choose_record_dir)
        experiment_form.addRow(self._save_video_check)
        self._record_dir_label = QLabel("未选择")
        self._record_dir_label.setWordWrap(True)
        experiment_form.addRow("保存位置", self._record_dir_label)
        self._shock_check = QCheckBox("按方案启用电刺激")
        experiment_form.addRow(self._shock_check)
        layout.addWidget(experiment_group)
        layout.addStretch()

        dock = QDockWidget("属性与实验", self)
        self._settings_dock = dock
        dock.setObjectName("settingsDock")
        dock.setWidget(panel)
        dock.setMinimumWidth(320)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        if not getattr(self, "_console_mode", False):
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_events_dock(self) -> None:
        self._event_table = QTableWidget(0, 5)
        self._event_table.setHorizontalHeaderLabels(
            ["摄像头", "#", "开始 (s)", "结束 (s)", "持续 (s)"]
        )
        self._event_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._event_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        dock = QDockWidget("Freeze 事件（全部摄像头）", self)
        self._events_dock = dock
        dock.setObjectName("eventsDock")
        dock.setWidget(self._event_table)
        dock.setMinimumHeight(170)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        if not getattr(self, "_console_mode", False):
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    # ---------- device selection / layout ----------
    def _refresh_sources(self) -> None:
        if self._refresh_thread is not None or self._any_active():
            return
        self._refresh_btn.setEnabled(False)
        self._device_list.clear()
        self._status_bar.showMessage("正在枚举 UVC 摄像头…")
        self._refresh_thread = QThread(self)
        self._refresh_worker = CameraRefreshWorker(self._source_manager)
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._on_sources_found)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_thread.finished.connect(self._cleanup_refresh)
        self._refresh_thread.start()

    def _on_sources_found(self, cameras_obj: object) -> None:
        cameras = cameras_obj if isinstance(cameras_obj, list) else []
        self._clear_sessions()
        self._device_list.blockSignals(True)
        for source_id, name in cameras:
            tile = CameraTile(source_id, name)
            tile.selected.connect(self._select_camera)
            tile.video.roi_selected.connect(
                lambda points, sid=source_id: self._on_roi_selected(sid, points)
            )
            session = CameraSession(
                source_id=source_id,
                name=name,
                controller=VideoController(self._config),
                tile=tile,
            )
            self._sessions[source_id] = session
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, source_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._device_list.addItem(item)
            self._items[source_id] = item
        self._device_list.blockSignals(False)
        self._reflow_grid()
        if cameras:
            self._status_bar.showMessage(f"检测到 {len(cameras)} 台摄像头，请勾选需要使用的设备")
        else:
            self._status_bar.showMessage("未检测到 UVC 摄像头")

    def _cleanup_refresh(self) -> None:
        self._refresh_btn.setEnabled(True)
        if self._refresh_worker is not None:
            self._refresh_worker.deleteLater()
        if self._refresh_thread is not None:
            self._refresh_thread.deleteLater()
        self._refresh_worker = None
        self._refresh_thread = None

    def _on_device_checked(self, _item: QListWidgetItem) -> None:
        self._reflow_grid()

    def _checked_sessions(self) -> list[CameraSession]:
        return [
            self._sessions[sid]
            for sid, item in self._items.items()
            if item.checkState() == Qt.CheckState.Checked
        ]

    def _reflow_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        selected = self._checked_sessions()
        self._device_summary.setText(f"{len(selected)} 台已选择")
        if not selected:
            self._grid.addWidget(self._empty_label, 0, 0)
            self._empty_label.show()
            self._select_camera(None)
            return
        self._empty_label.hide()
        count = len(selected)
        columns = 1 if count == 1 else 2 if count <= 4 else 3
        for index, session in enumerate(selected):
            self._grid.addWidget(session.tile, index // columns, index % columns)
        if self._selected_camera not in {s.source_id for s in selected}:
            self._select_camera(selected[0].source_id)

    def _on_device_item_selected(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if current is not None:
            self._select_camera(int(current.data(Qt.ItemDataRole.UserRole)))

    def _select_camera(self, source_id: Optional[int]) -> None:
        self._selected_camera = source_id
        for sid, session in self._sessions.items():
            session.tile.set_selected(sid == source_id)
        session = self._sessions.get(source_id) if source_id is not None else None
        self._threshold_spin.blockSignals(True)
        self._duration_spin.blockSignals(True)
        if session is None:
            self._current_camera_label.setText("未选择")
            self._roi_status.setText("未设置")
            self._processed_view.set_frame(QImage())
        else:
            self._current_camera_label.setText(session.name)
            self._threshold_spin.setValue(session.threshold)
            self._duration_spin.setValue(session.duration_sec)
            self._roi_status.setText("已设置" if session.roi_points else "未设置")
            self._processed_view.set_frame(session.last_processed or QImage())
        self._threshold_spin.blockSignals(False)
        self._duration_spin.blockSignals(False)

    # ---------- preview / experiment ----------
    def _start_preview(self) -> None:
        self._start_sessions(experiment=False)

    def _start_experiment(self) -> None:
        selected = self._checked_sessions()
        missing = [s.name for s in selected if not s.roi_points]
        if missing:
            QMessageBox.warning(
                self,
                "ROI 未设置",
                "请先预览并为以下摄像头设置 ROI：\n" + "\n".join(missing),
            )
            return
        if self._save_video_check.isChecked() and self._video_save_dir is None:
            QMessageBox.warning(self, "保存位置", "请先选择录像保存目录。")
            return
        self._start_sessions(experiment=True)

    def _start_sessions(self, experiment: bool) -> None:
        selected = self._checked_sessions()
        if not selected:
            QMessageBox.information(self, "摄像头", "请先在左侧勾选至少一台摄像头。")
            return
        self._stop_all(show_status=False)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        failures: list[str] = []
        self._event_table.setRowCount(0)
        for session in selected:
            session.last_freeze = False
            session.freeze_start = None
            session.bouts.clear()
            session.log_path = None
            record_path = None
            if experiment and self._video_save_dir is not None:
                base = self._video_save_dir / f"livefreeze_{stamp}_cam{session.source_id}"
                record_path = base.with_suffix(".mp4")
                session.record_path = record_path
                session.log_path = base.parent / f"{base.name}_freeze.csv"
                session.log_path.write_text(
                    "index,camera,start_s,end_s,duration_s\n", encoding="utf-8"
                )
            ok = session.controller.start_preview(
                session.source_id,
                enable_freeze_detection=experiment,
                freeze_threshold=session.threshold,
                freeze_duration_sec=session.duration_sec,
                record_path=record_path,
                roi_area_type=session.roi_type if experiment else None,
                roi_area_points=session.roi_points if experiment else None,
            )
            if not ok:
                failures.append(session.name)
                session.tile.status.setText("打开失败")
                continue
            session.active = True
            session.tile.status.setText("实验中" if experiment else "预览中")
            worker = session.controller.worker
            if worker is not None:
                sid = session.source_id
                worker.frame_ready.connect(
                    lambda image, width, height, fps, i=sid: self._on_frame(
                        i, image, width, height, fps
                    )
                )
                worker.freeze_result.connect(
                    lambda frozen, motion, i=sid: self._on_freeze(i, frozen, motion)
                )
                worker.processed_frame_ready.connect(
                    lambda image, i=sid: self._on_processed(i, image)
                )
                worker.error_occurred.connect(
                    lambda message, i=sid: self._on_camera_error(i, message)
                )
                worker.finished_signal.connect(lambda i=sid: self._on_camera_finished(i))
        active_count = sum(1 for s in selected if s.active)
        if active_count == 0:
            QMessageBox.warning(self, "摄像头", "所选摄像头均无法打开。")
            return
        self._experiment_running = experiment
        self._session_start = time.monotonic()
        self._fired_shocks.clear()
        if experiment:
            self._experiment_timer.start()
        self._set_running_ui(True)
        if failures:
            QMessageBox.warning(self, "部分设备失败", "以下摄像头无法打开：\n" + "\n".join(failures))
        self._status_bar.showMessage(
            f"{'实验' if experiment else '预览'}已启动：{active_count} 台摄像头"
        )

    def _stop_all(self, show_status: bool = True) -> None:
        self._experiment_timer.stop()
        now = self._elapsed()
        for session in self._sessions.values():
            if session.last_freeze and session.freeze_start is not None:
                self._append_bout(session, session.freeze_start, now)
            session.last_freeze = False
            session.freeze_start = None
            session.controller.stop_preview()
            session.active = False
            session.tile.status.setText("已停止")
            session.tile.video.set_frame(QImage())
        self._experiment_running = False
        self._session_start = None
        self._set_running_ui(False)
        if show_status:
            self._status_bar.showMessage("所有摄像头已停止")

    def _set_running_ui(self, running: bool) -> None:
        self._preview_btn.setEnabled(not running)
        self._experiment_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._refresh_btn.setEnabled(not running)
        self._device_list.setEnabled(not running)
        self._protocol_combo.setEnabled(not running)
        self._save_video_check.setEnabled(not running)
        self._shock_check.setEnabled(not running)

    # ---------- frame and freeze events ----------
    def _on_frame(self, source_id: int, image: QImage, width: int, height: int, fps: float) -> None:
        session = self._sessions.get(source_id)
        if session is None:
            return
        session.controller.on_frame_ready(image, width, height, fps)
        session.tile.video.set_frame(image)
        state = "Freeze" if session.last_freeze else "运行"
        session.tile.status.setText(f"{state} · {fps:.1f} FPS · {session.last_motion:.4f}")

    def _on_processed(self, source_id: int, image: QImage) -> None:
        session = self._sessions.get(source_id)
        if session is None:
            return
        session.last_processed = image.copy()
        if self._selected_camera == source_id:
            self._processed_view.set_frame(image)

    def _on_freeze(self, source_id: int, frozen: bool, motion: float) -> None:
        session = self._sessions.get(source_id)
        if session is None or not self._experiment_running:
            return
        elapsed = self._elapsed()
        previous = session.last_freeze
        session.last_freeze = frozen
        session.last_motion = motion
        if frozen and not previous:
            session.freeze_start = elapsed
        elif previous and not frozen and session.freeze_start is not None:
            self._append_bout(session, session.freeze_start, elapsed)
            session.freeze_start = None

    def _append_bout(self, session: CameraSession, start: float, end: float) -> None:
        end = max(end, start)
        session.bouts.append((start, end))
        values = [
            session.name,
            str(len(session.bouts)),
            f"{start:.3f}",
            f"{end:.3f}",
            f"{end - start:.3f}",
        ]
        row = self._event_table.rowCount()
        self._event_table.insertRow(row)
        for column, value in enumerate(values):
            self._event_table.setItem(row, column, QTableWidgetItem(value))
        self._event_table.scrollToBottom()
        if session.log_path is not None:
            try:
                with session.log_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        f"{len(session.bouts)},{session.source_id},{start:.3f},{end:.3f},{end-start:.3f}\n"
                    )
            except OSError as exc:
                session.log_path = None
                self._status_bar.showMessage(f"{session.name} Freeze 日志写入失败：{exc}", 5000)

    # ---------- settings ----------
    def _on_camera_params_changed(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        session.threshold = self._threshold_spin.value()
        session.duration_sec = self._duration_spin.value()
        session.controller.update_freeze_params(session.threshold, session.duration_sec)

    def _set_roi(self) -> None:
        session = self._selected_session()
        if session is None:
            QMessageBox.information(self, "ROI", "请先选择一台摄像头。")
            return
        if self._experiment_running:
            QMessageBox.information(self, "ROI", "实验进行中不能修改 ROI。")
            return
        if session.controller.get_last_image_copy() is None:
            QMessageBox.information(self, "ROI", "请先启动预览并等待画面出现。")
            return
        session.tile.video.set_roi_edit_mode(True)
        self._status_bar.showMessage(f"请在 {session.name} 画面中拖拽框选 ROI", 5000)

    def _on_roi_selected(self, source_id: int, points_obj: object) -> None:
        session = self._sessions.get(source_id)
        points = points_obj if isinstance(points_obj, list) else None
        if session is None or not points:
            return
        session.roi_type = "polygon"
        session.roi_points = points
        session.tile.video.set_roi_points(points)
        if self._selected_camera == source_id:
            self._roi_status.setText("已设置")

    def _choose_record_dir(self, state: int) -> None:
        if state != Qt.CheckState.Checked.value:
            self._video_save_dir = None
            self._record_dir_label.setText("未选择")
            return
        path = QFileDialog.getExistingDirectory(self, "选择多摄像头录像保存目录", str(Path.home()))
        if not path:
            self._save_video_check.setChecked(False)
            return
        self._video_save_dir = Path(path)
        self._record_dir_label.setText(path)

    def _fill_protocols(self) -> None:
        current_id = None
        old = self._protocol_combo.currentData() if hasattr(self, "_protocol_combo") else None
        if isinstance(old, ExperimentProtocol):
            current_id = old.id
        self._protocol_combo.clear()
        for protocol in get_protocol_list():
            self._protocol_combo.addItem(protocol.name, protocol)
            if protocol.id == current_id:
                self._protocol_combo.setCurrentIndex(self._protocol_combo.count() - 1)

    # ---------- shared experiment clock / shock ----------
    def _on_experiment_tick(self) -> None:
        if not self._experiment_running:
            return
        protocol = self._current_protocol()
        if protocol is None:
            return
        elapsed = self._elapsed()
        if protocol.total_duration_sec > 0 and elapsed >= protocol.total_duration_sec:
            self._stop_all(show_status=False)
            self._status_bar.showMessage(f"实验已按方案完成：{protocol.name}", 5000)
            return
        if not self._shock_check.isChecked() or self._shock_service.busy:
            return
        for index, shock in enumerate(protocol.shocks):
            if index not in self._fired_shocks and elapsed >= shock.time_sec:
                if self._shock_service.trigger_shock(shock.current_mA, shock.duration):
                    self._fired_shocks.add(index)
                    self._status_bar.showMessage(
                        f"全局电刺激：{shock.current_mA} mA @ {elapsed:.1f}s", 3000
                    )
                break

    # ---------- misc ----------
    def _snapshot_selected(self) -> None:
        session = self._selected_session()
        path = session.controller.take_snapshot() if session is not None else None
        if path is None:
            QMessageBox.information(self, "截图", "当前摄像头没有可保存的画面。")
        else:
            self._status_bar.showMessage(f"截图已保存：{path}", 5000)

    def _on_camera_error(self, source_id: int, message: str) -> None:
        session = self._sessions.get(source_id)
        if session is not None:
            session.tile.status.setText("错误")
            self._status_bar.showMessage(f"{session.name}：{message}", 5000)

    def _on_camera_finished(self, source_id: int) -> None:
        session = self._sessions.get(source_id)
        if session is not None:
            session.active = False
            session.tile.status.setText("已停止")
        if not self._any_active():
            self._experiment_timer.stop()
            self._experiment_running = False
            self._set_running_ui(False)

    def _on_shock_error(self, message: str) -> None:
        QMessageBox.warning(self, "电刺激错误", message)

    def _selected_session(self) -> Optional[CameraSession]:
        return self._sessions.get(self._selected_camera) if self._selected_camera is not None else None

    def _current_protocol(self) -> Optional[ExperimentProtocol]:
        value = self._protocol_combo.currentData()
        return value if isinstance(value, ExperimentProtocol) else None

    def _elapsed(self) -> float:
        return max(0.0, time.monotonic() - self._session_start) if self._session_start else 0.0

    def _any_active(self) -> bool:
        return any(session.active for session in self._sessions.values())

    def _clear_sessions(self) -> None:
        for session in self._sessions.values():
            session.controller.stop_preview()
            session.tile.deleteLater()
        self._sessions.clear()
        self._items.clear()
        self._selected_camera = None

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_all(show_status=False)
        if not self._shock_service.shutdown():
            QMessageBox.warning(self, "正在关闭", "电刺激命令尚未结束，请稍后再关闭。")
            event.ignore()
            return
        if self._refresh_thread is not None and self._refresh_thread.isRunning():
            self._refresh_thread.quit()
            if not self._refresh_thread.wait(5000):
                event.ignore()
                return
        event.accept()


# 保持 main.py 与外部调用的类名兼容。
MainWindow = MultiCameraWindow
