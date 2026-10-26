# 小红书（rednote）

在项目根目录运行：

```powershell
python examples/xhs/xhs.py --pages 3 --proxy http://127.0.0.1:7890 --output xhs.json
```

也可进入本目录运行 `python xhs.py`，或在安装包后运行 `python -m ruyijs.examples xhs --pages 3`。默认依次检查代理
环境变量、本机 7890，最后直连；`--direct` 强制直连，`--pages` 为向下滚动加载的推荐流页数（默认 2），`--timeout`
设置总期限（秒，默认 240）。

首页 `https://www.rednote.com/` 由服务端渲染首屏卡片，随后页面的安全 SDK 依次请求 `/api/sec/v1/ds`、
`/api/sec/v1/scripting`、`/api/sec/v1/sbtsource`，以访客身份 `POST /api/sns/web/v1/login/activate`（响应下发 HttpOnly
`web_session`），再请求 `/api/sns/web/v2/user/me`（访客）与 `/api/sec/v1/shield/webprofile`。推荐流第二页起由瀑布流组件
的 document `scroll` 监听触发：它读 `document.documentElement.scrollTop`，接近列表末尾时 `POST /api/sns/web/v1/homefeed`，
`X-s`、`X-t`、`X-S-Common`、`x-rap-param` 由页面 axios 拦截器加上。脚本只导航、像读者一样分段 `window.scrollBy` 并读取
页面渲染出的笔记卡片，不替换浏览器 API、不注入 cookie、不拼签名。流程与 Firefox trace
`jscall-detail-desktop-20261023-202623` 一致：首个 homefeed 请求体 `cursor_score:""`、`note_index:35`，之后各页携带上一页
响应给出的 `cursor_score`（trace 中为 `seo_homefeed_20261020_29`）。

`passed: true` 与退出码 0 表示：`login/activate` 与 `shield/webprofile` 为 HTTP 200，之后的请求带 `web_session`；每一页
homefeed 都是页面自己发出的 HTTP 200，第二页起带非空 `cursor_score`（页面解析了上一页 `code:0` 的响应）；每页都渲染出
此前未出现的笔记；没有页面脚本异常。`flow` 列出关键接口的顺序与状态，`homefeedRequests[].body` 为页面发出的原始请求体，
`pages[].newNotes` 为新笔记标题与链接（已去掉 `xsec_token` 查询串）。输出只显示 cookie 名称。

已知与 Firefox 的差异：homefeed 请求体 `image_formats` 为 `["jpg","avif"]`，Firefox 为 `["jpg","webp","avif"]`——页面用
`canvas.toDataURL("image/webp")` 检测 WebP，ruyijs Canvas 目前不编码 WebP（返回 `data:,`），属 Canvas owner 的独立缺口。
页面加载期间安全 SDK 的脚本在 js.exe 中计算较久，首次滚动前约需 35–40 秒（Firefox 约 28 秒）。

已知稳定性问题：连续加载到第 3 页及以后时，js.exe 偶发 GC 访问冲突退出（8 次三页运行中 6 次，均在第 2 页完成之后；2 次两页运行
未见）：GC 遇到已清扫对象的槽写入记录，写入者尚未定位，分析见 `artifacts/xhs/NOTES.md`。

未覆盖：trace 中鼠标悬停预取的笔记详情分块；打开笔记详情、评论与登录。
