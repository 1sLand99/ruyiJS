# ruyijs examples

通过 pip 安装后可直接运行 `python -m ruyijs.examples <名称>`（见[项目首页](../README.md)）。在仓库目录也可执行：

```powershell
python .\examples\google\google_search.py --query python --pages 1
python .\examples\google\google_search.py --query "site:tiktok.com electric bile" --pages 3
python .\examples\boss\boss.py --query ai --city 101210100
python ".\examples\网上房地产-瑞数6\fangdi.py"
python ".\examples\光大理财-瑞数定制\cebwm.py" --pages 3
python ".\examples\今日头条\toutiao.py" --pages 3
python ".\examples\抖音\douyin.py" --pages 3
python .\examples\xhs\xhs.py --pages 3
python ".\examples\极验\geetest_fullpage.py"
python ".\examples\网易易盾\yidun.py"
python ".\examples\数美\shumei.py"
python ".\examples\腾讯天御\tianyu.py"
python .\examples\creepjs\creepjs.py
python .\examples\turnstile\turnstile.py --direct --timeout 120
```

示例均支持 `--help`、`--direct` 和 `--proxy http://127.0.0.1:7890`。
Turnstile 示例是实时网络登录案例：它在同一 Context 中完成登录并复验 dashboard；结果受网络与站点当前响应影响。
Google 的 `--pages 1` 表示首页后再翻一页。实站结果取决于当前网络和站点响应。
查询带 `site:` 时会做投毒检测：结果中出现其他站点（按 `<cite>` 域名，视频/社交结果按来源名判断）即判 `poisoned`、退出码 1；Google 的拼写纠正（如 bile → bike）不算失败。
已有本地 `dist/js.exe` 的源码目录仍可直接运行；其余场景使用已安装的包。
便携发行目录可将上面的 `python` 替换成 `python.cmd`。

安装与 API 示例见 [项目首页](../README.md)。

## 长流程的请求分层

需要页面环境的示例只让 ruyijs 运行页面脚本，生成 challenge、签名、指纹和 Cookie 等参数；
拿到参数后，请求由 Necko 会话发送。Google、BOSS、极验、数美、腾讯天御的图片/接口请求已使用这一
混合路径，页面不再承担可以直接交给 HTTP 传输的等待。其余分页和验证码示例仍需保留页面任务，
因为下一页游标、拖动状态或服务端校验依赖页面事件；它们的底层 fetch/XHR 也统一经过 Resource
Network 的 Necko 适配器。每个示例报告中的 `elapsedSeconds` 用于比较参数计算和网络传输耗时。
