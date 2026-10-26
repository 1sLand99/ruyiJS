# ruyijs 构建与发布工具

从项目根目录查看构建参数：

```powershell
python -B tools/build.py --help
```

实际重建需要匹配的 Windows x64 SpiderMonkey standalone donor、完整对象树、
LLVM、MSVC/Windows SDK 和 CRT。工具只读取 donor，在本项目生成输出。
可用以下参数指定本机路径：

```powershell
python -B tools/build.py `
  --donor-obj "<firefox>/obj-js-standalone" `
  --toolchain-bin "<LLVM>/bin" `
  --firefox-font-prefs "<firefox>/obj-browser/dist/bin/greprefs.js"
```

如 donor 配置里的 VS/SDK 或 redistributable 路径在本机不同，使用 `--vs-root` 和
`--runtime-dll-dir` 显式指定。实际工具版本、输入哈希和命令写入本次构建记录。
`--prepare-only` 只准备输入；`--pristine` 仅重新链接 donor shell；
`--jobs` 指定 1–16 个编译进程，默认 4。清理对象后使用普通构建，
`--reuse-objects` 只适用于保留了完整且匹配的对象文件的工作目录。

| 文件 | 职责 |
| --- | --- |
| `build.py` | 构建编排、输入身份和产物版本检查 |
| `donor.py` | 读取 donor 配置、对象列表和库路径 |
| `generate.py` | 生成保留原许可头的 shell 单元和内嵌资源 |
| `native.py` | 调用编译器/链接器，部署运行库 |
| `client.py` | 构建 C ABI DLL、导入库和公开头文件 |
| `geometry_fonts.py` | 生成字体配置和 HarfBuzz 编译输入 |
| `product_sources.py` | 唯一生产源码清单、profile 和领域编译边界 |
| `provenance.py` | SHA256、thin archive 成员及输入身份复验 |
| `export_portable.py` | 组装当前产物并验证可迁移运行 |
| `portable_sources.py` / `package_files.py` | 生产源码白名单、源码归档和校验清单 |
| `portable_verify.py` / `portable_probe.py` / `package_probe.py` | 独立目录内的 Python/C、启动器和本地网络检查 |

正常构建产生 `dist/js.exe`、`dist/ruyijs_client.dll`、导入库和头文件，
并部署唯一生产 `src/resource_network/necko_oneshot.py` 到内置 Necko Python。
`build/runtime/` 保存派生源、对象、PDB 和日志；
`artifacts/build-runtime.json` 保存本次构建输入与产物身份。
这些目录由构建重新创建，发布清理不影响生产源文件。

`js_static.lib` 等 thin archive 引用 donor 对象树中的外部成员，
仅复制 `.lib` 不构成完整重建环境。源代码归档记录外部来源，
并保留生产表、构建工具及必要派生源；运行便携包无需 donor 或编译器。
`profiles/` 是生产配置和生成数据，不是浏览器用户资料目录。
`profiles/generation/` 保存 CSS/WebGL 表生成器的只读输入；
正常编译使用已经生成的生产源码，重新生成表时可先运行相应工具的 `--help`。

独立发布入口：

```powershell
python -B tools/export_portable.py --output out-release
```

输出目录须尚未存在；详细布局、来源及验证范围见 [PACKAGING.md](PACKAGING.md)。
当前发布检查验证已有产物的便携运行，未包含已移除的历史测试套件。
Google 脚本入口为包内 `google_search.cmd`，可执行 `--help` 查看参数。
