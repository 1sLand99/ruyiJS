# CreepJS

在项目根目录运行：

```powershell
python examples/creepjs/creepjs.py --proxy http://127.0.0.1:7890 --output creepjs.json
python examples/creepjs/creepjs.py --direct
```

默认依次检查代理环境变量、本机 7890，最后直连。参数：`--direct` 强制直连，`--timeout` 总期限（秒，默认 60），
`--output` 同时写出 JSON。一次运行约 6 秒，其中指纹计算约 1.6–2 秒（Firefox trace 中为 0.76 秒）。

页面是 `https://abrahamjuliot.github.io/creepjs/`，流程与 Firefox trace `jscall-detail-desktop-20261022-181949`
一致：creep.js 在主文档和一个同源 iframe 里依次检测各项，算出 FP ID 和 fuzzy hash。脚本只读取页面自己的
console 输出（各项 passed/failed 与耗时）和渲染出的 FP ID，不注入、不替换浏览器 API。

输出字段：

- `fpId`、`fuzzy`：页面显示的指纹；
- `passed`：通过的检测项与耗时（毫秒）；`failed`：失败的检测项；
- `notRun`：Firefox 跑过、本次没有出现的检测项；
- `consoleErrors`：页面 `console.error` 的文本；`ok`：结论。

`ok` 为真（退出码 0）的条件：指纹计算完成，loose/stable 两个指纹都通过，且没有失败项。全部检测项与 Firefox trace
一致，包括 service worker（creep.js 注册自身为 Service Worker，经 `postMessage` 取回 worker 作用域的数据）。

为跑通本例补齐的能力（各有 owner 记录与 Firefox 对照探针）：`<template>` 内容、HTML 解析器的 SVG/MathML
foreign content、`navigator.plugins`/`mimeTypes` 可迭代、网络 URL 的 Worker 脚本、canvas `measureText` 对无字体覆盖
字符的度量、`SVGTextContentElement.getSubStringLength`、跨 realm 的 Range 边界、Service Worker 执行（注册、安装/激活、双向消息）、`Range.getClientRects/getBoundingClientRect`、
导航后的语音列表发布、OfflineAudioContext 完成事件顺序、
`window[i]` 帧索引。
