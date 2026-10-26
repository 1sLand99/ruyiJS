"""Archive current project sources and preserve historical binary provenance."""

import hashlib
import json
import re
import zipfile
from pathlib import Path

from package_files import source_files
from provenance import digest


_WINDOWS_PATH = re.compile(r"(?i)([a-z]:[\\/][^\\/\s\"',;]+(?:[\\/][^\\/\s\"',;]+)*)")


def _path_alias(value, root, report):
    candidate = Path(value)
    aliases = [(root.resolve(), "PROJECT")]
    for field, label in (("source", "DONOR_SOURCE"), ("donor", "DONOR_BUILD")):
        location = report.get(field)
        if location:
            aliases.append((Path(location), label))
    compiler = report.get("compiler")
    if isinstance(compiler, list) and compiler:
        aliases.append((Path(compiler[0]).parent.parent, "TOOLCHAIN"))
    for base, label in sorted(aliases, key=lambda item: len(str(item[0])), reverse=True):
        try:
            relative = candidate.relative_to(base)
        except ValueError:
            continue
        return label + "/" + relative.as_posix()
    return "LOCAL_PATH/" + candidate.name


def _sanitize_value(value, root, report):
    if isinstance(value, dict):
        return {_sanitize_value(key, root, report): _sanitize_value(item, root, report)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item, root, report) for item in value]
    if isinstance(value, str):
        return _WINDOWS_PATH.sub(lambda match: _path_alias(match.group(1), root, report), value)
    return value


def portable_report_json(root, report):
    sanitized = _sanitize_value(report, root, report)
    return json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n"


def build_report_path(root):
    current = root / "artifacts/build-runtime.json"
    return current if current.is_file() else root / "release/provenance/build-runtime.json"


def donor_file(root, report, name):
    original = Path(report["source"]) / name
    saved = root / "release/donor" / name
    path = original if original.is_file() else saved
    expected = next((item["sha256"] for item in report["inputs"]
                     if Path(item["path"]) == original), None)
    if expected and digest(path) != expected:
        raise ValueError(f"Donor source differs from recorded build: {name}")
    return path


def archive_sources(root, output, report):
    records = []
    with zipfile.ZipFile(output / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        def add(path, name):
            archive.write(path, name)
            records.append({"path": name, "sha256": digest(path), "size": path.stat().st_size})

        def add_text(text, name):
            data = text.encode("utf-8")
            archive.writestr(name, data)
            records.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                            "size": len(data)})

        for path in sorted(set(source_files(root))):
            add(path, "ruyijs/" + path.relative_to(root).as_posix())
        for name in ("js.cpp", "Unified_cpp_js_src_shell0.cpp", "runtime_assets.h",
                     "firefox_environment_profile.h"):
            path = root / "build/runtime" / name
            if not path.is_file():
                path = root / "release/derived" / name
            add(path, "derived/" + name)
        donor = Path(report["source"])
        for item in report["inputs"]:
            path = Path(item["path"])
            if path.suffix == ".cpp" and path.is_relative_to(donor / "js/src/shell"):
                name = path.relative_to(donor).as_posix()
                add(donor_file(root, report, name), "donor/" + name)
        for name in ("LICENSE", "toolkit/content/license.html"):
            add(donor_file(root, report, name), "donor/" + name)
        add_text(portable_report_json(root, report), "provenance/build-runtime.json")
        for name in ("manifest.json", "base-manifest.json"):
            add(root / "vendor/necko-derived" / name, "provenance/necko-derived/" + name)
        add(root / "vendor/necko/manifest.json", "provenance/necko-base/manifest.json")
        for name in ("donor-files.json", "necko-release-validation.json"):
            path = root / "release/provenance" / name
            if path.is_file():
                add(path, "provenance/" + name)
        archive.writestr("SOURCE_MANIFEST.json", json.dumps(records, indent=2))
    return {"files": len(records), "sha256": digest(output / "source.zip")}
