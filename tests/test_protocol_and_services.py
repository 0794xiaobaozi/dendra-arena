import unittest
import time
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from src.config_service import ConfigService
from src.experiment_protocol import _parse_one
from src.main_window import MainWindow
from src.shock_service import ShockWorker
from src.video_capture_worker import VideoCaptureWorker


class ProtocolValidationTests(unittest.TestCase):
    @staticmethod
    def _data(**shock_overrides):
        shock = {"time_sec": 5, "current_mA": 1.0, "duration": 10}
        shock.update(shock_overrides)
        return {
            "schema_version": 1,
            "protocol": {
                "id": "test",
                "name": "Test",
                "total_duration_sec": 10,
                "shocks": [shock],
            },
        }

    def test_accepts_valid_protocol(self):
        protocol = _parse_one(self._data(), "test")
        self.assertEqual(protocol.shocks[0].current_mA, 1.0)

    def test_rejects_unsafe_current(self):
        with self.assertRaisesRegex(ValueError, "<= 4.0"):
            _parse_one(self._data(current_mA=4.01), "test")

    def test_rejects_zero_duration(self):
        with self.assertRaises(ValueError):
            _parse_one(self._data(duration=0), "test")

    def test_rejects_shock_after_session_end(self):
        with self.assertRaisesRegex(ValueError, "total_duration_sec"):
            _parse_one(self._data(time_sec=11), "test")


class ShockSignalTests(unittest.TestCase):
    def test_failure_does_not_emit_success(self):
        worker = ShockWorker()
        events = []
        worker.error.connect(lambda message: events.append(("error", message)))
        worker.finished.connect(lambda: events.append(("finished", None)))
        with patch("src.shock_service._run_shock_sequence", return_value="USB failed"):
            worker._do_run()
        self.assertEqual(events, [("error", "USB failed")])


class SourceSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_placeholder_is_not_camera_zero(self):
        window = MainWindow(ConfigService())
        self.assertEqual(window._current_source(), -1)
        window.close()

    def test_session_ends_even_when_shock_is_disabled(self):
        window = MainWindow(ConfigService())
        window._controller._worker = object()
        window._preview_start_time = time.time() - 11
        stopped = []
        window._on_stop = lambda: stopped.append(True)
        window._on_scheduled_shock_tick()
        self.assertEqual(stopped, [True])
        window._controller._worker = None
        window.close()


class CaptureShutdownTests(unittest.TestCase):
    def test_worker_thread_does_not_wait_for_itself(self):
        class FakeThread:
            waited = False

            def isRunning(self):
                return True

            def quit(self):
                pass

            def wait(self, _timeout):
                self.waited = True

        worker = VideoCaptureWorker(0)
        thread = FakeThread()
        worker._thread = thread
        with patch("src.video_capture_worker.QThread.currentThread", return_value=thread):
            worker.stop_capture()
        self.assertFalse(thread.waited)


if __name__ == "__main__":
    unittest.main()
