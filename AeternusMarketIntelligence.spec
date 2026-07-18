# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = [
    'flask', 'flask_cors', 'yfinance', 'pandas', 'numpy', 'requests',
    'multitasking', 'lxml', 'lxml.etree', 'bs4', 'appdirs', 'frozendict',
    'peewee', 'werkzeug', 'werkzeug.serving', 'jinja2', 'click',
    'charset_normalizer', 'certifi', 'urllib3', 'research_agent',
    'research_tools', 'pydantic_core', 'pandas.core.arrays.masked',
    'pandas.core.arrays.integer', 'pandas.core.arrays.floating',
]
hiddenimports += collect_submodules('openai')


a = Analysis(
    ['backend\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend', 'frontend'), ('backend\\app.py', 'backend')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'sklearn', 'tkinter', 'IPython',
        'pytest', '_pytest', 'hypothesis', 'mypy',
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
    name='AeternusMarketIntelligence',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='AeternusMarketIntelligence',
)
