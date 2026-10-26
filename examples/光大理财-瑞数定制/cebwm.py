"""光大理财 个人理财产品列表：ruyijs 原生环境通过瑞数挑战，由页面自己的脚本取数并翻页。

python cebwm.py
python cebwm.py --pages 3 --proxy http://127.0.0.1:7890 --output cebwm.json
python cebwm.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261022-004337 一致）：首页 412 -> 瑞数 js 生成 cookie ->
首页 200 -> 页面脚本 POST /eportal/ui（访问计数 + 产品列表，URL 参数与请求体由瑞数加密）-> 列表渲染。
翻页用可信点击“>”按钮，由页面脚本再次发出加密请求。脚本不替换任何浏览器 API，不注入 cookie。
退出码 0 表示每一页都渲染出产品行、对应请求均为 HTTP 200，且没有页面脚本异常。
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

URL = "https://www.cebwm.com/wealth/grlc/index.html"
NEXT = "document.querySelector('.lccp_page1 .page_right')"
# 第一张产品表：表头行之后每行一个产品。
READ_LIST = """(()=>{const rows=[...document.querySelectorAll('#finance_tb1 tbody tr')].filter(r=>!r.classList.contains('first_tr'));
  const cell=(r,i)=>{const c=r.cells[i];if(!c)return '';const d=c.querySelector('.datestyle');
    return (d?c.textContent.slice(0,c.textContent.length-d.textContent.length):c.textContent).trim()};
  return {ready:document.readyState,title:document.title,
    page:(document.getElementById('currentPage1')||{}).value||null,
    totalPages:(document.getElementById('totalpage1')||{}).textContent||null,
    totalCount:(document.querySelector('.total_count1')||{}).textContent||null,
    products:rows.map(r=>({name:cell(r,0),code:cell(r,1),minimum:cell(r,2),nav:cell(r,3),
      navDate:(r.cells[3]&&r.cells[3].querySelector('.datestyle')||{}).textContent||'',
      risk:cell(r,9)})).filter(p=>p.code)}})()"""


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


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

        def posts():
            return [row for row in call(context.net_log) if "/eportal/ui" in row["url"] and row["method"] == "POST"]

        call(context.configure_clock, "system")
        call(context.eval, "location.assign(" + json.dumps(URL) + ");undefined")
        state = None
        while True:
            advance()
            state = call(context.eval, READ_LIST)
            if state["ready"] == "complete" and state["products"]:
                break
        report["homepageStatuses"] = [row["status"] for row in call(context.net_log)
                                      if row["url"].split("?")[0] == URL]
        report["title"] = state["title"]
        report["totalCount"], report["totalPages"] = state["totalCount"], state["totalPages"]
        report["pages"].append({"page": state["page"], "products": state["products"]})
        for _ in range(args.pages - 1):
            before, sent = state["products"][0]["code"], len(posts())
            call(context.click, NEXT)
            while True:
                advance()
                state = call(context.eval, READ_LIST)
                if len(posts()) > sent and state["products"] and state["products"][0]["code"] != before:
                    break
            report["pages"].append({"page": state["page"], "products": state["products"]})
        requests = posts()
        report["eportalStatuses"] = [row["status"] for row in requests]
        report["cookieNames"] = call(context.eval, """document.cookie.split(';')
          .map(x=>x.trim().split('=')[0]).filter(Boolean)""")
        report["passed"] = (report["homepageStatuses"][-1:] == [200] and len(report["pages"]) == args.pages
                            and all(page["products"] for page in report["pages"])
                            and len({page["page"] for page in report["pages"]}) == args.pages
                            and all(status == 200 for status in report["eportalStatuses"])
                            and not report["scriptErrors"])
        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--pages", type=int, default=1, help="读取的页数（第 2 页起点击“>”翻页）")
    parser.add_argument("--timeout", type=float, default=90, help="总期限，秒")
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
