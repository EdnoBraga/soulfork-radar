# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec do SoulFork Radar (build Windows, modo onedir)

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('prospector/web/templates', 'prospector/web/templates'),
        ('nichos.json', '.'),
        ('LEIA-ME.md', '.'),
    ],
    hiddenimports=[],
    excludes=['tkinter', 'test', 'unittest', 'pydoc_data'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SoulForkRadar',
    icon='build_win/radar.ico',
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='SoulForkRadar', upx=False)
