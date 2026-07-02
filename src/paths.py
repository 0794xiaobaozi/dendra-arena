"""
项目根目录与资源路径解析。
- 开发时：仓库根目录
- 打包后：PyInstaller _internal 目录（sys._MEIPASS）
- protocols 特殊处理：打包后优先从 exe 同级的 protocols/ 读取（方便用户修改），
  若不存在则回退到 _internal/protocols/
"""
import sys
from pathlib import Path


def get_project_root() -> Path:
    """开发时返回仓库根；打包运行时返回 _MEIPASS（即 _internal 目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_protocols_dir() -> Path:
    """
    返回 protocols 目录路径。
    打包后优先使用 exe 同级的 protocols/（用户可自行修改），
    若不存在则回退到 _internal/protocols/。
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        external = exe_dir / "protocols"
        if external.is_dir():
            return external
    return get_project_root() / "protocols"
