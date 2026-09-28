from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

studio_root = Path(SPECPATH)
repository_root = studio_root.parent

a = Analysis(
    [str(studio_root / "desktop_entry.py")],
    pathex=[str(studio_root), str(repository_root)],
    binaries=[],
    datas=[(str(studio_root / "static"), "static"), (str(studio_root / "examples"), "examples")],
    hiddenimports=collect_submodules("webview") + collect_submodules("studio.desktop"),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["pytest", "uvicorn", "fastapi", "app", "polo_line"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PoloSimulator",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
               upx_exclude=[], name="PoloSimulator")
