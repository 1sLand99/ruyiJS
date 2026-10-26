# Windows x64 独立发布

在项目根目录执行：

```powershell
python -B tools/export_portable.py --output out-release
```

输出限项目根目录下的 `out` 或 `out-*`，同时生成同名 `.zip` 分发包和 `.sha256` 文件；
已有目录及归档均保留原样。
组装使用当前 `dist/`、Python 绑定和 Necko 私有运行组件，生成独立目录、
`source.zip`、许可证、来源记录和 `SHA256SUMS`。三个示例及使用说明均随运行包提供；
来源记录保留构建输入哈希，并将构建机器的绝对路径替换为便携别名。

| 文件 | 职责 |
| --- | --- |
| `export_portable.py` | 校验当前 EXE/C DLL/helper 身份，复制运行布局并触发检查 |
| `package_files.py` | 生产源码白名单、文件复制和 SHA256 清单 |
| `portable_sources.py` | 归档生产源码、派生源及原始来源记录 |
| `portable_verify.py` | 迁移目录、环境隔离、启动器与文件身份检查 |
| `portable_probe.py` | Python、状态、异常恢复、调度、资源和本地 HTTP/fetch |
| `package_probe.py` | 同一迁移目录内的真实 C ABI 调用 |

运行布局保留 `dist/`、`python/`、`vendor/` 同级：

- `dist/js.exe`、`ruyijs_client.dll`、`ruyijs_client.lib`、`include/ruyijs.h` 和运行库。
- `python/` 绑定以及启动用户脚本的 `_run.py`。
- `vendor/necko-derived/python/` 内置 Python、Necko、TLS/H2/压缩依赖及证书数据。
- Google、BOSS、网上房地产示例，保持原目录布局，另附 `examples/README.md`。
- 包根目录的 `google_search.cmd` 启动器；其它示例通过 `python.cmd` 运行。
- `licenses/`、`SOURCE_NOTICE.md`、`source.zip` 和精简交付证据。

Python 按自身位置发现 `dist/js.exe`；C 调用方传入包内 shell 的绝对 UTF-8 路径。
运行包不依赖 Firefox 浏览器、构建工具或开发目录中的 PATH。
导出时排除测试和字节码缓存，依赖组件及其许可证按现有运行布局保留。

源码归档使用生产白名单，排除测试、诊断、历史响应和临时产物。
`profiles/` 是生产配置与生成输入，包含 CSS/WebGL 表生成数据，不含浏览器用户资料。
构建报告读取 `artifacts/build-runtime.json`，派生源读取 `build/runtime/`，
两者均由 `tools/build.py` 生成，导出前须先完成一次构建。
源码包包含项目与派生源；重建仍需来源记录中匹配的完整 donor、对象树和工具链。
Mozilla、HarfBuzz、encoding_rs、CPython/Necko 和其它依赖的条款原文随包保留。

便携验证把整个包复制到临时中文空格目录，使用系统工作目录、仅含 Windows 的
PATH，并移除 Python/RUYIJS 环境覆盖。检查 CLI、包内 Python、C ABI、本地网络、
参数传递、本地模块导入和退出码；三个示例只运行 `--help`，不访问外网。
检查前后重新核对文件哈希，最终结果写入 `evidence/portable-verification.json`。

这些检查只说明本次交付可独立运行；不表示完整源码回归或全浏览器兼容性验收。
Google 实网耗时和成功率由单独实测报告描述。
