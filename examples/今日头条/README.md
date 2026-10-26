# 今日头条

在项目根目录运行：

```powershell
python "examples/今日头条/toutiao.py" --pages 3 --proxy http://127.0.0.1:7890 --output toutiao.json
```

也可进入本目录运行 `python toutiao.py`。默认依次检查代理环境变量、本机 7890，最后直连；
`--direct` 强制直连，`--pages` 为向下滚动加载的推荐流页数（默认 2），`--timeout` 设置总期限（秒）。

首页 `https://www.toutiao.com/` 先注册 ttwid 并回跳首页，随后页面加载字节的安全 SDK
（acrawler、sdk-glue、bdms、secsdk）：`/api/pc/info`、热搜词、热榜请求带 `_signature`；
推荐流 `/api/pc/list/feed` 由页面的滚动监听在接近列表底部时请求，bdms 的 XHR 钩子加上
`msToken` 与 `a_bogus`。脚本只导航、像读者一样分段 `window.scrollBy` 并读取页面渲染出的卡片，
不替换浏览器 API、不注入 cookie、不拼签名。流程与 Firefox trace
`jscall-detail-desktop-20261022-112029` 的首页部分一致（每次滚到底部一页 feed）。

`passed: true` 与退出码 0 表示每页 feed 请求都带 `a_bogus` 与 `msToken` 且 HTTP 200、每页都渲染出新的
文章卡片、三个 `_signature` 请求 HTTP 200、没有页面脚本异常。`pages[].newArticles` 为该页新出现的
文章标题与链接，`hotBoard` 为热榜前十条。输出只显示 cookie 名称。

未覆盖：trace 中点击文章卡片在新标签页打开文章（`target="_blank"`）及其评论请求；ruyijs 目前只有一个
顶层浏览上下文，链接的新标签页不会打开。
