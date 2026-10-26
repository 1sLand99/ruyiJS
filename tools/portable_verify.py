"""Relocate and verify Python/C, local networking and packaged examples."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from provenance import digest


def clean_environment():
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PYTHON", "RUYIJS"))}
    windows = Path(env.get("SystemRoot") or env.get("SYSTEMROOT") or "C:/Windows")
    env["PATH"] = os.pathsep.join([str(windows / "System32"), str(windows)])
    return env, windows


def verify_hashes(package):
    package = package.resolve()
    records = {}
    for line in (package / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        value, name = line.split("  ", 1)
        path = (package / name).resolve()
        if not path.is_relative_to(package) or name in records:
            raise ValueError(f"Invalid checksum path: {name}")
        if digest(path) != value:
            raise ValueError(f"Checksum mismatch: {name}")
        records[name] = value
    actual = set()
    for path in package.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Package contains a link: {path}")
        if path.name.lower() in ("test", "tests", ".pytest_cache"):
            raise ValueError(f"Test directory in runtime package: {path}")
        if path.name == "__pycache__" or path.suffix.lower() in (".pyc", ".pyo", ".go", ".pdb", ".obj"):
            raise ValueError(f"Unexpected package file: {path}")
        if path.is_file() and path.name != "SHA256SUMS":
            actual.add(path.relative_to(package).as_posix())
    if actual != set(records):
        raise ValueError("Checksum manifest does not cover the exact package")
    return records


def run(command, cwd, env, expected=0):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode != expected:
        raise RuntimeError(f"Probe exit {result.returncode}: {command}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def batch(windows, script, *args):
    # These quoted paths and fixture arguments are created by this verifier.
    tail = " ".join('"' + str(arg) + '"' for arg in args)
    command = f'"{script}" {tail}'.rstrip()
    return f'"{windows / "System32/cmd.exe"}" /d /s /c "{command}"'


def verify(root, package):
    hashes = verify_hashes(package)
    with zipfile.ZipFile(package / "source.zip") as archive:
        names = archive.namelist()
        if archive.testzip() is not None:
            raise ValueError("Corrupt source archive")
        if any("/go/" in name.lower() or name.lower().endswith(".go") for name in names):
            raise ValueError("Go source found in archive")
        if any(set(name.lower().split("/")) & {"tests", "test", "artifacts", "tasks", "__pycache__"}
               for name in names):
            raise ValueError("Source archive includes tests, diagnostics or caches")
        for folder in ("src", "python", "tools", "docs", "transport", "examples"):
            if not any(name.startswith(f"ruyijs/{folder}/") for name in names):
                raise ValueError(f"Source archive missing {folder}")
        for name in ("ruyijs/examples/boss/boss.py",
                     "ruyijs/examples/google/google_search.py",
                     "ruyijs/examples/网上房地产/fangdi.py",
                     "ruyijs/examples/网上房地产/README.md"):
            if name not in names:
                raise ValueError(f"Source archive missing {name}")
        for name in ("derived/js.cpp", "provenance/build-runtime.json", "SOURCE_MANIFEST.json"):
            if name not in names:
                raise ValueError(f"Source archive missing {name}")
        provenance = archive.read("provenance/build-runtime.json").decode("utf-8")
        if re.search(r"(?i)[a-z]:[\\/]", provenance):
            raise ValueError("Build provenance contains a machine-local absolute path")
    provenance = (package / "evidence/build-runtime.json").read_text(encoding="utf-8")
    if re.search(r"(?i)[a-z]:[\\/]", provenance):
        raise ValueError("Package evidence contains a machine-local absolute path")
    env, windows = clean_environment()
    with tempfile.TemporaryDirectory(prefix="ruyijs-portable-") as temporary:
        temp = Path(temporary).resolve()
        relocated = temp / "迁移 验证" / "ruyijs out"
        relocated.parent.mkdir(parents=True)
        shutil.copytree(package, relocated)
        env["TEMP"] = env["TMP"] = str(temp)
        cli = json.loads(run([str(relocated / "dist/js.exe"), "--ruyijs-runtime", "-e", "40+2"], windows, env))
        assert cli["ok"] and cli["value"] == {"type": "number", "value": 42}, cli
        probe = temp / "probe.py"
        shutil.copy2(root / "tools/portable_probe.py", probe)
        python = relocated / "vendor/necko-derived/python/python.exe"
        result = json.loads(run([str(python), "-I", "-B", str(probe), str(relocated)], windows, env))
        native_probe = temp / "native_probe.py"
        shutil.copy2(root / "tools/package_probe.py", native_probe)
        native = json.loads(run([str(python), "-I", "-B", str(native_probe), str(relocated)], windows, env))
        assert native["c_abi"] == "passed", native
        assert run(batch(windows, relocated / "run.cmd"), windows, env) == "42"
        help_text = run(batch(windows, relocated / "google_search.cmd", "--help"), windows, env)
        assert "usage:" in help_text.lower(), help_text
        for relative in ("examples/boss/boss.py", "examples/网上房地产/fangdi.py"):
            help_text = run(batch(windows, relocated / "python.cmd",
                                  relocated / relative, "--help"), windows, env)
            assert "usage:" in help_text.lower(), (relative, help_text)
        script = temp / "用户 脚本.py"
        (temp / "local_helper.py").write_text("VALUE = 42\n", encoding="utf-8")
        script.write_text("import sys, local_helper\nfrom ruyijs import Context\n"
                          "assert len(sys.argv) == 3 and sys.argv[1:] == ['hello world', '中文参数']\n"
                          "with Context() as c: assert c.eval('6*7') == local_helper.VALUE\n"
                          "print('arguments-ok')\n", encoding="utf-8")
        assert run(batch(windows, relocated / "python.cmd", script, "hello world", "中文参数"), windows, env) == "arguments-ok"
        script.write_text("raise SystemExit(7)\n", encoding="utf-8")
        run(batch(windows, relocated / "python.cmd", script), windows, env, expected=7)
        run(batch(windows, relocated / "python.cmd"), windows, env, expected=1)
        if verify_hashes(relocated) != hashes:
            raise ValueError("Package changed during verification")
    if verify_hashes(package) != hashes:
        raise ValueError("Source package changed during verification")
    return {"created_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "existing-runtime-portability", "files_verified": len(hashes),
            "shell_sha256": hashes["dist/js.exe"], "source_zip_sha256": hashes["source.zip"],
            "client_sha256": hashes["dist/ruyijs_client.dll"],
            "relocated_path": "<temporary>/迁移 验证/ruyijs out", "cwd": str(windows),
            "environment": {"PATH": env["PATH"], "PYTHONPATH": None, "RUYIJS": None},
            "probe": result, "native_probe": native, "cli": "passed", "launcher": "passed",
            "google_search_launcher_help": "passed",
            "boss_launcher_help": "passed", "fangdi_launcher_help": "passed",
            "script_arguments_and_imports": "passed", "launcher_exit_codes": "passed",
            "package_unchanged_after_tests": True, "go": "absent"}


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parents[1]
    package = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "out"
    print(json.dumps(verify(root, package), ensure_ascii=True, indent=2))
