# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('Assets', 'Assets'),
        ('locales', 'locales'),
        ('desk_calendar_default.db', '.'),
        ('LICENSE', '.'),
        ('README.md', '.'),
        ('SOURCE_OFFER.md', '.'),
        ('THIRD_PARTY_NOTICES.md', '.'),
    ] + collect_data_files('tzdata')
    + copy_metadata('PyQt6')
    + copy_metadata('PyQt6-Qt6')
    + copy_metadata('PyQt6-sip')
    + copy_metadata('QtAwesome'),
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DarkCalendar_Standalone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.ico'],
    version='version_info.txt',
)
