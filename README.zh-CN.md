<div align="center">

# 🦊 ruyiJS

**新一代、专为 AI 驱动打造的极简浏览器 —— 基于 Firefox 架构，使用原生的 Firefox JavaScript 引擎与网络栈构建。**

专为特定场景打造：**网页抓取、JS 逆向、数据采集，以及绕过人机验证** —— 全程在 Python 中完成，无需浏览器窗口。

[![PyPI](https://img.shields.io/pypi/v/ruyijs?style=flat-square&color=3775A9&logo=pypi&logoColor=white)](https://pypi.org/project/ruyijs/)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.10-3776AB?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/ruyijs/)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078D4?style=flat-square&logo=windows&logoColor=white)](https://pypi.org/project/ruyijs/)
[![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)](./LICENSE)

[English](./README.md) · **简体中文**

[快速开始](#-快速开始) · [功能特性](#-功能特性) · [攻克的验证系统](#-攻克的验证系统) · [使用方法](#-使用方法) · [运行示例](#-运行示例) · [架构](#-架构)

</div>

---

```python
from ruyijs import Context

with Context() as context:
    context.eval("let count = 40")
    print(context.eval("count += 2"))        # 42
    print(context.eval("navigator.userAgent"))
```

## 🎯 为什么是 ruyiJS

Headless Chrome 和 Playwright 给你的是一整个浏览器 —— 一个负责 GPU 渲染、管理窗口、吃内存的进程，而反爬厂商已经花了多年时间学习如何识别它。ruyiJS 走的是相反的路：它只嵌入与自动化真正相关的 **Firefox 原生内核** —— **SpiderMonkey** JavaScript 引擎与 **Necko** 网络栈（HTTP/1.1、HTTP/2、HTTP/3）—— 其余一概不要。

由此得到的运行环境会像 Firefox 一样**原样执行**站点的 JavaScript、challenge、签名与指纹，却是一个轻量、可脚本化的 Python 库，不留下任何窗口与布局引擎。每个 `Context` 都是独立进程，拥有持续保存的 JavaScript 世界和自己的代理，因此会话彼此隔离、可复现。

## ✨ 功能特性

- 🦊 **原生 Firefox 内核** —— 货真价实的 SpiderMonkey 引擎（Firefox 158）与 Necko 网络传输，而非重新实现或打补丁。
- 🪶 **真正无头** —— 没有窗口、没有渲染、没有布局引擎。纯 JavaScript + Web API 环境，启动快、占用低。
- 🧩 **38 个受限上下文（bounded context）** —— DOM、Navigator、Screen、Storage、Canvas/WebGL、Worker、Service Worker、iframe、Performance、Intl、Permissions 等。
- 🧬 **可配置指纹 / 环境** —— 通过一套带校验的配置接口设置 Navigator、Screen、视口、时区与区域。
- ⏱️ **确定性时钟与事件循环** —— 用逻辑时钟驱动定时器以获得可复现运行，或用系统时钟进行实时作业。
- 🌐 **基于 Necko 的原生 `fetch` / XHR** —— 真实的 HTTP/1.1、HTTP/2、HTTP/3，支持**按上下文独立代理**。
- 📴 **离线回放** —— 用 `put_resource()` 提供脚本与响应，无网络也能复跑已捕获的流程。
- 🔁 **Python ↔ JS 互通** —— 用 `set()` 传入数据、从 Python 调用 JS 函数、把 Python 回调暴露给 JavaScript。
- 📦 **开箱即用** —— wheel 内置 SHA256 锁定的原生运行时；`pip install` 之后本地脚本可完全离线运行。

## 🛡️ 攻克的验证系统

ruyiJS 附带可直接运行、闭环验证的示例，覆盖真实世界的反爬与验证码体系。每个示例都驱动站点自身的 JavaScript 生成其所需参数，再完成整个流程。

| 系统 | 类型 | 示例 |
| --- | --- | --- |
| **瑞数 Ruishu 5/6** | 动态 VM / 页面防护 | `fangdi`（网上房地产）、`cebwm`（光大理财） |
| **极验 Geetest** | 滑块 / 一键通过 | `geetest` |
| **腾讯天御 Tencent Captcha** | 无感 + 滑块 | `tianyu` |
| **数美 Shumei** | 滑块 | `shumei` |
| **网易易盾 NetEase Yidun** | 智能验证 | `yidun` |
| **Arkose Labs + iovation** | 企业风控 / 设备指纹 | `expedia-taap` |
| **CreepJS** | 指纹审计 | `creepjs`（全部项目通过） |

以及完整的生产级数据采集流程：**BOSS 直聘**、**今日头条**、**抖音**、**小红书**、**Google**、**Expedia TAAP**。

> 🔒 **严禁用于任何非法用途，仅用于研究新时代 AI 浏览器。** 线上结果取决于当前网络状况与各站点的实时响应。

## 🚀 快速开始

当前版本 **0.1.3**，适用于 **Windows 10 / 11 x64**，需要 **64 位 Python 3.10 或更高版本**（已在 Python 3.14 下验证）。

```powershell
python -m pip install ruyijs
python -c "import ruyijs; print(ruyijs.__version__)"
```

wheel 自带原生运行时，运行本地脚本无需再次下载。

## 📚 使用方法

### 核心 API 一览

| 功能 | 用法 |
| --- | --- |
| JavaScript 执行 | `Context.eval()`，同一上下文保留变量和函数 |
| Python / JS 数据交换 | `set()`、数组与对象转换、`UNDEFINED` |
| JS 函数调用 | `eval(..., to_py=False)` 返回可调用的 `JSFunction` |
| Python 回调 | `expose()` 将 Python 函数提供给 JavaScript |
| 页面与 DOM | `load_page(url, html)`、DOM 查询、经典脚本执行 |
| 环境配置 | `configure_fingerprint()`，配置 Navigator、Screen、时区等 |
| 时间与调度 | `advance()`、`tick()`、系统时钟与逻辑时钟 |
| 网络与代理 | 页面内 `fetch` / XHR，`Context(proxy=...)` |
| 离线资源 | `put_resource()` 提供脚本或请求响应 |
| 错误与日志 | `JSError`、`console_log()`、`net_log()` |

### 传入数据、调用 JavaScript 函数

```python
from ruyijs import Context

with Context() as context:
    context.set("config", {"offset": 2})
    add = context.eval("(value) => value + config.offset", to_py=False)
    print(add(40))  # 42
```

`JSFunction` / `JSObject` 引用随所属 `Context` 关闭而失效。需要普通 Python 数据时，可直接让 `eval()` 返回数组、对象或基本值。

### 调用 Python 函数

```python
from ruyijs import Context

with Context() as context:
    context.expose(lambda a, b: a + b, "add")
    print(context.eval("add(20, 22)"))  # 42
```

回调中请使用传入的数据；同一个 `Context` 的嵌套调用会抛出 `ReentrantError`。

### 加载 HTML 与脚本

```python
from ruyijs import Context

with Context() as context:
    context.put_resource("https://example.test/app.js", "window.answer = 42")
    context.load_page("https://example.test/", '''
        <script src="/app.js"></script><p id="message">hello</p>
    ''')
    print(context.eval("document.querySelector('#message').textContent"))  # hello
    print(context.eval("answer"))  # 42
```

`load_page()` 接收页面地址和 HTML 文本；相对资源地址按页面地址解析。上面的资源由 `put_resource()` 提供，整个示例可离线运行。

### 配置浏览器环境

```python
from ruyijs import Context

with Context() as context:
    context.configure_fingerprint({
        "navigator": {"language": "zh-CN", "hardwareConcurrency": 8},
        "screen": {"width": 1920, "height": 1080},
        "viewport": {"width": 1280, "height": 720},
        "locale": {"timezone": "Asia/Shanghai"},
    })
    print(context.eval("[navigator.language, screen.width]"))  # ['zh-CN', 1920]
```

在首次执行页面脚本或加载 HTML 前提交配置。`configure_fingerprint()` 与 `configure_environment()` 使用同一套字段校验。

### 执行定时任务

```python
from ruyijs import Context

with Context() as context:
    context.configure_clock("logical", epoch_ms=1700000000000)
    context.eval("globalThis.result = 0; setTimeout(() => { result = 42 }, 10)")
    context.advance(10)
    print(context.eval("result"))  # 42
```

定时器由宿主显式推进。逻辑时钟直接前进；默认系统时钟下，`advance(10)` 会实际等待相应时间。

### 使用 fetch 与代理

```python
from time import monotonic
from ruyijs import Context

with Context(proxy="http://127.0.0.1:7890", timeout=30) as context:
    context.load_page("https://example.com/", "")
    context.eval('''
        globalThis.reply = null;
        fetch('/').then(async r => ({status: r.status, text: await r.text()}))
          .then(value => { reply = value })
          .catch(error => { reply = {error: String(error)} });
        undefined
    ''')
    deadline = monotonic() + 30
    while context.eval("reply") is None:
        if monotonic() >= deadline:
            raise TimeoutError("等待 fetch 超时")
        context.advance(25)
    print(context.eval("reply"))
```

将代理地址替换为实际使用的 HTTP(S) 代理；传入 `proxy=None` 使用直连。代理仅作用于当前上下文。页面请求需要网络连接，可用 `net_log()` 查看请求记录。

### 处理 JavaScript 错误

```python
from ruyijs import Context, JSError

with Context(timeout=10) as context:
    try:
        context.eval("throw new TypeError('bad input')", filename="demo.js")
    except JSError as error:
        print(error.name, error.message)  # TypeError bad input
        print(error.stack)
```

`timeout` 限制启动及每次请求的等待时间；超时会关闭该上下文，后续工作需新建 `Context`。

## 🧪 运行示例

示例随包安装，无需下载仓库：

```powershell
python -m ruyijs.examples                      # 列出全部示例及其安装路径
python -m ruyijs.examples google --query python --pages 1
python -m ruyijs.examples boss --query ai --city 101210100
python -m ruyijs.examples fangdi               # 网上房地产（瑞数 6）
python -m ruyijs.examples cebwm --pages 3      # 光大理财（瑞数定制）
python -m ruyijs.examples toutiao --pages 3    # 今日头条
python -m ruyijs.examples xhs --pages 3        # 小红书 rednote 推荐流
python -m ruyijs.examples geetest              # 极验一键通过
python -m ruyijs.examples yidun                # 网易易盾
python -m ruyijs.examples shumei               # 数美滑块
python -m ruyijs.examples tianyu               # 腾讯天御
```

示例均支持 `--direct`（直连）和 `--proxy http://127.0.0.1:7890`，在名称后加 `--help` 查看全部参数，`--output result.json` 可保存结果。各示例目录内附 README。线上结果受网络与站点当前响应影响。

## 🏗️ 架构

ruyiJS 遵循严格的领域驱动分层：**领域层**只负责浏览器语义、不依赖引擎；**应用层**编排用例；**基础设施层**适配 V8/SpiderMonkey 与 Necko；**接口层**只拥有 C ABI 与生命周期。C API 与 Python 绑定共用同一套运行时装配协调器和同一组有序 API 安装器，因此每个浏览器 API 都有且仅有一个所有者。

实现代码位于 [`src/`](./src)（领域层、应用层与各浏览器子系统）与 [`python/ruyijs/`](./python/ruyijs)（Python 绑定）。

## 📏 使用范围与限制

本版本提供 **Windows x64** 上的 JavaScript 执行及广泛的 Web API 环境，**不含浏览器窗口，也没有完整的页面布局与渲染**。它是面向自动化、分析与研究的工具 —— 请在遵守目标站点服务条款与适用法律的前提下使用。

## 🔗 相关项目

- [**ruyiHttp**](https://gitee.com/losenine888/ruyiHttp) —— 基于 Firefox 原生网络组件的 Requests 风格 Python 请求库。

## 💬 联系方式

二次分发、商业授权、技术交流，欢迎添加作者微信，或扫码加入交流群。

<table>
<tr>
<td align="center"><img src="./assets/wechat-qr.jpg" alt="微信 — 如意" width="220"><br><b>微信：</b>如意</td>
<td align="center"><img src="./assets/wechat-group-qr.jpg" alt="交流群 — AI 浏览器过检测交流群" width="220"><br><b>交流群：</b>AI 浏览器过检测交流群</td>
</tr>
</table>

> 群二维码会定期刷新；如已过期，请添加作者微信（如意）邀请入群。

## 📄 许可证

基于 **[Mozilla Public License 2.0](./LICENSE)** 开源，第三方声明见 [`NOTICE`](./NOTICE)。

> 📌 温馨提示：**二次分发和商业化请取得作者许可** —— 可添加作者微信（**如意**）或在 [GitHub](https://github.com/aanderson1854/ruyijs) 提交 issue。
