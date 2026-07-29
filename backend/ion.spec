# PyInstaller one-folder definition for ION 0.2+.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
hidden = (
    collect_submodules("webview")
    + collect_submodules("uvicorn")
    + collect_submodules("sqlalchemy.dialects.sqlite")
)

a = Analysis(
    [str(root / "backend" / "ion_entry.py")],
    pathex=[str(root / "backend" / "src")],
    binaries=[],
    datas=[
        (str(root / "frontend" / "dist"), "frontend/dist"),
        (str(root / "backend" / "migrations"), "backend/migrations"),
        (str(root / "backend" / "alembic.ini"), "backend"),
        (str(root / "assets"), "assets"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ION",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "assets" / "ion.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ION",
)
