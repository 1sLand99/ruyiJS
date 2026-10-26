"""Assemble a small, self-contained Windows x64 bundle for the three examples."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "vendor/necko-derived/python"
RUNTIME = (
    "js.exe", "mozglue.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll",
)
EXTENSIONS = (
    "_bz2.pyd", "_ctypes.pyd", "_hashlib.pyd", "_lzma.pyd", "_queue.pyd",
    "_socket.pyd", "_ssl.pyd", "_uuid.pyd", "_zstd.pyd", "select.pyd",
    "unicodedata.pyd", "libcrypto-3.dll", "libssl-3.dll", "libffi-8.dll",
)
PACKAGES = (
    "brotli.py", "_brotli.cp314-win_amd64.pyd", "_cffi_backend.cp314-win_amd64.pyd",
    "certifi", "charset_normalizer", "cryptography", "h2", "hpack", "hyperframe",
    "idna", "necko", "publicsuffixlist", "requests", "ruyijs_necko", "urllib3",
)
UNUSED_STDLIB = {
    "__phello__", "__hello__.py", "antigravity.py", "asyncio", "concurrent",
    "curses", "dbm", "ensurepip", "idlelib", "multiprocessing", "pydoc_data",
    "site-packages", "sqlite3", "test", "tkinter", "turtledemo", "unittest",
    "venv", "wsgiref", "xml", "xmlrpc", "_pyrepl", "turtle.py", "pydoc.py",
    "pdb.py", "doctest.py", "compileall.py", "py_compile.py", "modulefinder.py",
    "tabnanny.py", "trace.py", "profile.py", "cProfile.py", "pstats.py",
}
SKIP = {"__pycache__", "test", "tests", ".pytest_cache"}
README = """# examples 精简运行包

Windows 10/11 x64，已内置 Python 3.14 和运行依赖，无需 pip 安装。
整个目录可复制到其他位置，请保持内部目录结构。

在本目录打开 PowerShell：

```powershell
.\\google_search.cmd --query python --pages 1
.\\python.cmd .\\examples\\boss\\boss.py --query ai --city 101210100
.\\python.cmd \".\\examples\\网上房地产\\fangdi.py\"
```

每个命令加 `--help` 查看参数；可用 `--proxy http://127.0.0.1:7890` 指定代理，
或 `--direct` 直连。实站结果取决于网络、代理和站点响应。

此包面向这三个示例：标准库压缩在 `vendor/necko-derived/python/python314.zip`，
保留引擎、Python 绑定、HTTP/TLS/H2/H3、证书、域名后缀和压缩组件。
省去了 C ABI、开发工具、源码归档、测试、缓存及示例未使用的 Python 组件。
`verification.json` 记录本包实际完成的检查，`SHA256SUMS` 记录文件哈希。

项目源码与许可说明：https://github.com/LoseNine/ruyijs
完整本地源码在原项目目录，组件许可文本保留在 `licenses/` 和组件目录。
"""


def include(path):
    return (not (set(path.parts) & SKIP)
            and not any(part.endswith(".dist-info") for part in path.parts)
            and path.suffix.lower() not in {".pyc", ".pyo", ".pyi"}
            and path.name not in {"py.typed", "quic-build.json", "firefox-profile.json"}
            and not ("charset_normalizer" in path.parts and path.suffix == ".pyd"))


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_tree(source, target):
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked input: {path}")
        if path.is_file() and include(Path(source.name) / relative):
            copy(path, target / relative)


def checksums(output):
    records = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            with path.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
            records.append(f"{sha}  {path.relative_to(output).as_posix()}\n")
    (output / "SHA256SUMS").write_text("".join(records), encoding="utf-8")


def assemble(output):
    output = output.resolve()
    if output.parent != ROOT or output.name != "result":
        raise ValueError("Output must be the project's result directory")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output is not empty: {output}")
    output.mkdir(exist_ok=True)
    for name in RUNTIME:
        copy(ROOT / "dist" / name, output / "dist" / name)
    copy_tree(ROOT / "python/ruyijs", output / "python/ruyijs")
    copy_tree(ROOT / "examples", output / "examples")
    for name in ("python.cmd", "google_search.cmd", "_run.py"):
        target = "python/_run.py" if name == "_run.py" else name
        copy(ROOT / "tools/portable" / name, output / target)
    python = output / "vendor/necko-derived/python"
    for name in ("python.exe", "python3.dll", "python314.dll", "LICENSE.txt"):
        copy(PYTHON / name, python / name)
    for name in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        copy(ROOT / "dist" / name, python / name)
    for name in EXTENSIONS:
        copy(PYTHON / "DLLs" / name, python / "DLLs" / name)
    (python / "python314._pth").write_text(
        "python314.zip\nDLLs\nLib/site-packages\n.\n", encoding="ascii")
    with zipfile.ZipFile(python / "python314.zip", "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for path in sorted((PYTHON / "Lib").rglob("*.py")):
            relative = path.relative_to(PYTHON / "Lib")
            if relative.parts[0] not in UNUSED_STDLIB and include(relative):
                archive.write(path, relative.as_posix())
    for name in PACKAGES:
        source, target = PYTHON / "Lib/site-packages" / name, python / "Lib/site-packages" / name
        (copy_tree if source.is_dir() else copy)(source, target)
    copy_tree(ROOT / "vendor/necko-derived/licenses", output / "licenses/necko-derived")
    copy(ROOT / "release/donor/LICENSE", output / "licenses/mozilla/LICENSE")
    copy(ROOT / "release/donor/gfx/harfbuzz/COPYING", output / "licenses/harfbuzz/COPYING")
    for name in ("LICENSE-APACHE", "LICENSE-MIT"):
        copy(ROOT / "src/web_platform/encoding_rs" / name, output / "licenses/encoding_rs" / name)
    for name in ("LICENSE", "NOTICE"):
        copy(ROOT / name, output / name)
    (output / "README.md").write_text(README, encoding="utf-8")
    checksums(output)
    files = [p for p in output.rglob("*") if p.is_file()]
    return {"output": str(output), "files": len(files), "bytes": sum(p.stat().st_size for p in files)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "result")
    args = parser.parse_args()
    print(json.dumps(assemble(args.output), ensure_ascii=True, indent=2))
