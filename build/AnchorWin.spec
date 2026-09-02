# -*- mode: python ; coding: utf-8 -*-
# AnchorWin v1.0.3 build spec
#
# Hardening against Windows Defender false positives:
#  - onedir (COLLECT) instead of onefile: no self-extracting stub at runtime
#  - upx=False: UPX-packed PE binaries are a top heuristic trigger
#  - version_info: proper VS_VERSION_INFO resources (FileDescription,
#    ProductName, CompanyName, version) so the PE looks like a normal
#    application instead of an anonymous PyInstaller stub

block_cipher = None

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=[],
    datas=[('../icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AnchorWin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign=False,
    icon='../icon.ico',
    version='version.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='AnchorWin',
)
