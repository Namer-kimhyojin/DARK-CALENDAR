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
        ('AppxManifest.xml', '.'),
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
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
    excludes=['PyQt6.QtMultimedia', 'PyQt6.QtPdf', 'PyQt6.QtSvg'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# The app uses the native Windows notification sound and does not load PDF or
# SVG image plugins. Removing those optional plugins also removes FFmpeg and
# unrelated Qt modules from the distributed compliance surface.
_FORBIDDEN_QT_RUNTIME_FILES = {
    'qt6multimedia.dll',
    'qt6pdf.dll',
    'qt6svg.dll',
    'avcodec-61.dll',
    'avformat-61.dll',
    'avutil-59.dll',
    'swresample-5.dll',
    'swscale-8.dll',
    'ffmpegmediaplugin.dll',
    'qpdf.dll',
    'qsvg.dll',
    'qsvgicon.dll',
}
a.binaries = [
    item
    for item in a.binaries
    if str(item[0]).replace('\\', '/').rsplit('/', 1)[-1].lower()
    not in _FORBIDDEN_QT_RUNTIME_FILES
]
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
