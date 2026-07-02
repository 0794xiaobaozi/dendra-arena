import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.config_service import ConfigService
from src.multi_camera_window import MultiCameraWindow


class MultiCameraWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MultiCameraWindow(ConfigService())
        self.window._on_sources_found(
            [(0, "Camera A"), (1, "Camera B"), (2, "Camera C"), (3, "Camera D")]
        )

    def tearDown(self):
        self.window.close()

    def _check_all(self):
        for item in self.window._items.values():
            item.setCheckState(Qt.CheckState.Checked)

    def test_checked_cameras_are_arranged_in_two_by_two_grid(self):
        self._check_all()
        positions = {
            self.window._grid.getItemPosition(index)[:2]
            for index in range(self.window._grid.count())
        }
        self.assertEqual(positions, {(0, 0), (0, 1), (1, 0), (1, 1)})
        self.assertEqual(self.window._device_summary.text(), "4 台已选择")

    def test_each_checked_camera_starts_an_independent_session(self):
        self._check_all()
        for session in self.window._sessions.values():
            session.controller.start_preview = lambda *args, **kwargs: True
        self.window._start_sessions(experiment=False)
        self.assertTrue(all(session.active for session in self.window._sessions.values()))
        self.assertEqual(self.window._status_bar.currentMessage(), "预览已启动：4 台摄像头")

    def test_selected_camera_owns_its_parameter_values(self):
        self._check_all()
        self.window._select_camera(1)
        self.window._threshold_spin.setValue(0.00123)
        self.window._duration_spin.setValue(1.7)
        self.assertAlmostEqual(self.window._sessions[1].threshold, 0.00123)
        self.assertAlmostEqual(self.window._sessions[1].duration_sec, 1.7)
        self.assertAlmostEqual(self.window._sessions[0].threshold, 0.0003)


if __name__ == "__main__":
    unittest.main()
