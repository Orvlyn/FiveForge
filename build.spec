# -*- mode: python ; coding: utf-8 -*-
#
# FiveForge — PyInstaller build spec
# Run:  pyinstaller build.spec --clean
#       or use build.ps1
#

from pathlib import Path

block_cipher = None

# Only include native/ and assets/ if they exist
datas = [("ui/styles", "ui/styles")]
if Path("native").exists():
    datas.append(("native", "native"))
if Path("assets").exists():
    datas.append(("assets", "assets"))

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "clr",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pytest",
        "jupyter",
        "notebook",
        "IPython",
        "pip",
        "setuptools",
        "wheel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtWebSockets",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtRemoteObjects",
        "PySide6.QtTest",
        "PySide6.QtSql",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PIL.AvifImagePlugin",
        "PIL.BlpImagePlugin",
        "PIL.BufrStubImagePlugin",
        "PIL.CurImagePlugin",
        "PIL.FitsImagePlugin",
        "PIL.GribStubImagePlugin",
        "PIL.Hdf5StubImagePlugin",
        "PIL.IcnsImagePlugin",
        "PIL.MpegImagePlugin",
        "PIL.PalmImagePlugin",
        "PIL.PdfImagePlugin",
        "PIL.PixarImagePlugin",
        "PIL.WebPImagePlugin",
        "PIL.WmfImagePlugin",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FiveForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/fiveforge.ico",
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["CodeWalker*.dll"],
    name="FiveForge",
)
