# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['nurse_app.py',
     'assessment.py',
     'diagnosis.py',
     'record.py',
     'record_review.py',
     'careplan.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('nanda_db.xlsx', '.'),           # Excel DB を同梱
        ('app_settings.json', '.'),       # あれば
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False
)

# コンソールを出さないGUI実行
exe = EXE(
    a.pure, a.scripts, a.binaries, a.zipfiles, a.datas,
    name='nurse_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='nurse_app'
)
