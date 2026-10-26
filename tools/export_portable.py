"""Export the current Python/C runtime and verify its portable layout."""

import argparse
import json
import shutil
from pathlib import Path

from package_files import checksums, copy_file, zip_directory
from portable_sources import archive_sources, build_report_path, donor_file, portable_report_json
from portable_verify import verify, verify_hashes
from provenance import digest

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".git",
                                "test", "tests", "test_*", "*_test.py",
                                "_test*.pyd", "_ctypes_test.pyd")
RUNTIME_FILES = (
    "js.exe", "mozglue.dll", "msvcp140.dll", "msvcp140_atomic_wait.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll",
    "ruyijs_client.dll", "ruyijs_client.lib", "include/ruyijs.h",
)


def copy_tree(source, target):
    for path in [source, *source.rglob("*")]:
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked package input: {path}")
    shutil.copytree(source, target, ignore=IGNORE)


def assemble(output):
    output = output.resolve()
    if output.parent != ROOT or not (output.name == "out" or output.name.startswith("out-")):
        raise ValueError("Output must be out or out-* directly under the project")
    if output.exists():
        raise FileExistsError(f"Output already exists; use a new --output out-NAME: {output}")
    archive_path = output.with_suffix(".zip")
    checksum_path = Path(str(archive_path) + ".sha256")
    if archive_path.exists() or checksum_path.exists():
        raise FileExistsError(f"Archive output already exists: {archive_path}")
    report_path = build_report_path(ROOT)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "built" or report.get("mode") != "runtime":
        raise ValueError("Expected an existing runtime build report")
    if digest(ROOT / "dist/js.exe") != report["sha256"]:
        raise ValueError("Shell differs from the historical build identity")
    if digest(ROOT / "dist/ruyijs_client.dll") != report["client"]["sha256"]:
        raise ValueError("C client differs from the recorded build identity")
    if digest(ROOT / "dist/include/ruyijs.h") != digest(ROOT / "src/client/ruyijs.h"):
        raise ValueError("Published C header differs from the production source")
    helper = ROOT / "vendor/necko-derived/python/Lib/site-packages/ruyijs_necko/oneshot.py"
    if digest(helper) != report["networkHelper"]["sha256"]:
        raise ValueError("Network helper differs from the recorded build identity")
    output.mkdir()
    for name in RUNTIME_FILES:
        copy_file(ROOT / "dist" / name, output / "dist" / name)
    copy_tree(ROOT / "python", output / "python")
    copy_tree(ROOT / "vendor/necko-derived/python", output / "vendor/necko-derived/python")
    copy_file(ROOT / "vendor/necko-derived/manifest.json", output / "vendor/necko-derived/manifest.json")
    copy_file(ROOT / "vendor/necko-derived/base-manifest.json", output / "vendor/necko-derived/base-manifest.json")
    inventory = ROOT / "vendor/necko-derived/release-files.json"
    if inventory.is_file():
        copy_file(inventory, output / "evidence/necko-release-files.json")
    copy_tree(ROOT / "vendor/necko-derived/licenses", output / "licenses/necko-derived")
    (output / "evidence").mkdir(parents=True, exist_ok=True)
    (output / "evidence/build-runtime.json").write_text(
        portable_report_json(ROOT, report), encoding="utf-8")
    donor = Path(report["source"])
    for name in ("LICENSE", "toolkit/content/license.html"):
        copy_file(donor_file(ROOT, report, name), output / "licenses/mozilla" / name)
    for name in ("LICENSE-APACHE", "LICENSE-MIT"):
        copy_file(ROOT / "src/web_platform/encoding_rs" / name,
                  output / "licenses/encoding_rs" / name)
    harfbuzz = ROOT / "release/donor/gfx/harfbuzz"
    if not harfbuzz.is_dir():
        harfbuzz = donor / "gfx/harfbuzz"
    for path in harfbuzz.glob("COPYING*"):
        copy_file(path, output / "licenses/harfbuzz" / path.name)
    for name in ("README.md", "boss/boss.py", "google/google_search.py",
                 "网上房地产/fangdi.py", "网上房地产/README.md"):
        copy_file(ROOT / "examples" / name, output / "examples" / name)
    for path in (ROOT / "tools/portable").iterdir():
        if path.is_file():
            destination = output / "python/_run.py" if path.name == "_run.py" else output / path.name
            copy_file(path, destination)
    (output / ".ruyijs-portable").write_text("Python and C portable runtime\n", encoding="utf-8")
    source = archive_sources(ROOT, output, report)
    checksums(output)
    evidence = verify(ROOT, output)
    target = output / "evidence/portable-verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records = checksums(output)
    verify_hashes(output)
    zip_directory(output, archive_path)
    archive_sha256 = digest(archive_path)
    checksum_path.write_text(f"{archive_sha256}  {archive_path.name}\n", encoding="ascii")
    return {"output": str(output), "archive": str(archive_path),
            "archive_sha256": archive_sha256, "checksum_file": str(checksum_path),
            "files": len(records) + 1,
            "bytes": sum(item["size"] for item in records) + (output / "SHA256SUMS").stat().st_size,
            "source_zip_sha256": source["sha256"], "shell_sha256": digest(output / "dist/js.exe"),
            "client_sha256": digest(output / "dist/ruyijs_client.dll"),
            "verification": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "out")
    args = parser.parse_args()
    print(json.dumps(assemble(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
