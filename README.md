<div align="center">

# 🦊 ruyiJS

**A new-generation, minimalist browser purpose-built for AI-driven automation — built on the Firefox architecture, with the authentic Firefox JavaScript engine and networking stack.**

Purpose-built for specialized workloads: **web scraping, JS reverse engineering, data collection, and bypassing bot-verification systems** — all from Python, with no browser window.

[![PyPI](https://img.shields.io/pypi/v/ruyijs?style=flat-square&color=3775A9&logo=pypi&logoColor=white)](https://pypi.org/project/ruyijs/)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.10-3776AB?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/ruyijs/)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078D4?style=flat-square&logo=windows&logoColor=white)](https://pypi.org/project/ruyijs/)
[![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)](./LICENSE)

**English** · [简体中文](./README.zh-CN.md)

[Quick Start](#-quick-start) · [Features](#-features) · [Verification Systems](#-verification-systems-defeated) · [Usage](#-usage) · [Examples](#-examples) · [Architecture](#-architecture)

</div>

---

```python
from ruyijs import Context

with Context() as context:
    context.eval("let count = 40")
    print(context.eval("count += 2"))        # 42
    print(context.eval("navigator.userAgent"))
```

## 🎯 Why ruyiJS

Headless Chrome and Playwright give you a whole browser — a GPU-rendering, window-managing, memory-hungry process that anti-bot vendors have spent years learning to detect. ruyiJS takes the opposite path: it embeds the **real Firefox internals** that matter for automation — the **SpiderMonkey** JavaScript engine and the **Necko** networking stack (HTTP/1.1, HTTP/2, HTTP/3) — and nothing else.

The result is an environment that executes a site's JavaScript, challenges, signatures, and fingerprints **exactly as Firefox would**, but as a lightweight, scriptable Python library that leaves no window and no layout engine behind. Each `Context` is its own process with a persistent JavaScript world and its own proxy, so sessions stay isolated and reproducible.

## ✨ Features

- 🦊 **Authentic Firefox internals** — the genuine SpiderMonkey engine (Firefox 158) and the Necko network transport, not a reimplementation or a shim.
- 🪶 **Truly headless** — no window, no rendering, no layout engine. A pure JavaScript + Web API environment that starts fast and stays light.
- 🧩 **38 bounded browser contexts** — DOM, Navigator, Screen, Storage, Canvas/WebGL, Workers, Service Workers, iframes, Performance, Intl, Permissions, and more.
- 🧬 **Configurable fingerprint/profile** — set Navigator, Screen, viewport, timezone, and locale through a single validated configuration surface.
- ⏱️ **Deterministic clock & event loop** — drive timers with a logical clock for reproducible runs, or use the system clock for live work.
- 🌐 **Native `fetch` / XHR over Necko** — real HTTP/1.1, HTTP/2 and HTTP/3, with a **per-context proxy**.
- 📴 **Offline replay** — serve scripts and responses with `put_resource()` to run captured flows with no network.
- 🔁 **Python ↔ JS bridge** — pass data with `set()`, call JS functions from Python, and expose Python callbacks to JavaScript.
- 📦 **Batteries included** — the wheel bundles the SHA256-pinned native runtime; after `pip install`, local scripts run fully offline.

## 🛡️ Verification systems defeated

ruyiJS ships runnable, closed-loop examples against real-world anti-bot and CAPTCHA stacks. Each example drives the site's own JavaScript to produce the parameters it demands, then completes the flow.

| System | Category | Example |
| --- | --- | --- |
| **瑞数 Ruishu 5/6** | Dynamic VM / page protection | `fangdi` (网上房地产), `cebwm` (光大理财) |
| **极验 Geetest** | Slider / one-click | `geetest` |
| **腾讯天御 Tencent Captcha** | No-feel + slider | `tianyu` |
| **数美 Shumei** | Slider | `shumei` |
| **网易易盾 NetEase Yidun** | Smart check | `yidun` |
| **Arkose Labs + iovation** | Enterprise risk / device | `expedia-taap` |
| **CreepJS** | Fingerprint audit | `creepjs` (passes every section) |

And full production data-collection flows: **BOSS 直聘**, **今日头条 Toutiao**, **抖音 Douyin**, **小红书 RedNote**, **Google**, **Expedia TAAP**.

> 🔒 **Strictly prohibited for any unlawful use.** ruyiJS is provided **solely for research into a new generation of AI browsers.** Live results depend on current network conditions and each site's present responses.

## 🚀 Quick Start

Current version **0.1.3**. Requires **Windows 10 / 11 x64** and **64-bit Python 3.10+** (verified on Python 3.14).

```powershell
python -m pip install ruyijs
python -c "import ruyijs; print(ruyijs.__version__)"
```

The wheel bundles the native runtime — no additional download is needed to run local scripts.

## 📚 Usage

### Core API at a glance

| Capability | How |
| --- | --- |
| Execute JavaScript | `Context.eval()` — variables and functions persist across calls |
| Python ↔ JS data | `set()`, array/object conversion, `UNDEFINED` |
| Call JS functions | `eval(..., to_py=False)` returns a callable `JSFunction` |
| Python callbacks | `expose()` makes a Python function available to JavaScript |
| Pages & DOM | `load_page(url, html)`, DOM queries, classic script execution |
| Environment / fingerprint | `configure_fingerprint()` — Navigator, Screen, timezone, … |
| Time & scheduling | `advance()`, `tick()`, system clock vs. logical clock |
| Network & proxy | in-page `fetch` / XHR, `Context(proxy=...)` |
| Offline resources | `put_resource()` serves scripts or request responses |
| Errors & logs | `JSError`, `console_log()`, `net_log()` |

### Pass data and call JavaScript functions

```python
from ruyijs import Context

with Context() as context:
    context.set("config", {"offset": 2})
    add = context.eval("(value) => value + config.offset", to_py=False)
    print(add(40))  # 42
```

`JSFunction` / `JSObject` references become invalid when their owning `Context` closes. For plain Python data, let `eval()` return arrays, objects, or primitives directly.

### Call Python functions from JavaScript

```python
from ruyijs import Context

with Context() as context:
    context.expose(lambda a, b: a + b, "add")
    print(context.eval("add(20, 22)"))  # 42
```

Use the data passed into the callback; a nested call back into the same `Context` raises `ReentrantError`.

### Load HTML and scripts

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

`load_page()` takes a page URL and HTML text; relative resource URLs resolve against the page URL. The resource above is served by `put_resource()`, so the whole example runs offline.

### Configure the browser environment

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

Commit the configuration before the first page script or HTML load. `configure_fingerprint()` and `configure_environment()` share one field-validation surface.

### Run scheduled tasks

```python
from ruyijs import Context

with Context() as context:
    context.configure_clock("logical", epoch_ms=1700000000000)
    context.eval("globalThis.result = 0; setTimeout(() => { result = 42 }, 10)")
    context.advance(10)
    print(context.eval("result"))  # 42
```

Timers are advanced explicitly by the host. A logical clock moves forward instantly; under the default system clock, `advance(10)` actually waits.

### Use `fetch` with a proxy

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
            raise TimeoutError("fetch timed out")
        context.advance(25)
    print(context.eval("reply"))
```

Replace the proxy with your own HTTP(S) proxy, or pass `proxy=None` for a direct connection. The proxy is scoped to the current context. Page requests need network access; use `net_log()` to inspect the request record.

### Handle JavaScript errors

```python
from ruyijs import Context, JSError

with Context(timeout=10) as context:
    try:
        context.eval("throw new TypeError('bad input')", filename="demo.js")
    except JSError as error:
        print(error.name, error.message)  # TypeError bad input
        print(error.stack)
```

`timeout` limits startup and each request. On timeout the context is closed; continue with a fresh `Context`.

## 🧪 Examples

Examples ship inside the package — no need to clone the repository:

```powershell
python -m ruyijs.examples                      # list every example and its install path
python -m ruyijs.examples google --query python --pages 1
python -m ruyijs.examples boss --query ai --city 101210100
python -m ruyijs.examples fangdi               # 网上房地产 (Ruishu 6)
python -m ruyijs.examples cebwm --pages 3      # 光大理财 (custom Ruishu)
python -m ruyijs.examples toutiao --pages 3    # 今日头条
python -m ruyijs.examples xhs --pages 3        # 小红书 / RedNote home feed
python -m ruyijs.examples geetest              # 极验 one-click
python -m ruyijs.examples yidun                # 网易易盾
python -m ruyijs.examples shumei               # 数美 slider
python -m ruyijs.examples tianyu               # 腾讯天御
```

Every example supports `--direct` (direct connection) and `--proxy http://127.0.0.1:7890`. Add `--help` after a name for all options, and `--output result.json` to save results. Each example directory ships its own README. Live results vary with network conditions and current site responses.

## 🏗️ Architecture

ruyiJS follows a strict domain-driven layering: **domain** code owns browser semantics with no engine dependency, **application** orchestrates use cases, **infrastructure** adapts V8/SpiderMonkey and Necko, and **interface** code owns only the C ABI and lifecycle. The C API and Python binding share one runtime-assembly coordinator and the same ordered API installers, so every browser API has exactly one owner.

The implementation lives under [`src/`](./src) (the domain layer, application layer, and every browser subsystem) and [`python/ruyijs/`](./python/ruyijs) (the Python binding).

## 📏 Scope & limitations

This release provides JavaScript execution and a broad Web API environment on **Windows x64**. It has **no browser window and no full page layout or rendering**. It is a tool for automation, analysis, and research — use it in compliance with the terms of service of any site you interact with and with applicable law.

## 🔗 Related projects

- [**ruyiHttp**](https://gitee.com/losenine888/ruyiHttp) — a Requests-style Python HTTP library built on Firefox's native networking components.

## 💬 Contact

Questions, permission requests, commercial licensing, or just to talk shop — add the author on WeChat, or scan to join the discussion group.

<table>
<tr>
<td align="center"><img src="./assets/wechat-qr.jpg" alt="WeChat QR — 如意" width="220"><br><b>WeChat:</b> 如意</td>
<td align="center"><img src="./assets/wechat-group-qr.jpg" alt="Group — AI 浏览器过检测交流群" width="220"><br><b>Group:</b> AI 浏览器过检测交流群</td>
</tr>
</table>

> The group QR refreshes periodically; if it has expired, add the author on WeChat (如意) for an invite.

## 📄 License

Licensed under the **[Mozilla Public License 2.0](./LICENSE)**. See [`NOTICE`](./NOTICE) for third-party attributions.

> 📌 As a courtesy: for **redistribution and commercial use, please obtain the author's permission** — add the author on WeChat (ID: **如意**) or open an issue on [GitHub](https://github.com/aanderson1854/ruyijs).
