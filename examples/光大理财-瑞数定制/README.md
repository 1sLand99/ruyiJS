# 光大理财

在项目根目录运行：

```powershell
python "examples/光大理财/cebwm.py" --pages 3 --proxy http://127.0.0.1:7890 --output cebwm.json
```

也可进入本目录运行 `python cebwm.py`。默认依次检查代理环境变量、本机 7890，最后直连；
`--direct` 强制直连，`--timeout` 设置总期限（秒）。

页面 `https://www.cebwm.com/wealth/grlc/index.html` 由瑞数保护：首页先返回 412 与动态 js，
js 生成 cookie 后首页返回 200；产品列表由页面脚本 POST `/eportal/ui` 取得，URL 参数和请求体
都由瑞数加密。脚本只导航并读取页面渲染出的表格，翻页用可信点击“>”按钮，不替换浏览器 API、
不注入 cookie。流程与 Firefox trace `jscall-detail-desktop-20261022-004337` 一致
（访问计数 POST + 列表 POST，每次翻页再发一次）。

`passed: true` 与退出码 0 表示每页都有产品行且页码不同、全部 `/eportal/ui` 请求 HTTP 200、
没有页面脚本异常。`pages[].products` 为名称、代码、起点金额、单位净值及日期、风险等级。
输出只显示 cookie 名称。
