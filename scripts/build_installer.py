"""Build a deterministic, accounting-data-free HAT user archive."""

from __future__ import annotations

import hashlib
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ARCHIVE = DIST / "HAT-Installer-1.0.1.zip"
APP_FILES = ("pyproject.toml", "README.md")
SOURCE_DIRS = ("src", "config", "docs")
LAUNCHERS = (
    "README_USER.txt",
    "install.sh",
    "start.sh",
    "Установить HAT.cmd",
    "Запустить HAT.cmd",
)
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", "local_inputs", "runs", ".git"}


def copy_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def build() -> tuple[Path, str]:
    DIST.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hat-installer-") as temporary:
        bundle = Path(temporary) / "HAT"
        app = bundle / "app"
        app.mkdir(parents=True)
        for name in APP_FILES:
            shutil.copyfile(ROOT / name, app / name)
        for name in SOURCE_DIRS:
            copy_tree(ROOT / name, app / name)
        for name in LAUNCHERS:
            shutil.copyfile(ROOT / "packaging" / name, bundle / name)
        copy_tree(ROOT / "config", bundle / "config")
        for name in ("install.sh", "start.sh"):
            (bundle / name).chmod((bundle / name).stat().st_mode | stat.S_IXUSR)

        with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(bundle.rglob("*")):
                if not path.is_file():
                    continue
                relative = Path("HAT") / path.relative_to(bundle)
                info = zipfile.ZipInfo(str(relative).replace("\\", "/"), (2026, 8, 27, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
                archive.writestr(info, path.read_bytes(), compresslevel=9)
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    (DIST / f"{ARCHIVE.name}.sha256").write_text(f"{digest}  {ARCHIVE.name}\n")
    return ARCHIVE, digest


if __name__ == "__main__":
    archive, checksum = build()
    print(f"Created {archive.relative_to(ROOT)}")
    print(f"SHA256 {checksum}")
