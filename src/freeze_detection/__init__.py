# Freeze 检测：直接使用 RpiBeh (NiLab-FDU) 的 DetectFreezing
# https://github.com/NiLab-FDU/RpiBeh

from ..rpibeh_adapter import RpiBehFreezeAdapter

# 对外仍叫 FreezeDetector，便于 VideoController 等无需改引用
FreezeDetector = RpiBehFreezeAdapter

__all__ = ["FreezeDetector", "RpiBehFreezeAdapter"]
