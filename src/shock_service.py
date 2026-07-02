"""
电刺激服务：在后台线程执行 shock.run_sequence，不阻塞 GUI。
"""
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal


def _run_shock_sequence(current_mA: float, duration: int) -> Optional[str]:
    """在调用线程执行一次刺激，成功返回 None，失败返回错误信息。"""
    try:
        from shock import run_sequence
        run_sequence(current_mA, duration, settle_s=0.05)
        return None
    except Exception as e:
        return str(e)


class ShockWorker(QObject):
    """在独立线程中执行 run_sequence。"""

    finished = Signal()
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._current_mA = 0.0
        self._duration = 0
        self._thread: Optional[QThread] = None

    def run_once(self, current_mA: float, duration: int) -> QThread:
        self._current_mA = current_mA
        self._duration = duration
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._do_run)
        self._thread.start()
        return self._thread

    def _do_run(self) -> None:
        err = _run_shock_sequence(self._current_mA, self._duration)
        if err:
            self.error.emit(err)
        else:
            self.finished.emit()
        if self._thread and self._thread.isRunning():
            self._thread.quit()


class ShockService(QObject):
    """
    对外接口：trigger_shock(current_mA, duration) 在后台执行一次刺激。
    信号 shock_done / shock_error 供界面提示。
    """

    shock_done = Signal()
    shock_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._worker: Optional[ShockWorker] = None
        self._thread: Optional[QThread] = None
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def trigger_shock(self, current_mA: float, duration: int) -> bool:
        """请求一次电刺激；若正在执行则忽略。返回是否已提交。"""
        if self._busy:
            return False
        self._busy = True
        self._worker = ShockWorker()
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread = self._worker.run_once(current_mA, duration)
        self._thread.finished.connect(self._on_thread_finished)
        return True

    def _on_thread_finished(self) -> None:
        self._busy = False
        self._worker = None
        self._thread = None

    def _on_finished(self) -> None:
        self.shock_done.emit()

    def _on_error(self, message: str) -> None:
        self.shock_error.emit(message)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """窗口退出时等待正在进行的 USB 命令完成，避免销毁运行中的 QThread。"""
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        thread.quit()
        return thread.wait(timeout_ms)
