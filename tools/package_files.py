"""Enumerate release sources and write exact package integrity manifests."""

import shutil
import zipfile

from provenance import digest


BUILD_TOOLS = frozenset("""
build.py client.py donor.py generate.py geometry_fonts.py binding_order.py native.py
product_sources.py provenance.py generate_cookie_suffixes.py
generate_css_properties.py generate_webgl_surface.py prepare_necko_bytecode.py
export_portable.py portable_sources.py portable_verify.py portable_probe.py
package_probe.py package_files.py README.md PACKAGING.md
""".split())
EXCLUDED = frozenset({"__pycache__", ".pytest_cache", ".git", "tests", "test"})
BINARY_SUFFIXES = frozenset({".pyc", ".pyo", ".exe", ".dll", ".pyd", ".obj", ".pdb", ".lib"})


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def source_files(root):
    for name in ("src", "python", "docs", "profiles", "transport", "vendor/necko-native"):
        for path in sorted((root / name).rglob("*")):
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"Linked source input: {path}")
            if (path.is_file() and not EXCLUDED.intersection(path.relative_to(root).parts)
                    and path.suffix.lower() not in BINARY_SUFFIXES):
                yield path
    for name in sorted(BUILD_TOOLS):
        path = root / "tools" / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing release tool: {path}")
        yield path
    for path in sorted((root / "tools/portable").iterdir()):
        if path.is_file():
            yield path
    for name in ("README.md", "README.zh-CN.md", "LICENSE", "NOTICE", "ARCHITECTURE.md", ".gitignore",
                 "examples/README.md", "examples/boss/boss.py",
                 "examples/google/google_search.py", "examples/网上房地产/fangdi.py",
                 "examples/网上房地产/README.md", "release/README.md"):
        yield root / name


def checksums(directory):
    records = [{"path": path.relative_to(directory).as_posix(), "sha256": digest(path),
                "size": path.stat().st_size} for path in sorted(directory.rglob("*"))
               if path.is_file() and path.name != "SHA256SUMS"]
    content = "".join(f"{item['sha256']}  {item['path']}\n" for item in records)
    (directory / "SHA256SUMS").write_text(content, encoding="utf-8")
    return records


def zip_directory(directory, output):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, directory.name + "/" + path.relative_to(directory).as_posix())
