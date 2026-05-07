# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['monitor.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'sqlite3',
        'tkinter',
        'tkinter.ttk',
        'tkinter.font',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'langchain',
        'langgraph',
        'pystray',
        'PIL',
        'watchdog',
        'google',
        'yaml',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BrinerMonitor',
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BrinerMonitor',
)
