# ruyijs Windows x64 便携包

适用 Windows x64。复制整个目录即可使用，已附带 Python 3.14 和运行依赖。

在此目录打开 PowerShell，运行示例：

```powershell
.\run.cmd
```

输出 `42`。运行自己的 Python 脚本：

```powershell
.\python.cmd "D:\work\hello.py"
```

脚本直接导入 Python 绑定，后续命令行参数也会传给脚本：

```python
from ruyijs import Context

with Context() as context:
    context.eval("globalThis.count = 40")
    print(context.eval("count += 2"))
```

也可使用已安装的 Python，将本目录下 `python` 的绝对路径加入 `sys.path`，
再执行上述代码。此时第三方 Python 包由自己的 Python 环境管理。

CLI 调用：

```powershell
.\dist\js.exe --ruyijs-runtime -e "40+2"
```

`dist/`、`python/`、`vendor/` 必须一起移动并保持目录结构。
`vendor` 包含实际网络请求所需的运行组件。

Google 搜索翻页示例（ruyijs 计算 SG_SS，Necko 发请求，带完整指纹替换）：

```powershell
.\google_search.cmd --help
.\google_search.cmd --query python --pages 3 --proxy http://127.0.0.1:7890
```

示例是单个文件 `examples/google/google_search.py`；指纹内置（`--region hk|us`），
`--dump-profile my.json` 导出后编辑，再用 `--profile my.json` 运行；`--json` 输出完整 JSON。

房地产和 BOSS 示例：

```powershell
.\python.cmd ".\examples\网上房地产\fangdi.py" --proxy http://127.0.0.1:7890
.\python.cmd ".\examples\boss\boss.py" --query ai --city 101210100 --proxy http://127.0.0.1:7890
```

房地产示例会运行站点挑战并验证首页；BOSS 示例会搜索职位并读取首条详情。
参数和结果字段见 `examples/网上房地产/README.md` 以及各脚本的 `--help`。

C 接口文件为 `dist/ruyijs_client.dll`、`dist/ruyijs_client.lib` 和
`dist/include/ruyijs.h`。调用时传入包内 `dist/js.exe` 的绝对 UTF-8 路径。

生产源码、构建/发布工具和详细 API 说明在 `source.zip`，第三方许可证在 `licenses/`。
源代码归档不携带测试、历史实网响应、运行日志或临时产物。
`SHA256SUMS` 用于核对文件；`evidence/portable-verification.json` 记录本包实际检查结果。
验证覆盖 Python/C 调用、状态、异常恢复、定时器、资源、本地 HTTP/fetch 和 Google 入口帮助。
Google 实网成功率与耗时不属于便携检查范围。
现有浏览器 API 支持范围见源码中的 README 与 docs/DEVIATIONS.md。
