"""使用 ruyijs 搜索 BOSS 职位，并读取第一条职位详情。

python boss.py --query ai --city 101210100 --output boss-result.json
python boss.py --query Python --proxy http://127.0.0.1:7890
python boss.py --direct

依赖项目 python/ruyijs 与 dist/js.exe；可用 RUYIJS_SHELL 指定运行时。
退出码 0 表示列表及首条详情均 HTTP 200、业务 code 0，且职位 ID 一致。
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
from time import monotonic, time
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
# The page context remains the parameter/token producer; API traffic uses the
# same Necko session that the runtime uses internally, without page fetch waits.
sys.path.insert(0, str(ROOT / "examples" / "google"))
from google_search import NeckoSession
ORIGIN = "https://www.zhipin.com"
DEFAULT_QUERY = "ai"
DEFAULT_CITY = "101210100"
DEFAULT_PROXY = None
DEFAULT_OUTPUT = None
ENTRY_PATH = "/hangzhou/?seoRefer=index"
ENVIRONMENT = {"screen": {"width": 2560, "height": 1440,
                           "availWidth": 2560, "availHeight": 1392},
               "viewport": {"width": 1280, "height": 955},
               "locale": {"timezone": "Asia/Shanghai"}}


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


class SearchSession:
    def __init__(self, context, deadline, js_error, report, necko):
        self.context, self.deadline, self.necko = context, deadline, necko
        self.js_error, self.report = js_error, report

    def call(self, method, *args, **kwargs):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("搜索流程达到总时间限制")
        self.context.timeout = remaining
        return method(*args, **kwargs)

    def evaluate(self, source):
        return self.call(self.context.eval, source)

    def advance(self):
        try:
            self.call(self.context.advance, 25, max_tasks=1)
        except self.js_error as error:
            item = {"name": error.name, "message": error.message[:300]}
            if item not in self.report["scriptErrors"] and len(self.report["scriptErrors"]) < 10:
                self.report["scriptErrors"].append(item)

    def fetch(self, url, form=None):
        headers = [("Accept", "application/json, text/plain, */*")]
        if urlsplit(url).path.startswith("/wapi/"):
            headers.append(("X-Requested-With", "XMLHttpRequest"))
        cookie = self.context.cookie_header(url, source_url=ORIGIN)
        if cookie:
            headers.append(("Cookie", cookie))
        method, body = "GET", b""
        if form is not None:
            method, body = "POST", urlencode(form).encode("utf-8")
            headers.append(("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8"))
        status, response_headers, payload, version = self.necko.send(method, url, headers, body)
        if urlsplit(url).hostname != "www.zhipin.com":
            raise RuntimeError("请求被重定向到其他域名")
        # Let the existing jar consume Set-Cookie without exposing a page API:
        # resource responses follow the normal HTTP cookie commit path.
        if any(name.lower() == "set-cookie" for name, _ in response_headers):
            self.context.put_resource(url, payload, status=status, headers=response_headers)
            self.evaluate("fetch(%s,{credentials:'include'}).then(()=>0).catch(()=>0);undefined" %
                          json.dumps(url))
            self.call(self.context.checkpoint)
        return {"status": status, "url": url, "contentType": next(
            (value for name, value in response_headers if name.lower() == "content-type"), None),
                "text": payload.decode("utf-8", "replace"), "http": version}

    def token(self):
        return self.evaluate("document.cookie.split(';').map(s=>s.trim())"
                             ".find(s=>s.startsWith('__zp_stoken__='))?.slice(14).trim() || ''")

    def process_security(self, config, callback):
        if not isinstance(config, dict) or any(not config.get(k) for k in ("seed", "ts", "name")):
            raise RuntimeError("code 37 响应缺少验证页参数")
        params = {k: config[k] for k in ("seed", "ts", "name")}
        params.update(callbackUrl=callback, srcReferer=callback, appName="zhipin_geek_spa_web")
        previous = self.token()
        page = self.fetch(ORIGIN + "/web/passport/zp/security.html?" + urlencode(params))
        attempt = {"httpStatus": page["status"], "tokenUpdated": False}
        self.report["security"].append(attempt)
        if page["status"] != 200 or "text/html" not in (page["contentType"] or "").lower():
            raise RuntimeError(f"验证页返回 HTTP {page['status']} 或非 HTML 内容")
        try:
            self.call(self.context.load_page, page["url"], page["text"])
        except self.js_error as error:
            self.report["scriptErrors"].append({"name": error.name, "message": error.message[:300]})
        for _ in range(300):
            current = self.token()
            if current and current != previous:
                attempt["tokenUpdated"] = True
                # The security page navigates back on its own after updating the token
                # (callback&_security_check=1); let that navigation settle first.
                last, stable = None, 0
                for _ in range(200):
                    here = self.evaluate("location.href + '|' + document.readyState")
                    stable = stable + 1 if here == last else 0
                    last = here
                    if stable >= 8 and here.endswith("|complete"):
                        break
                    self.advance()
                if "/web/passport/" in urlsplit(self.evaluate("location.href")).path:
                    self.evaluate("history.replaceState(null,''," + json.dumps(callback) + ");undefined")
                return
            if "/web/passport/" not in urlsplit(self.evaluate("location.href")).path:
                raise RuntimeError("验证页已结束，但会话令牌未更新")
            self.advance()
        raise RuntimeError("验证页达到任务数量限制，会话令牌未更新")

    def request_json(self, path, callback, form=None, params=None):
        for attempt in range(3):
            reply = self.fetch(ORIGIN + path + "?" + urlencode(dict(params or {}, _=int(time() * 1000))), form)
            try:
                data = json.loads(reply["text"])
            except ValueError:
                raise RuntimeError(f"{path}: HTTP {reply['status']}，响应不是 JSON") from None
            if not isinstance(data, dict):
                raise RuntimeError(f"{path}: 响应不是 JSON 对象")
            code = data.get("code")
            self.report["requests"].append({"path": path, "httpStatus": reply["status"], "code": code})
            if reply["status"] != 200:
                raise RuntimeError(f"{path}: HTTP {reply['status']}")
            if type(code) is int and code == 0:
                return data.get("zpData")
            if code == 37 and attempt < 2:
                self.process_security(data.get("zpData"), callback)
                continue
            raise RuntimeError(f"{path}: 业务 code {code}: " + str(data.get("message", ""))[:200])


def search(session, args):
    callback = ORIGIN + "/web/geek/jobs?" + urlencode({"city": args.city, "query": args.query})
    session.call(session.context.load_page, callback, "<!doctype html><html><body></body></html>")
    entry = session.fetch(ORIGIN + ENTRY_PATH)
    session.report["entryHttpStatus"] = entry["status"]
    if entry["status"] != 200:
        raise RuntimeError(f"入口页返回 HTTP {entry['status']}")
    form = dict(page=args.page, pageSize=15, city=args.city, expectInfo="", query=args.query,
                multiSubway="", multiBusinessDistrict="", position="", jobType="", salary="",
                experience="", degree="", industry="", scale="", stage="", scene=1, encryptExpectId="")
    data = session.request_json("/wapi/zpgeek/search/joblist.json", callback, form)
    jobs = data.get("jobList") if isinstance(data, dict) else None
    if not isinstance(jobs, list) or not jobs or any(not isinstance(j, dict) for j in jobs):
        raise RuntimeError("搜索响应没有非空职位列表")
    session.report["jobs"] = [{k: j[k] for k in ("jobName", "salaryDesc", "brandName", "cityName",
        "areaDistrict", "jobExperience", "jobDegree", "encryptJobId") if k in j} for j in jobs]
    first = jobs[0]
    if any(not isinstance(first.get(k), str) or not first[k].strip()
           for k in ("jobName", "encryptJobId", "securityId", "lid")):
        raise RuntimeError("第一条职位缺少名称、ID、securityId 或 lid")
    detail = session.request_json("/wapi/zpgeek/job/detail.json", callback,
                                  params={k: first[k] for k in ("securityId", "lid")})
    info = detail.get("jobInfo") if isinstance(detail, dict) else None
    if not isinstance(info, dict) or not info.get("jobName") or not info.get("postDescription"):
        raise RuntimeError("详情响应缺少职位名称或描述")
    session.report["detail"] = {k: info[k] for k in ("jobName", "salaryDesc", "degreeName",
        "experienceName", "postDescription", "encryptId") if k in info}
    if info.get("encryptId") != first["encryptJobId"]:
        raise RuntimeError("详情职位 ID 与第一条搜索结果不一致")
    session.report["status"] = "passed"


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", default=DEFAULT_QUERY, help="查询词，默认 ai")
    parser.add_argument("--city", default=DEFAULT_CITY, help="城市代码，默认杭州 101210100")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=90, help="整个流程的时间限制，秒")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="将 JSON 结果同时写入此文件")
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", default=DEFAULT_PROXY, help="HTTP(S) 代理；默认环境变量、本机 7890、直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    args = parser.parse_args()
    if not args.query.strip() or not args.city.isdigit() or args.page < 1:
        parser.error("查询词须非空，城市代码须是数字，页码须 >= 1")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 须是正有限数")
    selected = None if args.direct else (args.proxy or auto_proxy())
    proxy_label = "direct"
    if selected:
        try:
            proxy_url = urlsplit(selected)
            if proxy_url.scheme not in ("http", "https") or not proxy_url.hostname:
                raise ValueError("代理须使用带主机名的 http:// 或 https:// URL")
            port = proxy_url.port
            host = proxy_url.hostname
            if ":" in host:
                host = "[" + host + "]"
            proxy_label = proxy_url.scheme + "://" + host + (":" + str(port) if port else "")
        except ValueError as error:
            parser.error(str(error))
    started = monotonic()
    report = {"status": "error", "transport": "ruyijs-parameters+necko", "query": args.query, "city": args.city, "page": args.page,
              "proxy": proxy_label, "requests": [], "security": [], "jobs": [], "scriptErrors": []}
    context = None
    try:
        from ruyijs import Context, JSError
        context = Context(proxy=selected, timeout=args.timeout, environment=ENVIRONMENT)
        necko = NeckoSession(selected)
        session = SearchSession(context, started + args.timeout, JSError, report, necko)
        session.call(context.configure_clock, "system")
        search(session, args)
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)[:500]
    finally:
        if 'necko' in locals():
            try:
                necko.close()
            except Exception as error:
                report.setdefault("closeErrors", []).append(type(error).__name__ + ": " + str(error)[:200])
        if context:
            try:
                context.timeout = 5
                context.close()
            except Exception as error:
                report.update(status="error", closeError=type(error).__name__ + ": " + str(error)[:200])
    report["elapsedSeconds"] = round(monotonic() - started, 3)
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
        except OSError as error:
            report.update(status="error", outputError=str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
