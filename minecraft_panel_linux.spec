# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('translations.py', '.'),
        ('config_manager.py', '.'),
        ('server_manager.py', '.'),
        ('backup_manager.py', '.'),
        ('plugin_manager.py', '.'),
        ('stats_collector.py', '.'),
    ],
    hiddenimports=['psutil', 'requests', 'flask', 'jinja2', 'werkzeug', 'babel', 'pkg_resources', 'jinja2.ext.i18n', 'flask_babel'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='minecraft_panel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)