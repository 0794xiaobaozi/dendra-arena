import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.config_service import ConfigService
from src.console_window import AppState, ExperimentConsoleWindow


class ConsoleWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = ExperimentConsoleWindow(ConfigService())
        self.window._on_sources_found([(0, "Console Test Camera")])
        self.window._items[0].setCheckState(Qt.CheckState.Checked)

    def tearDown(self):
        self.window.close()

    def test_workflow_has_three_pages(self):
        self.window._apply_language("en")
        self.assertEqual(self.window._workspace_stack.count(), 3)
        self.assertEqual([b.text() for b in self.window._nav_buttons], ["Setup", "Run", "Review"])

    def test_preflight_blocks_missing_roi_save_and_stimulator(self):
        self.window._apply_language("zh")
        self.assertFalse(self.window._update_preflight())
        self.assertFalse(self.window._experiment_btn.isEnabled())
        self.assertIn("ROI", self.window._start_reason.text())
        self.assertIn("刺激器", self.window._start_reason.text())

    def test_runtime_language_switch_covers_workflow_and_preflight(self):
        self.window._apply_language("en")
        self.assertEqual(self.window._nav_buttons[0].text(), "Setup")
        self.assertIn("Before start", self.window._start_reason.text())
        self.window._apply_language("zh")
        self.assertEqual(self.window._nav_buttons[0].text(), "准备")
        self.assertIn("开始实验前", self.window._start_reason.text())
        self.assertEqual(self.window._event_table.horizontalHeaderItem(0).text(), "摄像头")

    def test_completed_experiment_writes_manifest_and_review(self):
        session = self.window._sessions[0]
        session.roi_type = "polygon"
        session.roi_points = [[0, 0], [100, 0], [100, 100], [0, 100]]
        session.controller.start_preview = lambda *args, **kwargs: True
        self.window._stim_armed = True
        self.window._shock_check.setChecked(True)
        with tempfile.TemporaryDirectory() as directory:
            self.window._output_root = Path(directory)
            self.window._video_save_dir = self.window._output_root
            self.assertTrue(self.window._update_preflight())
            self.window._start_experiment()
            self.assertEqual(self.window._app_state, AppState.RUNNING)
            self.assertIsNotNone(self.window._manifest)
            self.window._stop_all()
            self.assertEqual(self.window._app_state, AppState.REVIEW)
            manifests = list(Path(directory).glob("LiveFreeze_*/*_session.json"))
            self.assertEqual(len(manifests), 1)
            data = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["cameras"][0]["user_label"], session.name)


if __name__ == "__main__":
    unittest.main()
