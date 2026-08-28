from pathlib import Path


project_root = Path(SPECPATH).parent

analysis = Analysis(
    [str(project_root / "packaging" / "wpt_manager_entry.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "LICENSE"), "."),
        (str(project_root / "README.md"), "."),
        (
            str(project_root / "data" / "config.example.json"),
            "data",
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="WPT-Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WPT-Manager",
)
