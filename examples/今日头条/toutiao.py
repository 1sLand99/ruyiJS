"""今日头条 PC 首页推荐流：ruyijs 原生环境由页面自己的脚本完成 ttwid、msToken、a_bogus、_signature 并加载信息流。

python toutiao.py
python toutiao.py --pages 3 --proxy http://127.0.0.1:7890 --output toutiao.json
python toutiao.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261022-112029 一致）：首页 -> ttwid 注册回跳 -> 首页 ->
页面脚本加载 acrawler/sdk-glue/bdms 等 SDK，请求 /api/pc/info、热搜词、热榜（_signature）->
读者向下滚动，页面的滚动监听在接近列表底部时请求 /api/pc/list/feed（msToken + a_bogus，由 bdms 的
XHR 钩子加签）-> 新卡片渲染。滚动用 window.scrollBy，滚动事件由 ruyijs 的窗口滚动 owner 派发。
脚本不替换任何浏览器 API，不注入 cookie，不拼签名。
退出码 0 表示每一页都发出了带 a_bogus 和 msToken 的 feed 请求、均为 HTTP 200、新卡片已渲染，
_signature 请求均为 HTTP 200，且没有页面脚本异常。
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
from time import monotonic
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

URL = "https://www.toutiao.com/"
FEED = "/api/pc/list/feed"
SIGNED = ("/api/pc/info", "/search/suggest/hot_words/", "/hot-event/hot-board/")
# 推荐流里的文章卡片标题与热榜条目，均从页面已渲染的 DOM 读取。
READ = """(()=>({ready:document.readyState,title:document.title,url:location.href,
  cards:document.querySelectorAll('.feed-card-wrapper').length,
  articles:[...document.querySelectorAll('.feed-card-article-l a.title')].map(a=>({title:a.textContent.trim(),
    url:a.href})).filter(a=>a.title),
  hot:[...document.querySelectorAll('.home-hotboard a')].map(a=>a.textContent.trim()).filter(Boolean).slice(0,10)}))()"""


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


def signed(row):
    path = urlsplit(row["url"]).path
    query = parse_qs(urlsplit(row["url"]).query)
    return {"path": path, "status": row["status"], "a_bogus": "a_bogus" in query,
            "msToken": "msToken" in query, "_signature": "_signature" in query}


def run(args, report):
    deadline = monotonic() + args.timeout
    with Context(proxy=report["proxy"] or None, timeout=args.timeout) as context:
        def call(method, *values, **kwargs):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("等待页面超时")
            context.timeout = remaining
            return method(*values, **kwargs)

        def advance(ms=250):
            try:
                call(context.advance, ms, max_tasks=500)
            except JSError as error:
                entry = {"name": error.name, "message": error.message[:300]}
                if entry not in report["scriptErrors"] and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(entry)

        def rows(part):
            return [row for row in call(context.net_log)
                    if urlsplit(row["url"]).netloc == "www.toutiao.com" and part in urlsplit(row["url"]).path]

        call(context.configure_clock, "system")
        call(context.navigate, URL)
        state = None
        began = monotonic()

        def bdms_ready():
            # bdms reads msToken from its mssdk.bytedance.com/web/common response; a reader
            # scrolls after the page (and this security SDK) finished initializing.
            return any(urlsplit(r["url"]).netloc == "mssdk.bytedance.com" and r["status"] == 200
                       for r in call(context.net_log)) or monotonic() - began > 15
        while True:  # 首页完成且首屏卡片渲染
            advance()
            state = call(context.eval, READ)
            if state["ready"] == "complete" and state["cards"] and all(rows(p) for p in SIGNED) and bdms_ready():
                break
        report["title"], report["firstScreenCards"] = state["title"], state["cards"]
        report["hotBoard"] = state["hot"]
        seen = {a["url"] for a in state["articles"]}
        for page in range(args.pages):
            sent, cards = len(rows(FEED)), state["cards"]
            while True:  # 像读者一样分段向下滚动，直到页面自己请求下一页并渲染
                call(context.eval, "window.scrollBy(0, 600); undefined")
                advance(400)
                state = call(context.eval, READ)
                if len(rows(FEED)) > sent and state["cards"] > cards:
                    break
            fresh = [a for a in state["articles"] if a["url"] not in seen]
            seen.update(a["url"] for a in fresh)
            report["pages"].append({"page": page + 1, "cards": state["cards"], "newArticles": fresh})
        for _ in range(8):
            advance()
        report["feedRequests"] = [signed(row) for row in rows(FEED)]
        report["signatureRequests"] = [signed(row) for part in SIGNED for row in rows(part)]
        report["cookieNames"] = call(context.eval, "document.cookie.split(';').map(x=>x.trim().split('=')[0]).filter(Boolean)")
        feeds = report["feedRequests"]
        report["passed"] = (len(report["pages"]) == args.pages and len(feeds) >= args.pages
                            and all(r["status"] == 200 and r["a_bogus"] and r["msToken"] for r in feeds)
                            and all(r["status"] == 200 and r["_signature"] for r in report["signatureRequests"])
                            and all(p["newArticles"] for p in report["pages"])
                            and not report["scriptErrors"])
        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--pages", type=int, default=2, help="向下滚动加载的推荐流页数")
    parser.add_argument("--timeout", type=float, default=120, help="总期限，秒")
    parser.add_argument("--output", type=Path, help="将 JSON 结果同时写入此文件")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    if args.pages < 1:
        parser.error("--pages 至少为 1")
    report = {"passed": False, "transport": "ruyijs-page-parameters+necko-fetch", "proxy": None if args.direct else (args.proxy or auto_proxy()),
              "pages": [], "scriptErrors": []}
    started = monotonic()
    try:
        run(args, report)
    except Exception as error:
        report.update(passed=False, error=type(error).__name__ + ": " + str(error))
    report["elapsedSeconds"] = round(monotonic() - started, 3)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", "utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
