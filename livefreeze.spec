# PyInstaller spec：打包为独立文件夹，便于迁移到其他电脑
# 使用：先安装 pyinstaller（pixi add -G pyinstaller 或 pip install pyinstaller），再执行：
#   pyinstaller livefreeze.spec

import sys
from pathlib import Path

block_cipher = None

# 打包时带上的数据：protocols 目录、RpiBeh_repo 目录、根目录的 shock.py
datas = [
    ('protocols', 'protocols'),
    ('assets/NotoSansSC.ttf', 'assets'),
    ('assets/NotoSansSC-OFL.txt', 'assets'),
    ('RpiBeh_repo/client_host/__init__.py', 'RpiBeh_repo/client_host'),
    ('RpiBeh_repo/client_host/PostDetect.py', 'RpiBeh_repo/client_host'),
    ('RpiBeh_repo/client_host/Utils.py', 'RpiBeh_repo/client_host'),
    ('RpiBeh_repo/client_host/DataBuffer.py', 'RpiBeh_repo/client_host'),
    ('RpiBeh_repo/client_host/Custom.py', 'RpiBeh_repo/client_host'),
    ('shock.py', '.'),
]

# 确保 PySide6、matplotlib、yaml、pyusb backend 等被正确收集
hiddenimports = [
    'yaml',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'matplotlib',
    'matplotlib.backends.backend_qtagg',
    'numpy',
    'cv2',
    'usb.backend.libusb1',
    'usb.backend.libusb0',
]


def _runtime_binaries():
    env_root = Path(sys.prefix)
    site_packages = env_root / 'Lib' / 'site-packages'
    names = [
        'vcruntime140.dll',
        'vcruntime140_1.dll',
        'vcruntime140_threads.dll',
        'concrt140.dll',
        'msvcp140.dll',
        'msvcp140_1.dll',
        'msvcp140_2.dll',
        'msvcp140_atomic_wait.dll',
        'msvcp140_codecvt_ids.dll',
        'ucrtbase.dll',
        'vcomp140.dll',
        'vccorlib140.dll',
        'vcamp140.dll',
    ]
    search_roots = [
        env_root,
        site_packages / 'PySide6',
        site_packages / 'shiboken6',
    ]
    out = []
    for name in names:
        seen = False
        for root in search_roots:
            candidate = root / name
            if candidate.is_file():
                out.append((str(candidate), '.'))
                out.append((str(candidate), 'PySide6'))
                seen = True
                break
        if seen:
            continue
    shiboken_dll = site_packages / 'shiboken6' / 'shiboken6.abi3.dll'
    if shiboken_dll.is_file():
        out.append((str(shiboken_dll), 'PySide6'))
    return out

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_runtime_binaries(),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Qt 6.10 的 Windows wheel 使用 Windows 自带 ICU。开发机 PATH 中若存在
# Conda，PyInstaller 可能误收集只导出 ucnv_open_73 的 ICU 73，并遮蔽
# 系统中导出 ucnv_open 的 DLL，最终让目标电脑无法加载 Qt6Core.dll。
_forbidden_icu = {'icuuc.dll', 'icudt73.dll', 'icuuc73.dll'}
a.binaries = [
    entry for entry in a.binaries
    if Path(entry[0]).name.lower() not in _forbidden_icu
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='livefreeze',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 不弹出黑色命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='livefreeze',
)
