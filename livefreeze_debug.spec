import sys
from pathlib import Path

block_cipher = None

datas = [
    ('protocols', 'protocols'),
    ('RpiBeh_repo', 'RpiBeh_repo'),
    ('shock.py', '.'),
]

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
    for name in ('icuuc.dll', 'icudt73.dll'):
        candidate = env_root / 'Library' / 'bin' / name
        if candidate.is_file():
            out.append((str(candidate), '.'))
            out.append((str(candidate), 'PySide6'))
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='livefreeze_debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name='livefreeze_debug',
)
