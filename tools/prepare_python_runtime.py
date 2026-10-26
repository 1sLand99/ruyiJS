"""Freeze the current Windows runtime as the pinned Python wheel dependency."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import zipfile

from package_files import checksums, copy_file

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/python-package"
RUNTIME = BUILD / "runtime"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "python/ruyijs/_version.py").read_text(encoding="utf-8"))[1]
ARCHIVE = BUILD / f"ruyijs-runtime-{VERSION}-win-amd64.zip"
DIST = ("js.exe", "mozglue.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
IGNORE = {"__pycache__", ".pytest_cache", "tests", "test"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def include(path):
    return not IGNORE.intersection(path.parts) and path.suffix not in (".pyc", ".pyo", ".pyi")


def copy_tree(source, target):
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked runtime input: {path}")
        if path.is_file() and include(path.relative_to(source)):
            copy_file(path, target / path.relative_to(source))


def main():
    if RUNTIME.exists() or ARCHIVE.exists():
        raise FileExistsError("Use a fresh build/python-package runtime staging directory")
    RUNTIME.mkdir(parents=True)
    for name in DIST:
        copy_file(ROOT / "dist" / name, RUNTIME / "dist" / name)
    original = ROOT / "vendor/necko-derived/python"
    python = RUNTIME / "vendor/necko-derived/python"
    for path in original.iterdir():
        if path.is_file() and path.name != "python314._pth":
            copy_file(path, python / path.name)
    copy_tree(original / "DLLs", python / "DLLs")
    copy_tree(original / "Lib/site-packages", python / "Lib/site-packages")
    copy_file(ROOT / "dist/msvcp140.dll", python / "msvcp140.dll")
    (python / "python314._pth").write_text("python314.zip\nDLLs\nLib/site-packages\n.\n", encoding="ascii")
    with zipfile.ZipFile(python / "python314.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted((original / "Lib").rglob("*")):
            relative = path.relative_to(original / "Lib")
            if path.is_file() and relative.parts[0] != "site-packages" and include(relative):
                archive.write(path, relative.as_posix())
    for name in ("manifest.json", "base-manifest.json"):
        copy_file(ROOT / "vendor/necko-derived" / name, RUNTIME / "vendor/necko-derived" / name)
    copy_tree(ROOT / "vendor/necko-derived/licenses", RUNTIME / "licenses/necko-derived")
    for name in ("LICENSE", "toolkit/content/license.html"):
        copy_file(ROOT / "release/donor" / name, RUNTIME / "licenses/mozilla" / name)
    copy_file(ROOT / "release/donor/gfx/harfbuzz/COPYING", RUNTIME / "licenses/harfbuzz/COPYING")
    for name in ("LICENSE-APACHE", "LICENSE-MIT"):
        copy_file(ROOT / "src/web_platform/encoding_rs" / name, RUNTIME / "licenses/encoding_rs" / name)
    for name in ("LICENSE", "NOTICE"):
        copy_file(ROOT / name, RUNTIME / name)
    (RUNTIME / "SOURCE_NOTICE.md").write_text(
        "# Runtime sources\n\nThis bundle retains the current ruyijs/SpiderMonkey and Necko binaries.\n"
        f"Package: https://pypi.org/project/ruyijs/{VERSION}/\n"
        "Component license texts are in licenses/ and the embedded Python packages.\n"
        "SHA256SUMS describes this runtime; Necko manifests retain the original build identities.\n"
        "Rebuilding native components requires the donor and toolchain described in the repository.\n",
        encoding="utf-8")
    checksums(RUNTIME)
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(RUNTIME.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(RUNTIME).as_posix())
    api = "https://gitee.com/api/v5/repos/losenine888/ruyiJS/releases"
    manifest = {"version": VERSION, "archive": ARCHIVE.name, "sha256": digest(ARCHIVE),
                "size": ARCHIVE.stat().st_size, "unpacked_limit": 200 * 1024 * 1024,
                "shell_sha256": digest(RUNTIME / "dist/js.exe"),
                "inventory_sha256": digest(RUNTIME / "SHA256SUMS"),
                # The archive is not published; wheel builds pass RUYIJS_BUILD_RUNTIME_ARCHIVE.
                "url": "",
                "release_api": api + f"/tags/v{VERSION}", "releases_api": api}
    (ROOT / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
