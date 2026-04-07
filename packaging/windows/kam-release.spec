# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd().resolve()
hiddenimports: list[str] = []
for package_name in (
    "api",
    "adapters",
    "services",
    "aiosqlite",
    "uvicorn",
    "watchfiles",
    "websockets",
    "anyio",
    "alembic",
    "sqlalchemy.dialects.sqlite",
):
    hiddenimports += collect_submodules(package_name)

datas = [
    (str(ROOT / "app" / "dist"), "app/dist"),
    (str(ROOT / "backend" / "alembic"), "backend/alembic"),
    (str(ROOT / "backend" / "alembic.ini"), "backend"),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "packaging" / "windows" / "README.txt"), "."),
]

a = Analysis(
    [str(ROOT / "backend" / "release_launcher.py")],
    pathex=[str(ROOT), str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="KAM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KAM",
)
