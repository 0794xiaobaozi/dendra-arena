"""Lightweight runtime localization and bundled CJK font loading."""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from .paths import get_project_root


TEXT = {
    "en": {
        "window_title": "LiveFreeze — Experiment Console",
        "setup": "Setup", "run": "Run", "review": "Review",
        "protocol": "Protocol", "save": "Save", "stim_disarmed": "Stimulator: DISARMED",
        "stim_armed": "Stimulator: ARMED", "connect_preview": "Connect & Preview",
        "start_experiment": "Start Experiment", "stop_experiment": "End Experiment",
        "snapshot": "Capture Selected Camera", "select_output": "Select Session Folder",
        "arm": "Detect & Arm Stimulator", "disarm": "Disarm Stimulator",
        "preflight": "Preflight Checklist", "rename_hint": "Double-click a device name to assign a label such as Box A.",
        "experiment_status": "Experiment Status", "remaining": "Remaining", "recording_off": "● Recording: OFF",
        "recording_on": "● Recording: ON · {count} streams", "next_shock": "Next shock", "timeline": "Timeline",
        "recent_events": "Recent Events", "no_active": "No active cameras",
        "session_review": "Session Review", "no_session": "No completed session",
        "open_folder": "Open Session Folder", "export_summary": "Export Summary CSV",
        "freeze_details": "Freeze Event Details", "camera": "Camera", "freeze_bouts": "Freeze bouts",
        "freeze_total": "Freeze total (s)", "freeze_percent": "Freeze %", "status": "Status",
        "completed": "Completed", "refresh_devices": "Refresh Devices", "device_note": "Select cameras for simultaneous preview or experiment.",
        "selected_count": "{count} selected", "current_camera": "Selected Camera", "device": "Device",
        "threshold": "Freeze threshold", "duration": "Minimum duration (s)", "roi": "ROI",
        "set_roi": "Draw ROI on Selected Camera", "roi_set": "Configured", "roi_unset": "Not configured",
        "processed": "Selected Camera · Motion Detection", "global_experiment": "Global Experiment",
        "experiment_protocol": "Protocol", "refresh_protocol": "Reload Protocols", "save_location": "Save location",
        "camera_list_empty": "No camera selected", "waiting_preview": "Waiting for preview", "not_started": "Idle",
        "camera_preview": "PREVIEW", "camera_recording": "REC", "camera_moving": "Moving", "camera_freeze": "FREEZE",
        "camera_stopped": "Stopped", "camera_error": "Error", "open_failed": "Open failed",
        "roi_select_camera": "Select a camera first.", "roi_locked": "ROI cannot be changed during an experiment.",
        "roi_wait_frame": "Start preview and wait for an image first.", "roi_instruction": "Drag on {camera} to draw the ROI.",
        "events_all": "Freeze Events (All Cameras)",
        "status_select": "Refresh devices, select cameras, configure ROI, then complete Preflight.",
        "check_cameras_ok": "{count} cameras selected", "check_cameras_bad": "No cameras selected",
        "check_roi_ok": "ROI configured for every camera", "check_roi_bad": "ROI incomplete{names}",
        "check_save_ok": "Session folder valid: {path}", "check_save_bad": "Session folder not selected",
        "check_protocol_ok": "Protocol valid: {name} / {seconds:.0f}s", "check_protocol_bad": "Protocol invalid",
        "check_stim_ok": "Stimulator armed", "check_no_stim": "Protocol has no shock events", "check_stim_bad": "Stimulator not armed",
        "ready": "Ready to start", "before_start": "Before start: {reasons}", "separator": "; ",
        "select_root_title": "Select session data folder", "stim_connection_failed": "Stimulator connection failed",
        "preflight_failed": "Preflight Failed", "shock_submitted": "Shock submitted",
        "freeze_start": "Freeze start", "freeze_end": "Freeze end", "error": "ERROR",
        "summary_exported": "Summary exported: {path}", "running": "Running", "preview": "Preview",
        "idle": "Idle", "enumerating": "Enumerating", "ready_state": "Ready", "stopping": "Stopping", "review_state": "Review",
        "summary_headers": ["Camera", "Freeze bouts", "Freeze total (s)", "Freeze %", "Status"],
        "event_headers": ["Camera", "#", "Start (s)", "End (s)", "Duration (s)"],
    },
    "zh": {
        "window_title": "LiveFreeze — 实验控制台",
        "setup": "准备", "run": "运行", "review": "复盘",
        "protocol": "方案", "save": "保存", "stim_disarmed": "刺激器：未武装",
        "stim_armed": "刺激器：已武装", "connect_preview": "连接并预览",
        "start_experiment": "开始实验", "stop_experiment": "结束实验",
        "snapshot": "截取当前摄像头", "select_output": "选择实验保存目录",
        "arm": "检测并武装刺激器", "disarm": "解除刺激器武装",
        "preflight": "实验前检查", "rename_hint": "双击设备名称，可改为 Box A、Box B 等实验标签。",
        "experiment_status": "实验状态", "remaining": "剩余时间", "recording_off": "● 录像：关闭",
        "recording_on": "● 录像：{count} 路正在写入", "next_shock": "下次刺激", "timeline": "时间轴",
        "recent_events": "最近事件", "no_active": "没有运行中的摄像头",
        "session_review": "实验复盘", "no_session": "尚无已完成实验",
        "open_folder": "打开保存目录", "export_summary": "导出汇总 CSV",
        "freeze_details": "Freeze 事件明细", "camera": "摄像头", "freeze_bouts": "Freeze 次数",
        "freeze_total": "Freeze 总时长 (s)", "freeze_percent": "Freeze 占比", "status": "状态",
        "completed": "已完成", "refresh_devices": "刷新设备", "device_note": "勾选需要同时预览或实验的摄像头。",
        "selected_count": "已选择 {count} 台", "current_camera": "当前摄像头", "device": "设备",
        "threshold": "冻结阈值", "duration": "最短持续时间 (s)", "roi": "ROI",
        "set_roi": "在当前画面框选 ROI", "roi_set": "已设置", "roi_unset": "未设置",
        "processed": "当前摄像头 · 运动检测", "global_experiment": "全局实验",
        "experiment_protocol": "实验方案", "refresh_protocol": "刷新方案", "save_location": "保存位置",
        "camera_list_empty": "尚未选择摄像头", "waiting_preview": "等待预览", "not_started": "未启动",
        "camera_preview": "预览", "camera_recording": "录像", "camera_moving": "运动", "camera_freeze": "FREEZE",
        "camera_stopped": "已停止", "camera_error": "错误", "open_failed": "打开失败",
        "roi_select_camera": "请先选择一台摄像头。", "roi_locked": "实验进行中不能修改 ROI。",
        "roi_wait_frame": "请先启动预览并等待画面出现。", "roi_instruction": "请在 {camera} 画面中拖拽框选 ROI。",
        "events_all": "Freeze 事件（全部摄像头）",
        "status_select": "刷新设备、选择摄像头、设置 ROI，然后完成实验前检查。",
        "check_cameras_ok": "已选择 {count} 台摄像头", "check_cameras_bad": "尚未选择摄像头",
        "check_roi_ok": "所有摄像头 ROI 已设置", "check_roi_bad": "ROI 未完成{names}",
        "check_save_ok": "保存目录有效：{path}", "check_save_bad": "尚未选择保存目录",
        "check_protocol_ok": "方案有效：{name} / {seconds:.0f} 秒", "check_protocol_bad": "实验方案无效",
        "check_stim_ok": "刺激器已武装", "check_no_stim": "方案不包含刺激事件", "check_stim_bad": "刺激器尚未武装",
        "ready": "可以开始实验", "before_start": "开始实验前：{reasons}", "separator": "；",
        "select_root_title": "选择实验数据根目录", "stim_connection_failed": "刺激器连接失败",
        "preflight_failed": "实验前检查未通过", "shock_submitted": "已提交刺激",
        "freeze_start": "Freeze 开始", "freeze_end": "Freeze 结束", "error": "错误",
        "summary_exported": "汇总已导出：{path}", "running": "运行中", "preview": "预览",
        "idle": "空闲", "enumerating": "枚举设备", "ready_state": "就绪", "stopping": "正在停止", "review_state": "复盘",
        "summary_headers": ["摄像头", "Freeze 次数", "Freeze 总时长 (s)", "Freeze 占比", "状态"],
        "event_headers": ["摄像头", "#", "开始 (s)", "结束 (s)", "持续 (s)"],
    },
}


def text(language: str, key: str, **values):
    value = TEXT.get(language, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return value.format(**values) if isinstance(value, str) else value


def load_bundled_font() -> str:
    """Register a bundled OFL CJK font and return a usable UI family."""
    path = get_project_root() / "assets" / "NotoSansSC.ttf"
    if path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    available = set(QFontDatabase.families())
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI"):
        if family in available:
            return family
    return QApplication.font().family()


def apply_application_font(family: str) -> None:
    QApplication.setFont(QFont(family, 10))
