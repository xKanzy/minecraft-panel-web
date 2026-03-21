# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# Используем текущую рабочую директорию вместо __file__
project_path = os.getcwd()

a = Analysis(
    ['app.py'],
    pathex=[project_path],
    binaries=[],
    datas=[
        (os.path.join(project_path, 'templates'), 'templates'),
        (os.path.join(project_path, 'static'), 'static'),
        (os.path.join(project_path, 'translations.py'), '.'),
        (os.path.join(project_path, 'config_manager.py'), '.'),
        (os.path.join(project_path, 'server_manager.py'), '.'),
        (os.path.join(project_path, 'backup_manager.py'), '.'),
        (os.path.join(project_path, 'plugin_manager.py'), '.'),
        (os.path.join(project_path, 'stats_collector.py'), '.'),
    ],
    hiddenimports=[
        'psutil',
        'psutil._psutil_windows',
        'psutil._psutil_linux',
        'requests',
        'flask',
        'jinja2',
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.utils',
        'werkzeug.wsgi',
        'jinja2.ext',
        'babel',
        'babel.support',
        'pkg_resources',
        'pkg_resources.py2_warn',
        'queue',
        'threading',
        'time',
        'json',
    ],
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
    icon='icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)