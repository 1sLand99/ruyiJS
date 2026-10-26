"""小红书（rednote）PC 首页推荐流：ruyijs+necko 原生环境由页面自己的安全 SDK 完成访客会话与签名并滚动加载。

python xhs.py
python xhs.py --pages 3 --proxy http://127.0.0.1:7890 --output xhs.json
python xhs.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261023-202623 一致）：首页 -> 安全 SDK（/api/sec/v1/ds、
scripting、sbtsource）-> 访客 /api/sns/web/v1/login/activate（下发 HttpOnly web_session）-> /api/sns/web/v2/user/me
-> /api/sec/v1/shield/webprofile -> 读者向下滚动；页面瀑布流的 scroll 监听读 documentElement.scrollTop，接近列表
末尾时请求 /api/sns/web/v1/homefeed（X-s/X-t/X-S-Common/x-rap-param 由页面 axios 拦截器加上）-> 新卡片渲染。
脚本只导航、用 window.scrollBy 滚动并读取页面渲染出的卡片；不替换浏览器 API、不注入 cookie、不拼签名。
退出码 0 表示 login/activate 与 shield/webprofile 为 HTTP 200、之后的请求带 web_session、每一页 homefeed 都是
页面自己发出的 HTTP 200（第二页起携带上一页响应给出的 cursor_score）、每页都渲染出新笔记，且没有页面脚本异常。
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
from time import monotonic
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

URL = "https://www.rednote.com/"
HOMEFEED = "/api/sns/web/v1/homefeed"
FLOW = ("/api/sec/v1/ds", "/api/sec/v1/scripting", "/api/sec/v1/sbtsource", "/api/sns/web/v1/login/activate",
        "/api/sns/web/v2/user/me", "/api/sec/v1/shield/webprofile", HOMEFEED)
# 瀑布流里当前渲染的笔记卡片（虚拟列表会回收离开视口的卡片），链接去掉 xsec_token 查询串。
READ = """(()=>({ready:document.readyState,title:document.title,scrollTop:document.documentElement.scrollTop,
  notes:[...document.querySelectorAll('section.note-item')].map(s=>{const a=s.querySelector('a.cover'),
    t=s.querySelector('.footer a.title');return a&&{url:new URL(a.getAttribute('href'),location.href).origin+
    new URL(a.getAttribute('href'),location.href).pathname,title:t?t.textContent.trim():''}}).filter(Boolean)}))()"""


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
    try:
        body = json.loads(row.get("requestBody") or "{}")
    except ValueError:
        body = {}
    return {"status": row["status"], "cursorScore": body.get("cursor_score"), "noteIndex": body.get("note_index"),
            "category": body.get("category"), "webSession": "web_session" in (row.get("cookieNames") or []),
            "body": row.get("requestBody")}


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

        def rows(path):
            return [row for row in call(context.net_log) if urlsplit(row["url"]).path == path]

        def done(path):
            return any(row["status"] == 200 for row in rows(path))

        call(context.configure_clock, "system")
        call(context.navigate, URL)
        while True:  # 首屏卡片 + 安全 SDK、访客会话与设备画像完成，读者此时才开始滚动
            advance()
            state = call(context.eval, READ)
            if state["ready"] == "complete" and state["notes"] and all(
                    done(path) for path in ("/api/sns/web/v1/login/activate", "/api/sec/v1/shield/webprofile")):
                break
        report["title"], report["firstScreen"] = state["title"], state["notes"]
        seen = {note["url"] for note in state["notes"]}
        for page in range(args.pages):
            sent, fresh = len(rows(HOMEFEED)), []
            while True:  # 像读者一样分段向下滚动，直到页面自己请求下一页、响应 200 并渲染新笔记
                call(context.eval, "window.scrollBy(0, 600); undefined")
                advance(400)
                state = call(context.eval, READ)
                fresh += [n for n in state["notes"] if n["url"] not in seen and n not in fresh]
                feeds = rows(HOMEFEED)
                if len(feeds) > sent and feeds[sent]["status"] == 200 and fresh:
                    break
            seen.update(note["url"] for note in fresh)
            report["pages"].append({"page": page + 1, "scrollTop": state["scrollTop"], "newNotes": fresh})
        for _ in range(8):
            advance()
        log = call(context.net_log)
        report["flow"] = [{"method": row["method"], "path": urlsplit(row["url"]).path, "status": row["status"]}
                          for row in log if urlsplit(row["url"]).path in FLOW]
        report["homefeedRequests"] = [feed_request(row) for row in rows(HOMEFEED)]
        activated = next(i for i, row in enumerate(log) if urlsplit(row["url"]).path == FLOW[3])
        report["webSessionAfterActivate"] = any("web_session" in (row.get("cookieNames") or [])
                                                for row in log[activated + 1:])
        feeds = report["homefeedRequests"][:args.pages]
        report["passed"] = (len(report["pages"]) == args.pages and len(feeds) == args.pages
                            and all(f["status"] == 200 and f["webSession"] for f in feeds)
                            and all(f["cursorScore"] for f in feeds[1:])
                            and report["webSessionAfterActivate"]
                            and all(p["newNotes"] for p in report["pages"])
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
