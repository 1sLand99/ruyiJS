"""Expedia TAAP（旅行社门户）登入：ruyijs+necko 原生环境由页面自己的 React SPA 完成设备指纹、
Arkose FunCaptcha 与登入请求，脚本只导航、在页面自己的表单里输入邮箱/密码并点击提交。

python expedia.py
python expedia.py --proxy http://127.0.0.1:7890 --output expedia.json
python expedia.py --direct --email you@example.com --password ****

流程（与 Firefox trace jscall-detail-desktop-20261025-134004 一致）：
  GET /taap/signin -> React SPA（bernie/core/graphql/vendor/app 等分包）-> iovation(iesnare) 设备画像
  -> POST /taap/identity/api/v1/pre-auth {email} -> {"data_exchange_blob":""}
  -> Arkose FunCaptcha POST /fc/gt2/public_key/<pk>（token 带 sup=1，抑制模式，无需可视拼图）
  -> POST /egcs/v2/collect（点击流）
  -> POST /taap/identity/api/v1/sign-in {email,password,challengeResponse:{arkoseToken...}} -> 202
  -> GET / 303 -> /account-not-associated（凭据有效、但该账号未关联 TAAP 代理身份：trace 的终态）

脚本不替换任何浏览器 API、不注入 cookie、不拼 Arkose token、不伪造设备 blob——这些都由页面脚本在
ruyijs 环境里算出，necko 负责真实的 TLS/cookie。退出码 0 表示：pre-auth 200、Arkose public_key 200、
collect 204、sign-in 202、最终顶层导航落在 /account-not-associated（标题 "Account Not Associated"），
且全程没有页面脚本异常。这是与 Firefox 逐字一致的业务终态（示例账号非 TAAP 账号）。
"""
import argparse
import json
import math
import os
import socket
import sys
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

URL = "https://www.expediataap.com.hk/taap/signin"
# Credentials come from arguments or the environment, never from source.
DEFAULT_EMAIL = os.environ.get("EXPEDIA_EMAIL", "")
DEFAULT_PASSWORD = os.environ.get("EXPEDIA_PASSWORD", "")
HOST = "www.expediataap.com.hk"
PRE_AUTH = "/taap/identity/api/v1/pre-auth"
SIGN_IN = "/taap/identity/api/v1/sign-in"
COLLECT = "/egcs/v2/collect"
ARKOSE = "/fc/gt2/public_key/"
FINAL_PATH = "/account-not-associated"

# 页面自己的登入表单：邮箱框、密码框、提交按钮。
READ = """(()=>{
  const q=s=>document.querySelector(s);
  const email=q('input[type=email],input[name=email],input#email,input[autocomplete=username]');
  const pwd=q('input[type=password]');
  return {ready:document.readyState,title:document.title,href:location.href,
          hasEmail:!!email,hasPwd:!!pwd};
})()"""

FILL = """(()=>{
  const set=(el,v)=>{const d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
    d.set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));};
  const email=document.querySelector('input[type=email],input[name=email],input#email,input[autocomplete=username]');
  const pwd=document.querySelector('input[type=password]');
  if(!email||!pwd)return false;
  set(email,%s);set(pwd,%s);return true;
})()"""

SUBMIT = """(()=>{
  const b=[...document.querySelectorAll('button')].find(b=>b.type==='submit')||
          [...document.querySelectorAll('button')].find(b=>/sign|登入|登錄|login|continue|繼續/i.test(b.textContent||''));
  if(b){b.click();return (b.textContent||'').trim().slice(0,40);}return null;
})()"""


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
                item = {"name": error.name, "message": error.message[:300]}
                if item not in report["scriptErrors"] and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(item)

        def log_rows():
            return call(context.net_log)

        def status_of(predicate):
            for row in log_rows():
                if predicate(row):
                    return row.get("status")
            return None

        call(context.configure_clock, "system")
        call(context.navigate, URL)

        state = {}
        for _ in range(500):  # 等 SPA 分包加载、渲染出登入表单
            advance()
            state = call(context.eval, READ)
            if state.get("ready") == "complete" and state.get("hasEmail") and state.get("hasPwd"):
                break
        report["title"] = state.get("title")
        if not (state.get("hasEmail") and state.get("hasPwd")):
            raise RuntimeError("登入表单未渲染出邮箱/密码框")

        if not call(context.eval, FILL % (json.dumps(args.email), json.dumps(args.password))):
            raise RuntimeError("无法向登入表单写入邮箱/密码")
        for _ in range(8):
            advance()

        clicked = call(context.eval, SUBMIT)
        report["submitButton"] = clicked
        if not clicked:
            raise RuntimeError("找不到登入提交按钮")

        for _ in range(900):  # 让页面完成 pre-auth / Arkose / sign-in，并跟随 303 顶层导航
            advance()
            here = call(context.eval, "location.href")
            if urlsplit(here).path == FINAL_PATH:
                break

        here = call(context.eval, "location.href + '|' + document.title")
        report["finalHref"], report["finalTitle"] = here.split("|", 1)

        rows = log_rows()
        report["flow"] = [{"method": r["method"], "path": urlsplit(r["url"]).path,
                           "host": urlsplit(r["url"]).hostname, "status": r.get("status")}
                          for r in rows if any(x in r["url"] for x in
                          (PRE_AUTH, SIGN_IN, ARKOSE, COLLECT, FINAL_PATH)) or urlsplit(r["url"]).path == "/"]

        report["preAuthStatus"] = status_of(lambda r: urlsplit(r["url"]).path == PRE_AUTH and r["method"] == "POST")
        report["arkoseStatus"] = status_of(lambda r: ARKOSE in r["url"] and r["method"] == "POST")
        report["collectStatus"] = status_of(lambda r: urlsplit(r["url"]).path == COLLECT and r["method"] == "POST")
        report["signInStatus"] = status_of(lambda r: urlsplit(r["url"]).path == SIGN_IN and r["method"] == "POST")
        report["finalStatus"] = status_of(lambda r: urlsplit(r["url"]).path == FINAL_PATH and r["method"] == "GET")

        report["passed"] = (report["preAuthStatus"] == 200
                            and report["arkoseStatus"] == 200
                            and report["collectStatus"] == 204
                            and report["signInStatus"] == 202
                            and report["finalStatus"] == 200
                            and urlsplit(report["finalHref"]).path == FINAL_PATH
                            and not report["scriptErrors"])
        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="登入邮箱（或环境变量 EXPEDIA_EMAIL）")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="登入密码（或环境变量 EXPEDIA_PASSWORD）")
    parser.add_argument("--timeout", type=float, default=240, help="总期限，秒")
    parser.add_argument("--output", type=Path, help="将 JSON 结果同时写入此文件")
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    if not args.email.strip() or not args.password:
        parser.error("邮箱与密码不能为空")

    selected = None if args.direct else (args.proxy or auto_proxy())
    report = {"status": "error", "transport": "ruyijs-page-parameters+necko-fetch", "proxy": selected or "direct", "scriptErrors": [], "flow": [], "passed": False}
    try:
        run(args, report)
        report["status"] = "ok" if report["passed"] else "failed"
    except (JSError, RuntimeError, TimeoutError) as error:
        report["error"] = str(error)[:300]
    finally:
        if args.output:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
