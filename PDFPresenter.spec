# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

app_version = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version']
version_tuple = tuple(int(part) for part in app_version.split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                     mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('041904B0', [
        StringStruct('FileDescription', 'Сцена — презентации, изображения и видео'),
        StringStruct('FileVersion', app_version), StringStruct('ProductName', 'Сцена'),
        StringStruct('ProductVersion', app_version),
        StringStruct('OriginalFilename', 'PDFPresenter.exe'),
    ])]), VarFileInfo([VarStruct('Translation', [1049, 1200])])],
)

# Keep unrelated tools (e.g. Poppler/Conda ICU builds) out of DLL resolution.
# This changes only the build process environment, never the user's Windows PATH.
if sys.platform == 'win32':
    windows = Path(os.environ['SystemRoot'])
    os.environ['PATH'] = os.pathsep.join([
        str(Path(sys.executable).parent), str(Path(sys.base_prefix)),
        str(windows / 'System32'), str(windows),
    ])

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=collect_data_files('pymupdf') + collect_data_files(
        'pdf_presenter', includes=['resources/icons/*.ico', 'resources/icons/*.png', 'resources/icons/*.svg', 'resources/*.js', 'resources/locales/*.json']),
    hiddenimports=['pythoncom', 'pywintypes', 'win32com.client', 'win32com.server',
                   'win32api', 'win32gui', 'win32process', 'win32event', 'win32job', 'win32ui',
                   'webview.platforms.winforms', 'webview.platforms.edgechromium', 'clr'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtWebEngineQuick', 'PySide6.QtQml', 'PySide6.QtQuick',
              'webview.platforms.qt', 'webview.platforms.cef', 'webview.platforms.gtk',
              'webview.platforms.cocoa', 'webview.platforms.android',
              'imageio_ffmpeg', 'pytest', 'ruff'],
    noarchive=False,
)
# Official recent Qt Windows wheels import the OS ICU API (unversioned exports).
# An unrelated icuuc.dll from PATH has incompatible, version-suffixed exports.
# Windows provides this DLL; do not redistribute or shadow it.
if sys.platform == 'win32':
    a.binaries = [entry for entry in a.binaries
                  if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icuin.dll'}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='PDFPresenter',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon='src/pdf_presenter/resources/icons/scene.ico',
    version=version_info,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PDFPresenter')
