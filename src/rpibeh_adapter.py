"""
直接使用 RpiBeh (NiLab-FDU) 的 DetectFreezing 与 Utils，仅提供最小 config/controller 适配。
https://github.com/NiLab-FDU/RpiBeh
"""
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

import cv2
import numpy as np

from .paths import get_project_root

_rpibeh_root = str(get_project_root() / "RpiBeh_repo")
if _rpibeh_root not in sys.path:
    sys.path.insert(0, _rpibeh_root)

from client_host.PostDetect import DetectFreezing  # noqa: E402
from client_host.Utils import get_largest_component_and_center  # noqa: E402


class _MinimalConfig:
    """最小 config，仅提供 DetectFreezing 需要的接口，与 RpiBeh ConfigManager 一致。"""

    def __init__(
        self,
        freezing_threshold: str = "0.0003",
        freezing_duration: str = "0.5s",
        area_type=None,
        area_points=None,
    ):
        self.settings_config = {
            "Detection": {
                "freezing_threshold": freezing_threshold,
                "freezing_duration": freezing_duration,
            },
            "Region of interest": {
                "area_type": area_type,
                "area_points": area_points if area_points is not None else [],
            },
        }
        self.close_loop_config = {"Close Loop Method": "None"}

    def get_detection_threshold_and_dur(self, detection_name: str) -> Tuple[float, float]:
        config = self.settings_config["Detection"]
        th = float(config[detection_name + "_threshold"])
        dur_str = config[detection_name + "_duration"]
        dur = float(dur_str.replace("s", "").strip())
        return th, dur

    def get_region_of_interest_area(self) -> Tuple[object, np.ndarray]:
        config = self.settings_config["Region of interest"]
        at = config["area_type"]
        ap = config["area_points"]
        return at, np.array(ap) if ap is not None else np.array([])

    def get_close_loop_method(self) -> str:
        return self.close_loop_config["Close Loop Method"]


class _MinimalController:
    """最小 controller，仅带 config_manager，供 DetectFreezing 使用。"""

    def __init__(self, config: _MinimalConfig):
        self.config_manager = config


class RpiBehFreezeAdapter:
    """
    封装 RpiBeh 的 DetectFreezing，提供 push_frame(bgr) -> (is_freeze, motion_level)。
    完全使用其现成逻辑，仅此薄封装便于接入我们的 worker。
    """

    def __init__(
        self,
        fps: float = 30.0,
        threshold: str = "0.0003",
        duration_str: str = "0.5s",
        delay: float = 0.0,
        duration: float = 0.0,
        area_type: Optional[str] = None,
        area_points: Optional[list[list[int]]] = None,
    ):
        config = _MinimalConfig(
            freezing_threshold=threshold,
            freezing_duration=duration_str,
            area_type=area_type,
            area_points=area_points,
        )
        controller = _MinimalController(config)
        self._detector = DetectFreezing(controller, fps, delay, duration)

    @property
    def fps(self) -> float:
        return self._detector.fps

    @fps.setter
    def fps(self, value: float) -> None:
        self._detector.fps = value

    @property
    def duration_sec(self) -> float:
        return self._detector.dur_time

    @property
    def over_th_frame_num(self) -> int:
        return self._detector.over_th_frame_num

    @over_th_frame_num.setter
    def over_th_frame_num(self, value: int) -> None:
        self._detector.over_th_frame_num = value

    def set_threshold(self, value: float) -> None:
        """运行时更新冻结阈值（运动面积比），下一帧起生效。"""
        self._detector.threshold = float(value)

    def set_duration_sec(self, value: float) -> None:
        """运行时更新判定冻结所需持续时长(秒)，下一帧起生效。"""
        self._detector.dur_time = float(value)
        self._detector.over_th_frame_num = max(int(value * self._detector.fps), 1)

    def set_roi(self, area_type: Optional[str], area_points: Optional[list[list[int]]]) -> None:
        """运行时更新 ROI。area_type 常用 'polygon'；None 表示取消 ROI。"""
        self._detector.area_type = area_type
        if area_points:
            self._detector.area_points = np.array(area_points)
        else:
            self._detector.area_points = np.array([])

    def _mask_to_roi(self, img: np.ndarray) -> np.ndarray:
        """仅保留 ROI 内区域，ROI 外置黑。"""
        if self._detector.area_type is None or self._detector.area_points is None:
            return img
        points = np.array(self._detector.area_points)
        if points.size == 0:
            return img
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [points.astype(np.int32)], 255)
        return cv2.bitwise_and(img, img, mask=mask)

    def reset(self) -> None:
        self._detector.clear_params()

    def push_frame(self, bgr_frame: np.ndarray) -> Tuple[bool, float, Optional[np.ndarray]]:
        """
        与 RpiBeh DetectFreezing.get_res 一致；并返回处理图（运动二值图）供右侧显示。
        返回 (is_freezing, motion_level, thresh_img)。
        """
        current_time = time.time()
        prev_frame = (
            self._detector.last_frame.copy()
            if self._detector.last_frame is not None
            else None
        )
        input_data = [current_time, bgr_frame]
        res_list = self._detector.get_res(input_data)
        thresh_img = None
        if prev_frame is not None:
            try:
                _, thresh_img, _, _, _ = get_largest_component_and_center(
                    bgr_frame,
                    prev_frame,
                    diff_type="div",
                    div_coeff=5,
                    thresh_type="manual",
                    thresh=120,
                    use_open_close=True,
                    get_edge=False,
                    area_type=self._detector.area_type,
                    area_points=self._detector.area_points,
                )
                if thresh_img is not None:
                    thresh_img = self._mask_to_roi(thresh_img)
            except Exception:
                pass
        if not res_list or not res_list[0]:
            return False, 0.0, thresh_img
        row = res_list[0]
        is_freeze = bool(row[0])
        area_sum = row[2]
        motion = float(area_sum) if not np.isnan(area_sum) else 0.0
        return is_freeze, motion, thresh_img
