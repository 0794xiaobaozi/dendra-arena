# PyInstaller spec：把 arena_backend 打包为独立 exe，供 Tauri 捆绑
# 用法：pyinstaller backend\backend.spec

import sys
from pathlib import Path

block_cipher = None

# 后端入口模块
entry_script = Path("backend/arena_backend/main.py").resolve()

# RpiBeh client_host 模块（freeze 检测必需）
rpi_beh = Path("RpiBeh_repo/client_host").resolve()
rpi_beh_datas = [
    (str(rpi_beh / name), "RpiBeh_repo/client_host")
    for name in ("__init__.py", "PostDetect.py", "Utils.py", "DataBuffer.py", "Custom.py")
    if (rpi_beh / name).is_file()
]

a = Analysis(
    [str(entry_script)],
    pathex=[],
    binaries=[],
    datas=rpi_beh_datas,
    hiddenimports=[
        "numpy",
        "cv2",
        "yaml",
        "usb",
        "usb.backend.libusb1",
        "usb.backend.libusb0",
        "libusb_package",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="arena-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="arena-backend",
)
