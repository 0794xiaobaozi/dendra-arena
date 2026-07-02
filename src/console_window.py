"""LiveFreeze 实验控制台：Setup / Run / Review 三段式工作流。"""
from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import usb.util
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config_service import ConfigService
from .experiment_protocol import ExperimentProtocol
from .i18n import text
from .multi_camera_window import CameraSession, MultiCameraWindow


APP_VERSION = "0.2.0"


class AppState(Enum):
    IDLE = "Idle"
    ENUMERATING = "Enumerating"
    PREVIEWING = "Preview"
    READY_TO_RUN = "Ready"
    RUNNING = "Running"
    STOPPING = "Stopping"
    REVIEW = "Review"
    ERROR = "Error"


STYLE = """
QMainWindow, QWidget { background: #0F1115; color: #EAECEF; font-size: 13px; }
QWidget#topBar { background: #171A21; border-bottom: 1px solid #2A303A; }
QLabel#brand { font-size: 20px; font-weight: 700; color: #FFFFFF; }
QLabel#muted { color: #9AA4B2; }
QLabel#stateBadge { background: #253247; color: #8DB5FF; border-radius: 11px; padding: 4px 10px; font-weight: 600; }
QLabel#clock { font-family: Consolas; font-size: 20px; font-weight: 700; }
QPushButton { background: #252B35; border: 1px solid #343C49; border-radius: 6px; padding: 7px 14px; min-height: 20px; }
QPushButton:hover { background: #303846; border-color: #4F8CFF; }
QPushButton:disabled { color: #68717F; background: #1B1F26; border-color: #252B33; }
QPushButton#primary { background: #3F7EE8; border-color: #4F8CFF; color: white; font-weight: 700; }
QPushButton#danger { background: #432326; border-color: #A73C43; color: #FF8B8B; font-weight: 700; }
QPushButton#arm { background: #49371B; border-color: #9A722C; color: #F5C66A; font-weight: 700; }
QPushButton#armed { background: #183A2A; border-color: #2C9A61; color: #67E3A0; font-weight: 700; }
QPushButton#nav { border: 0; background: transparent; color: #9AA4B2; padding: 10px 16px; }
QPushButton#nav:checked { color: #FFFFFF; background: #242A34; border-bottom: 2px solid #4F8CFF; }
QGroupBox { background: #171A21; border: 1px solid #2A303A; border-radius: 8px; margin-top: 12px; padding: 14px 10px 10px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #C8D0DA; }
QListWidget, QTableWidget, QComboBox, QDoubleSpinBox, QLineEdit { background: #171A21; border: 1px solid #2A303A; border-radius: 5px; padding: 4px; selection-background-color: #294B78; }
QHeaderView::section { background: #1D222B; color: #AEB7C4; padding: 8px; border: 0; border-right: 1px solid #2A303A; }
QScrollArea { border: 0; background: #0F1115; }
QSplitter::handle { background: #20252D; width: 2px; }
QStatusBar { background: #171A21; color: #9AA4B2; border-top: 1px solid #2A303A; }
#cameraTile { border: 1px solid #2A303A; border-radius: 8px; background: #171A21; }
#cameraTile[selected='true'] { border: 2px solid #4F8CFF; }
"""


