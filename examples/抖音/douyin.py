"""抖音精选 PC（www.douyin.com/jingxuan）：ruyijs+necko 原生环境由页面自己的脚本完成 ttwid、msToken、
a_bogus 并加载精选视频流。

python douyin.py
python douyin.py --pages 3 --proxy http://127.0.0.1:7890 --output douyin.json
python douyin.py --direct

流程（与 Firefox trace envtrace-desktop-20261024-212518 一致）：首页 www.douyin.com 302 到 /jingxuan ->
页面脚本加载 bdms、验证码等安全 SDK，首屏请求 /aweme/v2/web/module/feed/（a_bogus 与 verifyFp 由页面安全
SDK 的 XHR 钩子加签，refresh_index=1）-> 顶部分类 Tab 与三列视频网格渲染 -> 读者在视频网格的滚动容器里
向下滚动，页面瀑布流接近底部时继续请求下一页 feed（refresh_index 递增）-> 新卡片渲染。
脚本只导航、用元素 scrollTop 滚动并读取页面渲染出的卡片；不替换浏览器 API、不注入 cookie、不拼签名。
退出码 0 表示：首屏 feed 均为 HTTP 200 且带 a_bogus 与 verifyFp，顶部分类 Tab 与首屏视频卡片已渲染，
之后每一页滚动都由页面自己发出 refresh_index 递增、带 a_bogus 与 verifyFp 的 feed 请求且均为 HTTP 200、
每页都渲染出新卡片，且没有页面脚本异常。
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

URL = "https://www.douyin.com/"
FEED = "/aweme/v2/web/module/feed/"
# 精选页的分类 Tab、首屏视频网格的滚动容器，以及当前渲染的视频卡片（id 为真实 aweme id，标题取卡片最深层文本）。
READ = r"""(()=>{const panel=document.querySelector('#semiTabPanel0');
  const tabs=[...document.querySelectorAll('[id^="semiTab"]:not([id^="semiTabPanel"])')]
    .map(e=>e.textContent.trim()).filter(Boolean).slice(0,12);
  const cardEls=panel?[...panel.querySelectorAll('[id]')].filter(e=>/^\d{15,}$/.test(e.id)):[];
  const cards=cardEls.map(e=>{const img=e.querySelector('img[alt]');
    const title=[...e.querySelectorAll('*')].map(x=>x.children.length===0&&x.textContent.trim())
      .find(t=>t&&t.length>6&&!/^[\d:]+$/.test(t))||'';
    return {id:e.id,alt:(img&&img.getAttribute('alt'))||'',title:String(title).slice(0,60)};});
  const scroller=panel?[...panel.querySelectorAll('*')]
    .find(e=>/auto|scroll/.test(getComputedStyle(e).overflowY)&&e.scrollHeight>e.clientHeight+50):null;
  if(scroller&&!scroller.id)scroller.id='__ruyi_feed_scroller';
  return {ready:document.readyState,title:document.title,url:location.href,tabs,
    cards,scroller:scroller?{id:scroller.id,top:scroller.scrollTop,height:scroller.scrollHeight,
      view:scroller.clientHeight}:null};})()"""


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


def feed_request(row):
    query = parse_qs(urlsplit(row["url"]).query)
    index = query.get("refresh_index", [None])[0]
    return {"status": row["status"], "method": row.get("method"),
            "a_bogus": bool(query.get("a_bogus", [""])[0]),
            "verifyFp": bool(query.get("verifyFp", [""])[0]),
            "refresh_index": int(index) if index and index.isdigit() else index,
            "module_id": query.get("module_id", [None])[0]}


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

        def feeds():
            return [row for row in call(context.net_log) if urlsplit(row["url"]).path == FEED]

        call(context.configure_clock, "system")
        call(context.navigate, URL)
        state = None
        while True:  # 跳转到 /jingxuan，首屏 feed 成功、分类 Tab 与视频卡片渲染
            advance()
            state = call(context.eval, READ)
            done = [r for r in feeds() if r["status"] == 200]
            if (state["ready"] == "complete" and "/jingxuan" in state["url"] and state["tabs"]
                    and state["cards"] and done and state["scroller"]):
                break
        report["title"] = state["title"]
        report["categories"] = state["tabs"]
        report["firstScreen"] = {"cards": len(state["cards"]), "sample": state["cards"][:6]}
        first_screen_feeds = len(feeds())
        seen = {card["id"] for card in state["cards"]}
        scroller = state["scroller"]["id"]
        for page in range(args.pages):
            sent = len(feeds())
            fresh = []
            while True:  # 像读者一样在视频网格容器里分段向下滚动，直到页面请求下一页、响应 200 并渲染新卡片
                call(context.eval,
                     "(()=>{const s=document.getElementById(%r);if(s)s.scrollTop+=1200;})()" % scroller)
                for _ in range(3):
                    advance(300)
                state = call(context.eval, READ)
                fresh += [c for c in state["cards"] if c["id"] not in seen and c not in fresh]
                batch = feeds()
                if len(batch) > sent and batch[sent]["status"] == 200 and fresh:
                    break
            seen.update(card["id"] for card in fresh)
            report["pages"].append({"page": page + 1, "scrollTop": state["scroller"]["top"],
                                    "newCards": len(fresh), "sample": fresh[:4]})
        for _ in range(8):
            advance()
        batch = feeds()
        report["feedRequests"] = [feed_request(row) for row in batch]
        report["firstScreenFeeds"] = first_screen_feeds
        report["cookieNames"] = call(context.eval,
            "document.cookie.split(';').map(x=>x.trim().split('=')[0]).filter(Boolean)")
        scrolled = report["feedRequests"][first_screen_feeds:]
        # 与 Firefox trace 一致：精选 feed 的签名是 a_bogus + verifyFp（webid），不带 msToken。
        report["passed"] = (
            len(report["pages"]) == args.pages
            and bool(report["categories"]) and report["firstScreen"]["cards"] > 0
            and bool(batch)
            and all(r["status"] == 200 and r["a_bogus"] and r["verifyFp"] for r in report["feedRequests"])
            and len(scrolled) >= args.pages
            and increasing(r["refresh_index"] for r in report["feedRequests"])
            and all(p["newCards"] > 0 for p in report["pages"])
            and not report["scriptErrors"])
        context.timeout = min(5, max(1, deadline - monotonic()))


def increasing(values):
    seen = [v for v in values if isinstance(v, int)]
    return all(b >= a for a, b in zip(seen, seen[1:]))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--pages", type=int, default=2, help="向下滚动加载的视频流页数")
    parser.add_argument("--timeout", type=float, default=240, help="总期限，秒")
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
