"""
LiveFreeze 视频预览 — 入口。
"""
from __future__ import annotations

import sys
import traceback
import ctypes
import os
from datetime import datetime
from pathlib import Path


def _log_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _write_crash_log(exc_text: str) -> Path | None:
    try:
        log_dir = _log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "livefreeze_crash.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meipass = getattr(sys, "_MEIPASS", "")
        path_head = os.environ.get("PATH", "")[:600]
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                f"\n[{timestamp}]\n"
                f"sys.executable={sys.executable}\n"
                f"sys.frozen={getattr(sys, 'frozen', False)}\n"
                f"sys._MEIPASS={meipass}\n"
                f"PATH(head)={path_head}\n"
                f"{exc_text}\n"
            )
        return log_path
    except Exception:
        return None


def _prepare_windows_dll_search_paths() -> None:
    if sys.platform != "win32":
        return
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        base_dir,
        base_dir / "PySide6",
        base_dir / "shiboken6",
        base_dir / "cv2",
        base_dir / "numpy.libs",
    ]
    existing = [p for p in candidates if p.is_dir()]
    if hasattr(os, "add_dll_directory"):
        for path in existing:
            try:
                os.add_dll_directory(str(path))
            except OSError:
                pass
    path_head = os.environ.get("PATH", "")
    prepend = os.pathsep.join(str(p) for p in existing)
    if prepend:
        os.environ["PATH"] = prepend + os.pathsep + path_head if path_head else prepend


def _diagnose_windows_qt_load() -> None:
    if sys.platform != "win32":
        return
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    dlls = [
        base_dir / "python3.dll",
        base_dir / "VCRUNTIME140.dll",
        base_dir / "VCRUNTIME140_1.dll",
        base_dir / "vcruntime140_threads.dll",
        base_dir / "MSVCP140.dll",
        base_dir / "msvcp140_1.dll",
        base_dir / "msvcp140_2.dll",
        base_dir / "concrt140.dll",
        base_dir / "PySide6" / "shiboken6.abi3.dll",
        base_dir / "PySide6" / "pyside6.abi3.dll",
        base_dir / "PySide6" / "Qt6Core.dll",
        base_dir / "PySide6" / "QtCore.pyd",
    ]
    lines: list[str] = []
    for dll in dlls:
        if not dll.exists():
            lines.append(f"MISSING {dll}")
            continue
        try:
            ctypes.WinDLL(str(dll))
            lines.append(f"OK {dll.name}")
        except OSError as e:
            lines.append(f"FAIL {dll.name}: {e}")
    _write_crash_log("DLL preload diagnostics:\n" + "\n".join(lines))


def _show_fatal_error(message: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        created_app = False
        if app is None:
            app = QApplication(sys.argv)
            created_app = True
        try:
            QMessageBox.critical(None, "LiveFreeze 启动失败", message)
        finally:
            if created_app:
                app.quit()
    except Exception:
        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "LiveFreeze 启动失败",
            0x10,
        )


def _handle_unexpected_exception(exc_type, exc_value, exc_tb) -> None:
    exc_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log_path = _write_crash_log(exc_text)
    details = f"\n\n崩溃日志: {log_path}" if log_path else ""
    _show_fatal_error(
        "程序发生未处理异常，无法继续运行。"
        f"{details}\n\n错误摘要:\n{exc_value}"
    )


def main() -> None:
    sys.excepthook = _handle_unexpected_exception
    _prepare_windows_dll_search_paths()
    _diagnose_windows_qt_load()
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication
    from src.app_icon import create_app_icon
    from src.config_service import ConfigService
    from src.i18n import apply_application_font, load_bundled_font
    from src.console_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    apply_application_font(load_bundled_font())
    app.setWindowIcon(create_app_icon())
    config = ConfigService()
    win = MainWindow(config)
    if "--smoke-test" in sys.argv:
        # 打包后启动检查：完成所有模块导入和主窗口构造后自动正常退出。
        QTimer.singleShot(0, app.quit)
    else:
        win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        exc_text = traceback.format_exc()
        log_path = _write_crash_log(exc_text)
        if "--smoke-test" in sys.argv:
            sys.stderr.write(exc_text)
            sys.exit(1)
        details = f"\n\n崩溃日志: {log_path}" if log_path else ""
        _show_fatal_error(
            "程序在启动阶段失败。"
            f"{details}\n\n请把该日志发回开发端定位问题。"
        )
        sys.exit(1)