class ExperimentConsoleWindow(MultiCameraWindow):
    """在多摄像头业务层之上提供稳定、分阶段的实验控制台。"""

    def __init__(self, config: ConfigService):
        self._console_mode = True
        super().__init__(config)
        self.setWindowTitle("LiveFreeze — Experiment Console")
        self.setStyleSheet(STYLE)
        self._app_state = AppState.IDLE
        self._language = self._config.language()
        self._stim_connected = False
        self._stim_armed = False
        self._output_root: Optional[Path] = None
        self._active_session_dir: Optional[Path] = None
        self._manifest: Optional[dict] = None
        self._frame_buffers: dict[int, list[str]] = {}
        self._session_duration = 0.0

        self._detach_legacy_containers()
        self._prepare_existing_controls()
        self._build_console_top_bar()
        self._build_preflight_panel()
        self._build_run_sidebars()
        self._build_review_page()
        self._build_workspaces()
        self._wire_console_events()
        self._apply_state(AppState.IDLE)
        self._on_protocol_context_changed()
        self._apply_language(self._language)

    # ---------- layout ----------
    def _detach_legacy_containers(self) -> None:
        self.setMenuWidget(None)
        for dock, panel in (
            (self._device_dock, self._device_panel),
            (self._settings_dock, self._settings_panel),
            (self._events_dock, self._event_table),
        ):
            panel.setParent(None)
            dock.setWidget(QWidget())
            dock.hide()
            dock.deleteLater()
        self._camera_scroll.setParent(None)

    def _prepare_existing_controls(self) -> None:
        self._preview_btn.setText("连接并预览")
        self._preview_btn.setObjectName("primary")
        self._experiment_btn.setText("开始实验")
        self._experiment_btn.setObjectName("primary")
        self._stop_btn.setText("结束实验")
        self._stop_btn.setObjectName("danger")
        self._snapshot_btn.setText("截取当前摄像头")
        self._save_video_check.hide()
        self._shock_check.hide()

        self._select_output_btn = QPushButton("选择实验保存目录")
        self._select_output_btn.clicked.connect(self._select_output_root)
        self._arm_btn = QPushButton("检测并武装刺激器")
        self._arm_btn.setObjectName("arm")
        self._arm_btn.clicked.connect(self._toggle_stimulator_arm)
        self._settings_panel.layout().insertWidget(0, self._snapshot_btn)
        self._settings_panel.layout().addWidget(self._select_output_btn)
        self._settings_panel.layout().addWidget(self._arm_btn)

    def _build_console_top_bar(self) -> None:
        bar = QWidget()
        bar.setObjectName("topBar")
        root = QVBoxLayout(bar)
        root.setContentsMargins(16, 8, 16, 8)
        root.setSpacing(6)
        first = QHBoxLayout()
        brand = QLabel("LiveFreeze")
        brand.setObjectName("brand")
        brand.setMinimumWidth(125)
        first.addWidget(brand)
        first.addSpacing(20)
        self._nav_buttons: list[QPushButton] = []
        for index, text in enumerate(("Setup", "Run", "Review")):
            button = QPushButton(text)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, i=index: self._show_workspace(i))
            first.addWidget(button)
            self._nav_buttons.append(button)
        first.addStretch()
        self._header_protocol = QLabel("Protocol: —")
        self._header_protocol.setMaximumWidth(300)
        self._header_protocol.setObjectName("muted")
        self._header_save = QLabel("Save: —")
        self._header_save.setMaximumWidth(240)
        self._header_save.setObjectName("muted")
        self._state_badge = QLabel("Idle")
        self._state_badge.setObjectName("stateBadge")
        self._clock_label = QLabel("00:00 / --:--")
        self._clock_label.setObjectName("clock")
        first.addWidget(self._header_protocol)
        first.addSpacing(14)
        first.addWidget(self._header_save)
        first.addSpacing(14)
        first.addWidget(self._state_badge)
        first.addWidget(self._clock_label)
        self._language_combo = QComboBox()
        self._language_combo.addItem("English", "en")
        self._language_combo.addItem("中文", "zh")
        self._language_combo.setCurrentIndex(0 if self._language == "en" else 1)
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        first.addWidget(self._language_combo)
        root.addLayout(first)

        actions = QHBoxLayout()
        self._stim_header = QLabel("Stimulator: DISARMED")
        self._stim_header.setStyleSheet("color: #F5B94C; font-weight: 700;")
        actions.addWidget(self._stim_header)
        actions.addStretch()
        actions.addWidget(self._preview_btn)
        actions.addWidget(self._experiment_btn)
        actions.addWidget(self._stop_btn)
        root.addLayout(actions)
        self._console_top_bar = bar

    def _build_preflight_panel(self) -> None:
        group = QGroupBox("Preflight Checklist")
        self._preflight_group = group
        layout = QVBoxLayout(group)
        self._preflight_labels: dict[str, QLabel] = {}
        for key in ("cameras", "roi", "save", "protocol", "stim"):
            label = QLabel()
            label.setWordWrap(True)
            layout.addWidget(label)
            self._preflight_labels[key] = label
        self._start_reason = QLabel()
        self._start_reason.setWordWrap(True)
        self._start_reason.setStyleSheet("color: #F5B94C;")
        layout.addWidget(self._start_reason)
        self._device_panel.layout().insertWidget(2, group)

        rename_hint = QLabel("双击设备名称可改为 Box A、Box B 等实验标签")
        self._rename_hint = rename_hint
        rename_hint.setObjectName("muted")
        rename_hint.setWordWrap(True)
        self._device_panel.layout().insertWidget(3, rename_hint)

    def _build_run_sidebars(self) -> None:
        self._run_left = QWidget()
        left = QVBoxLayout(self._run_left)
        left.setContentsMargins(12, 12, 12, 12)
        status_group = QGroupBox("Experiment Status")
        self._run_status_group = status_group
        status_layout = QVBoxLayout(status_group)
        self._run_clock = QLabel("00:00.000")
        self._run_clock.setStyleSheet("font: 700 28px Consolas; color: #FFFFFF;")
        self._run_remaining = QLabel("Remaining: —")
        self._run_recording = QLabel("● Recording: OFF")
        self._run_stim = QLabel("Stimulator: DISARMED")
        self._next_shock = QLabel("Next shock: —")
        for widget in (
            self._run_clock,
            self._run_remaining,
            self._run_recording,
            self._run_stim,
            self._next_shock,
        ):
            status_layout.addWidget(widget)
        left.addWidget(status_group)
        self._timeline = QLabel("Timeline: —")
        self._timeline.setWordWrap(True)
        self._timeline.setStyleSheet("background:#171A21; border:1px solid #2A303A; padding:12px;")
        left.addWidget(self._timeline)
        left.addStretch()

        self._run_right = QWidget()
        right = QVBoxLayout(self._run_right)
        right.setContentsMargins(12, 12, 12, 12)
        title = QLabel("Recent Events")
        self._recent_title = title
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        right.addWidget(title)
        self._recent_events = QListWidget()
        self._recent_events.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        right.addWidget(self._recent_events, 1)
        self._run_camera_summary = QLabel("No active cameras")
        self._run_camera_summary.setWordWrap(True)
        right.addWidget(self._run_camera_summary)

    def _build_review_page(self) -> None:
        self._review_page = QWidget()
        layout = QVBoxLayout(self._review_page)
        layout.setContentsMargins(16, 16, 16, 16)
        head = QHBoxLayout()
        title = QLabel("Session Review")
        self._review_title = title
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        self._review_path = QLabel("No completed session")
        self._review_path.setObjectName("muted")
        self._open_folder_btn = QPushButton("打开保存目录")
        self._open_folder_btn.clicked.connect(self._open_session_folder)
        self._export_summary_btn = QPushButton("导出 Summary CSV")
        self._export_summary_btn.clicked.connect(self._export_summary_csv)
        head.addWidget(title)
        head.addWidget(self._review_path, 1)
        head.addWidget(self._open_folder_btn)
        head.addWidget(self._export_summary_btn)
        layout.addLayout(head)
        self._summary_table = QTableWidget(0, 5)
        self._summary_table.setHorizontalHeaderLabels(
            ["Camera", "Freeze bouts", "Freeze total (s)", "Freeze %", "Status"]
        )
        self._summary_table.horizontalHeader().setStretchLastSection(True)
        self._summary_table.setMaximumHeight(190)
        layout.addWidget(self._summary_table)
        events_title = QLabel("Freeze Event Details")
        self._events_title = events_title
        events_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(events_title)
        layout.addWidget(self._event_table, 1)

    def _build_workspaces(self) -> None:
        self._workspace_stack = QStackedWidget()

        self._setup_page = QWidget()
        setup = QHBoxLayout(self._setup_page)
        setup.setContentsMargins(0, 0, 0, 0)
        self._setup_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._setup_splitter.addWidget(self._device_panel)
        self._setup_camera_holder = QWidget()
        self._setup_camera_layout = QVBoxLayout(self._setup_camera_holder)
        self._setup_camera_layout.setContentsMargins(0, 0, 0, 0)
        self._setup_splitter.addWidget(self._setup_camera_holder)
        self._setup_splitter.addWidget(self._settings_panel)
        self._setup_splitter.setSizes([280, 900, 340])
        setup.addWidget(self._setup_splitter)

        self._run_page = QWidget()
        run = QHBoxLayout(self._run_page)
        run.setContentsMargins(0, 0, 0, 0)
        self._run_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._run_splitter.addWidget(self._run_left)
        self._run_camera_holder = QWidget()
        self._run_camera_layout = QVBoxLayout(self._run_camera_holder)
        self._run_camera_layout.setContentsMargins(0, 0, 0, 0)
        self._run_splitter.addWidget(self._run_camera_holder)
        self._run_splitter.addWidget(self._run_right)
        self._run_splitter.setSizes([250, 1000, 300])
        run.addWidget(self._run_splitter)

        self._workspace_stack.addWidget(self._setup_page)
        self._workspace_stack.addWidget(self._run_page)
        self._workspace_stack.addWidget(self._review_page)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._console_top_bar)
        root.addWidget(self._workspace_stack, 1)
        self.setCentralWidget(central)
        self._show_workspace(0)

    def _wire_console_events(self) -> None:
        self._protocol_combo.currentIndexChanged.connect(self._on_protocol_context_changed)
        self._shock_service.shock_done.connect(self._on_console_shock_done)

    def _tr(self, key: str, **values):
        return text(self._language, key, **values)

    def _on_language_changed(self) -> None:
        language = self._language_combo.currentData()
        if language in ("en", "zh"):
            self._apply_language(language)

    def _apply_language(self, language: str) -> None:
        self._language = language
        self._config.set_language(language)
        self.setWindowTitle(self._tr("window_title"))
        self.setStyleSheet(STYLE)
        self._nav_buttons[0].setText(self._tr("setup"))
        self._nav_buttons[1].setText(self._tr("run"))
        self._nav_buttons[2].setText(self._tr("review"))
        self._preview_btn.setText(self._tr("connect_preview"))
        self._experiment_btn.setText(self._tr("start_experiment"))
        self._stop_btn.setText(self._tr("stop_experiment"))
        self._snapshot_btn.setText(self._tr("snapshot"))
        self._select_output_btn.setText(self._tr("select_output"))
        self._preflight_group.setTitle(self._tr("preflight"))
        self._rename_hint.setText(self._tr("rename_hint"))
        self._run_status_group.setTitle(self._tr("experiment_status"))
        self._recent_title.setText(self._tr("recent_events"))
        self._review_title.setText(self._tr("session_review"))
        if self._manifest is None:
            self._review_path.setText(self._tr("no_session"))
        self._open_folder_btn.setText(self._tr("open_folder"))
        self._export_summary_btn.setText(self._tr("export_summary"))
        self._events_title.setText(self._tr("freeze_details"))
        self._summary_table.setHorizontalHeaderLabels(self._tr("summary_headers"))
        self._event_table.setHorizontalHeaderLabels(self._tr("event_headers"))
        self._refresh_btn.setText(self._tr("refresh_devices"))
        self._roi_btn.setText(self._tr("set_roi"))
        self._refresh_protocol_btn.setText(self._tr("refresh_protocol"))
        self._empty_label.setText(self._tr("camera_list_empty"))
        self._run_camera_summary.setText(self._tr("no_active"))
        self._run_remaining.setText(f"{self._tr('remaining')}: —")
        self._run_recording.setText(self._tr("recording_off"))
        self._run_stim.setText(self._tr("stim_armed") if self._stim_armed else self._tr("stim_disarmed"))
        self._next_shock.setText(f"{self._tr('next_shock')}: —")
        self._device_summary.setText(self._tr("selected_count", count=len(self._checked_sessions())))

        static_map = {
            "当前摄像头": "current_camera", "Selected Camera": "current_camera",
            "设备": "device", "Device": "device",
            "冻结阈值": "threshold", "Freeze threshold": "threshold",
            "持续时间 (s)": "duration", "Minimum duration (s)": "duration",
            "当前摄像头 · 运动检测": "processed", "Selected Camera · Motion Detection": "processed",
            "全局实验": "global_experiment", "Global Experiment": "global_experiment",
            "实验方案": "experiment_protocol", "Protocol": "experiment_protocol",
            "保存位置": "save_location", "Save location": "save_location",
            "勾选需要同时预览或实验的摄像头": "device_note",
            "Select cameras for simultaneous preview or experiment.": "device_note",
        }
        for group in self.findChildren(QGroupBox):
            key = group.property("i18n_key") or static_map.get(group.title())
            if key:
                group.setProperty("i18n_key", key)
                group.setTitle(self._tr(str(key)))
        for label in self.findChildren(QLabel):
            key = label.property("i18n_key") or static_map.get(label.text())
            if key:
                label.setProperty("i18n_key", key)
                label.setText(self._tr(str(key)))
        for session in self._sessions.values():
            session.tile.video._placeholder = self._tr("waiting_preview")
            if session.tile.video.pixmap() is None:
                session.tile.video.setText(self._tr("waiting_preview"))
            if not session.active:
                session.tile.status.setText(self._tr("not_started"))
        self._processed_view._placeholder = self._tr("waiting_preview")
        if self._processed_view.pixmap() is None:
            self._processed_view.setText(self._tr("waiting_preview"))
        selected_session = self._selected_session()
        self._roi_status.setText(
            self._tr("roi_set") if selected_session and selected_session.roi_points else self._tr("roi_unset")
        )
        if self._output_root is None:
            self._record_dir_label.setText("—")
        self._status_bar.showMessage(self._tr("status_select"))
        self._update_stim_ui()
        self._on_protocol_context_changed(reset_arm=False)
        self._header_save.setText(
            f"{self._tr('save')}: {self._output_root}" if self._output_root else f"{self._tr('save')}: —"
        )
        self._apply_state(self._app_state)
        self._update_preflight()

    def _show_workspace(self, index: int) -> None:
        if index == 1 and self._app_state != AppState.RUNNING:
            index = 0
        if index == 2 and self._manifest is None:
            index = 0
        if index == 0:
            self._setup_camera_layout.addWidget(self._camera_scroll)
        elif index == 1:
            self._run_camera_layout.addWidget(self._camera_scroll)
        self._workspace_stack.setCurrentIndex(index)
        for i, button in enumerate(self._nav_buttons):
            button.setChecked(i == index)

    # ---------- state and preflight ----------
    def _apply_state(self, state: AppState) -> None:
        self._app_state = state
        state_keys = {
            AppState.IDLE: "idle", AppState.ENUMERATING: "enumerating",
            AppState.PREVIEWING: "preview", AppState.READY_TO_RUN: "ready_state",
            AppState.RUNNING: "running", AppState.STOPPING: "stopping",
            AppState.REVIEW: "review_state", AppState.ERROR: "error",
        }
        self._state_badge.setText(self._tr(state_keys[state]))
        running = state == AppState.RUNNING
        preview = state == AppState.PREVIEWING
        self._refresh_btn.setEnabled(state in (AppState.IDLE, AppState.READY_TO_RUN, AppState.REVIEW))
        self._device_list.setEnabled(not running and not preview)
        self._preview_btn.setEnabled(not running and state != AppState.ENUMERATING)
        self._stop_btn.setEnabled(running or preview)
        self._settings_panel.setEnabled(not running)
        self._run_stim.setText(self._tr("stim_armed") if self._stim_armed else self._tr("stim_disarmed"))

    def _update_preflight(self) -> bool:
        selected = self._checked_sessions()
        roi_missing = [s.name for s in selected if not s.roi_points]
        protocol = self._current_protocol()
        needs_stim = bool(protocol and protocol.shocks)
        checks = {
            "cameras": (bool(selected), self._tr("check_cameras_ok", count=len(selected)) if selected else self._tr("check_cameras_bad")),
            "roi": (bool(selected) and not roi_missing, self._tr("check_roi_ok") if selected and not roi_missing else self._tr("check_roi_bad", names=(": " + ", ".join(roi_missing)) if roi_missing else "")),
            "save": (self._output_root is not None and self._output_root.is_dir(), self._tr("check_save_ok", path=self._output_root) if self._output_root else self._tr("check_save_bad")),
            "protocol": (protocol is not None, self._tr("check_protocol_ok", name=protocol.name, seconds=protocol.total_duration_sec) if protocol else self._tr("check_protocol_bad")),
            "stim": (not needs_stim or self._stim_armed, self._tr("check_stim_ok") if needs_stim and self._stim_armed else self._tr("check_no_stim") if not needs_stim else self._tr("check_stim_bad")),
        }
        for key, (ok, text) in checks.items():
            self._preflight_labels[key].setText(("✓  " if ok else "⚠  ") + text)
            self._preflight_labels[key].setStyleSheet(
                "color:#67E3A0;" if ok else "color:#F5B94C;"
            )
        ready = all(ok for ok, _ in checks.values())
        if self._app_state not in (AppState.RUNNING, AppState.PREVIEWING):
            self._experiment_btn.setEnabled(ready)
            self._apply_state(AppState.READY_TO_RUN if ready else AppState.IDLE)
        failed = [text for ok, text in checks.values() if not ok]
        self._start_reason.setText(
            self._tr("before_start", reasons=self._tr("separator").join(failed))
            if failed else self._tr("ready")
        )
        return ready

    # ---------- overrides: devices and settings ----------
    def _refresh_sources(self) -> None:
        self._apply_state(AppState.ENUMERATING)
        super()._refresh_sources()

    def _on_sources_found(self, cameras_obj: object) -> None:
        super()._on_sources_found(cameras_obj)
        for source_id, session in self._sessions.items():
            device_name = session.name
            session.device_name = device_name
            label = self._config.camera_label(device_name, device_name)
            session.name = label
            session.tile.title.setText(label)
            item = self._items[source_id]
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setText(label)
            item.setToolTip(f"设备：{device_name}\n双击修改实验标签")
        self._update_preflight()

    def _reflow_grid(self) -> None:
        super()._reflow_grid()
        if hasattr(self, "_language"):
            self._device_summary.setText(
                self._tr("selected_count", count=len(self._checked_sessions()))
            )

    def _select_camera(self, source_id: Optional[int]) -> None:
        super()._select_camera(source_id)
        if not hasattr(self, "_language"):
            return
        session = self._sessions.get(source_id) if source_id is not None else None
        self._roi_status.setText(
            self._tr("roi_set") if session and session.roi_points else self._tr("roi_unset")
        )

    def _on_device_checked(self, item: QListWidgetItem) -> None:
        super()._on_device_checked(item)
        source_id = item.data(Qt.ItemDataRole.UserRole)
        session = self._sessions.get(source_id)
        if session is not None and item.text().strip() and item.text() != session.name:
            session.name = item.text().strip()
            session.tile.title.setText(session.name)
            self._config.set_camera_label(session.device_name, session.name)
        self._update_preflight()

    def _on_roi_selected(self, source_id: int, points_obj: object) -> None:
        super()._on_roi_selected(source_id, points_obj)
        self._update_preflight()

    def _set_roi(self) -> None:
        session = self._selected_session()
        if session is None:
            QMessageBox.information(self, "ROI", self._tr("roi_select_camera"))
            return
        if self._experiment_running:
            QMessageBox.information(self, "ROI", self._tr("roi_locked"))
            return
        if session.controller.get_last_image_copy() is None:
            QMessageBox.information(self, "ROI", self._tr("roi_wait_frame"))
            return
        session.tile.video.set_roi_edit_mode(True)
        self._status_bar.showMessage(self._tr("roi_instruction", camera=session.name), 5000)

    def _on_protocol_context_changed(self, _index=None, *, reset_arm: bool = True) -> None:
        protocol = self._current_protocol()
        self._header_protocol.setText(f"{self._tr('protocol')}: {protocol.name}" if protocol else f"{self._tr('protocol')}: —")
        if protocol:
            shocks = "  ".join(f"{s.time_sec:.0f}s ⚡" for s in protocol.shocks)
            self._timeline.setText(
                f"{self._tr('timeline')}  0s  ─────  {shocks or '—'}  ─────  {protocol.total_duration_sec:.0f}s"
            )
        if reset_arm:
            self._stim_armed = False
            self._shock_check.setChecked(False)
        self._update_stim_ui()
        self._update_preflight()

    def _select_output_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self._tr("select_root_title"), str(self._output_root or Path.home()))
        if not path:
            return
        self._output_root = Path(path)
        self._video_save_dir = self._output_root
        self._record_dir_label.setText(path)
        self._header_save.setText(f"{self._tr('save')}: {path}")
        self._update_preflight()

    # ---------- stimulator safety ----------
    def _toggle_stimulator_arm(self) -> None:
        if self._stim_armed:
            self._stim_armed = False
            self._shock_check.setChecked(False)
            self._update_stim_ui()
            self._update_preflight()
            return
        try:
            from shock import find_device

            device = find_device()
            usb.util.dispose_resources(device)
            self._stim_connected = True
            self._stim_armed = True
            self._shock_check.setChecked(True)
        except Exception as exc:
            self._stim_connected = False
            self._stim_armed = False
            QMessageBox.warning(self, self._tr("stim_connection_failed"), str(exc))
        self._update_stim_ui()
        self._update_preflight()

    def _update_stim_ui(self) -> None:
        if self._stim_armed:
            self._arm_btn.setText(self._tr("disarm"))
            self._arm_btn.setObjectName("armed")
            self._stim_header.setText(self._tr("stim_armed"))
            self._stim_header.setStyleSheet("color:#67E3A0; font-weight:700;")
        else:
            self._arm_btn.setText(self._tr("arm"))
            self._arm_btn.setObjectName("arm")
            self._stim_header.setText(self._tr("stim_disarmed"))
            self._stim_header.setStyleSheet("color:#F5B94C; font-weight:700;")
        self._arm_btn.style().unpolish(self._arm_btn)
        self._arm_btn.style().polish(self._arm_btn)

    # ---------- experiment / logging ----------
    def _start_experiment(self) -> None:
        if not self._update_preflight():
            QMessageBox.warning(self, self._tr("preflight_failed"), self._start_reason.text())
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._active_session_dir = self._output_root / f"LiveFreeze_{stamp}"
        self._active_session_dir.mkdir(parents=True, exist_ok=False)
        self._video_save_dir = self._active_session_dir
        self._recent_events.clear()
        self._frame_buffers.clear()
        super()._start_experiment()
        self._video_save_dir = self._output_root
        if not self._experiment_running:
            return
        self._create_manifest(stamp)
        self._apply_state(AppState.RUNNING)
        self._show_workspace(1)
        for session in self._checked_sessions():
            if session.active:
                session.tile.status.setText(self._tr("camera_recording"))
        self._run_recording.setText(self._tr("recording_on", count=len(self._checked_sessions())))
        self._run_recording.setStyleSheet("color:#67E3A0; font-weight:700;")

    def _start_preview(self) -> None:
        super()._start_preview()
        if self._any_active():
            self._apply_state(AppState.PREVIEWING)
            for session in self._checked_sessions():
                if session.active:
                    session.tile.status.setText(self._tr("camera_preview"))

    def _set_running_ui(self, running: bool) -> None:
        super()._set_running_ui(running)
        if running:
            self._apply_state(AppState.RUNNING if self._experiment_running else AppState.PREVIEWING)
        elif self._app_state not in (AppState.REVIEW, AppState.STOPPING):
            self._apply_state(AppState.IDLE)
            self._update_preflight()

    def _on_experiment_tick(self) -> None:
        before = set(self._fired_shocks)
        super()._on_experiment_tick()
        if not self._experiment_running:
            return
        elapsed = self._elapsed()
        protocol = self._current_protocol()
        total = protocol.total_duration_sec if protocol else 0.0
        self._run_clock.setText(f"{elapsed:09.3f}")
        remaining = max(total - elapsed, 0.0) if total > 0 else 0.0
        self._run_remaining.setText(f"{self._tr('remaining')}: {remaining:.1f}s" if total > 0 else f"{self._tr('remaining')}: —")
        self._clock_label.setText(
            f"{self._format_clock(elapsed)} / {self._format_clock(total) if total else '--:--'}"
        )
        new_shocks = self._fired_shocks - before
        for index in new_shocks:
            self._record_shock(index, elapsed, "submitted")
            self._add_recent_event(f"{elapsed:8.3f}s  ⚡ {self._tr('shock_submitted')}")
        pending = [s for i, s in enumerate(protocol.shocks) if i not in self._fired_shocks] if protocol else []
        self._next_shock.setText(f"{self._tr('next_shock')}: {pending[0].time_sec:.3f}s" if pending else f"{self._tr('next_shock')}: —")
        self._flush_frame_logs(force=False)
        self._update_run_camera_summary()

    def _on_freeze(self, source_id: int, frozen: bool, motion: float) -> None:
        session = self._sessions.get(source_id)
        previous = session.last_freeze if session else False
        super()._on_freeze(source_id, frozen, motion)
        if session is None or not self._experiment_running:
            return
        elapsed = self._elapsed()
        session.frame_index = getattr(session, "frame_index", 0) + 1
        line = (
            f"{session.frame_index},{elapsed:.6f},{datetime.now().isoformat(timespec='milliseconds')},"
            f"{motion:.8f},{int(frozen)}\n"
        )
        self._frame_buffers.setdefault(source_id, []).append(line)
        if frozen and not previous:
            self._add_recent_event(f"{elapsed:8.3f}s  {session.name}  {self._tr('freeze_start')}")
        elif previous and not frozen:
            self._add_recent_event(f"{elapsed:8.3f}s  {session.name}  {self._tr('freeze_end')}")

    def _on_frame(self, source_id: int, image, width: int, height: int, fps: float) -> None:
        super()._on_frame(source_id, image, width, height, fps)
        session = self._sessions.get(source_id)
        if session is not None:
            camera_state = self._tr("camera_recording") if self._experiment_running else self._tr("camera_preview")
            behavior = self._tr("camera_freeze") if session.last_freeze else self._tr("camera_moving")
            session.tile.status.setText(f"{camera_state} · {behavior} · {fps:.1f} fps")

    def _on_camera_error(self, source_id: int, message: str) -> None:
        super()._on_camera_error(source_id, message)
        session = self._sessions.get(source_id)
        self._record_error("camera", message, session.name if session else str(source_id))
        self._add_recent_event(f"{self._elapsed():8.3f}s  {self._tr('error')}  {message}")
        session = self._sessions.get(source_id)
        if session is not None:
            session.tile.status.setText(self._tr("camera_error"))

    def _on_shock_error(self, message: str) -> None:
        self._record_error("stimulator", message, "global")
        super()._on_shock_error(message)

    def _stop_all(self, show_status: bool = True) -> None:
        was_experiment = getattr(self, "_experiment_running", False)
        if was_experiment:
            self._session_duration = self._elapsed()
            self._apply_state(AppState.STOPPING)
        super()._stop_all(show_status)
        for session in self._sessions.values():
            session.tile.status.setText(self._tr("camera_stopped"))
        if was_experiment:
            self._flush_frame_logs(force=True)
            self._finalize_manifest()
            self._populate_review()
            self._apply_state(AppState.REVIEW)
            self._show_workspace(2)
        else:
            self._update_preflight()

    def _create_manifest(self, stamp: str) -> None:
        protocol = self._current_protocol()
        protocol_data = {
            "id": protocol.id,
            "name": protocol.name,
            "total_duration_sec": protocol.total_duration_sec,
            "shocks": [vars(s) for s in protocol.shocks],
        }
        protocol_json = json.dumps(protocol_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        cameras = []
        for session in self._checked_sessions():
            width, height, fps = session.controller.last_frame_info()
            frame_path = self._active_session_dir / f"livefreeze_{stamp}_{self._safe_name(session.name)}_frames.csv"
            frame_path.write_text(
                "frame_index,experiment_time_sec,wall_time,motion_value,is_freeze\n",
                encoding="utf-8",
            )
            session.frame_log_path = frame_path
            session.frame_index = 0
            cameras.append(
                {
                    "camera_id": f"cam{session.source_id}",
                    "user_label": session.name,
                    "device_name": getattr(session, "device_name", session.name),
                    "device_index": session.source_id,
                    "resolution": [width, height],
                    "reported_fps": fps,
                    "roi": session.roi_points,
                    "freeze_threshold": session.threshold,
                    "freeze_duration_sec": session.duration_sec,
                    "video_file": getattr(session, "record_path", None).name
                    if getattr(session, "record_path", None)
                    else None,
                    "freeze_csv": session.log_path.name if session.log_path else None,
                    "frames_csv": frame_path.name,
                    "status": "recording",
                }
            )
        self._manifest = {
            "app_version": APP_VERSION,
            "session_id": stamp,
            "start_wall_time": datetime.now().isoformat(),
            "start_monotonic_reference": self._session_start,
            "protocol": protocol_data,
            "protocol_hash_sha256": hashlib.sha256(protocol_json).hexdigest(),
            "save_video": True,
            "cameras": cameras,
            "shock_events": [
                {
                    "scheduled_time_sec": s.time_sec,
                    "current_mA": s.current_mA,
                    "duration": s.duration,
                    "status": "pending",
                    "actual_trigger_time_sec": None,
                }
                for s in protocol.shocks
            ],
            "errors": [],
            "status": "running",
        }
        self._write_manifest()

    def _record_shock(self, index: int, actual_time: float, status: str) -> None:
        if self._manifest and index < len(self._manifest["shock_events"]):
            self._last_shock_index = index
            event = self._manifest["shock_events"][index]
            event["status"] = status
            event["actual_trigger_time_sec"] = actual_time
            self._write_manifest()

    def _on_console_shock_done(self) -> None:
        index = getattr(self, "_last_shock_index", None)
        if self._manifest is not None and index is not None:
            self._manifest["shock_events"][index]["status"] = "success"
            self._write_manifest()

    def _record_error(self, category: str, message: str, source: str) -> None:
        if self._manifest is not None:
            self._manifest["errors"].append(
                {
                    "experiment_time_sec": self._elapsed(),
                    "wall_time": datetime.now().isoformat(),
                    "category": category,
                    "source": source,
                    "message": message,
                }
            )
            self._write_manifest()

    def _flush_frame_logs(self, force: bool) -> None:
        for source_id, lines in self._frame_buffers.items():
            if not lines or (not force and len(lines) < 100):
                continue
            session = self._sessions.get(source_id)
            path = getattr(session, "frame_log_path", None) if session else None
            if path:
                with Path(path).open("a", encoding="utf-8") as stream:
                    stream.writelines(lines)
            lines.clear()

    def _finalize_manifest(self) -> None:
        if self._manifest is None:
            return
        self._manifest["status"] = "completed"
        self._manifest["end_wall_time"] = datetime.now().isoformat()
        self._manifest["actual_duration_sec"] = self._session_duration
        for camera in self._manifest["cameras"]:
            session = self._sessions.get(camera["device_index"])
            if session:
                width, height, fps = session.controller.last_frame_info()
                camera["resolution"] = [width, height]
                camera["reported_fps"] = fps
                camera["freeze_bout_count"] = len(session.bouts)
                camera["freeze_total_sec"] = sum(end - start for start, end in session.bouts)
                camera["status"] = "completed"
        self._write_manifest()

    def _write_manifest(self) -> None:
        if self._manifest is not None and self._active_session_dir is not None:
            path = self._active_session_dir / f"livefreeze_{self._manifest['session_id']}_session.json"
            path.write_text(json.dumps(self._manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- review ----------
    def _populate_review(self) -> None:
        self._review_path.setText(str(self._active_session_dir or ""))
        self._summary_table.setRowCount(0)
        duration = max(self._session_duration, 0.001)
        for session in self._checked_sessions():
            total = sum(end - start for start, end in session.bouts)
            row = self._summary_table.rowCount()
            self._summary_table.insertRow(row)
            values = [session.name, str(len(session.bouts)), f"{total:.3f}", f"{total/duration*100:.2f}%", self._tr("completed")]
            for column, value in enumerate(values):
                self._summary_table.setItem(row, column, QTableWidgetItem(value))

    def _export_summary_csv(self) -> None:
        if self._active_session_dir is None:
            return
        path = self._active_session_dir / "session_summary.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["camera", "freeze_bouts", "freeze_total_sec", "freeze_percent"])
            duration = max(self._session_duration, 0.001)
            for session in self._checked_sessions():
                total = sum(end - start for start, end in session.bouts)
                writer.writerow([session.name, len(session.bouts), f"{total:.3f}", f"{total/duration*100:.3f}"])
        self._status_bar.showMessage(self._tr("summary_exported", path=path), 5000)

    def _open_session_folder(self) -> None:
        if self._active_session_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._active_session_dir)))

    def _add_recent_event(self, text: str) -> None:
        self._recent_events.insertItem(0, text)
        while self._recent_events.count() > 100:
            self._recent_events.takeItem(self._recent_events.count() - 1)

    def _update_run_camera_summary(self) -> None:
        lines = []
        for session in self._checked_sessions():
            _w, _h, fps = session.controller.last_frame_info()
            behavior = "FREEZE" if session.last_freeze else "Moving"
            lines.append(f"{session.name}: {fps:.1f} fps · {behavior}")
        self._run_camera_summary.setText("\n".join(lines))

    @staticmethod
    def _format_clock(seconds: float) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value).strip("_") or "camera"


MainWindow = ExperimentConsoleWindow
