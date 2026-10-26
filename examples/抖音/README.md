# 抖音精选

在项目根目录运行：

```powershell
python "examples/抖音/douyin.py" --pages 3 --proxy http://127.0.0.1:7890 --output douyin.json
```

也可进入本目录运行 `python douyin.py`。默认依次检查代理环境变量、本机 7890，最后直连；
`--direct` 强制直连，`--pages` 为向下滚动加载的视频流页数（默认 2），`--timeout` 设置总期限（秒，默认 240）。

首页 `https://www.douyin.com/` 302 跳转到 `/jingxuan`，随后页面加载字节的安全 SDK（bdms、验证码 SDK 等）：
精选视频流 `/aweme/v2/web/module/feed/` 由页面的瀑布流在接近底部时请求，XHR 钩子加上 `a_bogus` 与
`verifyFp`（`webid`）。顶部是分类 Tab（CSS grid 三列网格），视频卡片在网格的滚动容器里渲染。脚本只导航、
像读者一样在视频网格容器里分段设置 `scrollTop` 向下滚动并读取页面渲染出的卡片，不替换浏览器 API、
不注入 cookie、不拼签名。流程与 Firefox trace `envtrace-desktop-20261024-212518` 一致。

`passed: true` 与退出码 0 表示：首屏 feed 均为 HTTP 200 且带 `a_bogus` 与 `verifyFp`、顶部分类 Tab 与
首屏视频卡片已渲染、之后每一页滚动都由页面自己发出 `refresh_index` 递增、带 `a_bogus` 与 `verifyFp`
的 feed 请求且均为 HTTP 200、每页都渲染出新卡片、没有页面脚本异常。`categories` 为分类 Tab 文案，
`firstScreen.sample` 与 `pages[].sample` 为卡片的 aweme id、标题和封面 alt（从已渲染 DOM 读取）。
输出只显示 cookie 名称。

与 trace 一致，精选 feed 的签名是 `a_bogus` + `verifyFp`，不带 `msToken`（`msToken` 用于抖音的其它接口）。

未覆盖：trace 中点击视频卡片打开播放页及其后续请求；ruyijs 目前只有一个顶层浏览上下文，视频详情页不会打开。
