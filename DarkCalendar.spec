# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('Assets', 'Assets'),
        ('locales', 'locales'),
        ('AppxManifest.xml', '.'),
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
    ] + collect_data_files('tzdata'),
    hiddenimports=[
        'calendar_app',
        'calendar_app.bootstrap',
        'calendar_app.presentation.main_window.app_window',
        'calendar_app.infrastructure.runtime.crash_bootstrap',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6.Qt6.qml', 'PyQt6.Qt6.network', 'PyQt6.Qt6.sql', 'PyQt6.Qt6.test', 'PyQt6.Qt6.xml'],
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
    name='DarkCalendar',
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
    icon=['app_icon.ico'],
    version='version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DarkCalendar',
)
