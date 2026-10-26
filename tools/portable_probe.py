"""Probe a relocated package with the package's own Python and runtime."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        self.__class__.requests.append(self.path)
        body = b"portable-http-ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def main():
    package = Path(sys.argv[1]).resolve()
    if any(key.upper().startswith("RUYIJS") for key in os.environ):
        raise AssertionError("RUYIJS environment override leaked into probe")
    if "PYTHONPATH" in os.environ:
        raise AssertionError("PYTHONPATH leaked into probe")
    sys.path.insert(0, str(package / "python"))
    from ruyijs import Context, JSError
    import ruyijs

    assert Path(ruyijs.__file__).resolve().is_relative_to(package)
    assert Path(sys.executable).resolve() == package / "vendor/necko-derived/python/python.exe"
    with Context(timeout=20) as context:
        assert context.shell == package / "dist/js.exe"
        assert context.eval("40 + 2") == 42
        assert context.eval("globalThis.answer = '迁移 空格'; answer") == "迁移 空格"
        assert context.eval("answer") == "迁移 空格"
        try:
            context.eval("throw new Error('portable')")
        except JSError:
            pass
        else:
            raise AssertionError("JavaScript exception did not cross the binding")
        assert context.eval("6 * 7") == 42

    with Context(timeout=20) as context:
        context.configure_clock("logical", epoch_ms=1700000000000)
        context.eval("globalThis.order=[];setTimeout(()=>{order.push('timer');"
                     "queueMicrotask(()=>order.push('microtask'))},10);undefined")
        assert context.advance(10)["pending"] == 0
        assert context.eval("order") == ["timer", "microtask"]
        context.put_resource("/portable", b"\x00\xff", status=201)
        resource = context.get_resource("/portable")
        assert resource["body"] == b"\x00\xff" and resource["status"] == 201
        assert context.eval("new Headers([['X','one'],['x','two']]).get('x')") == "one, two"
        assert context.clear_resources() == {"resources": 0, "bytes": 0}

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/portable"
        with Context(timeout=20) as context:
            value = context.eval("(() => { const x = new XMLHttpRequest(); "
                                 f"x.open('GET', {json.dumps(url)}, false); x.send(); "
                                 "return [x.status, x.responseText]; })()")
            assert value == [200, "portable-http-ok"], value
            context.eval("globalThis.reply=null;fetch(" + json.dumps(url) +
                         ").then(r=>r.text()).then(t=>{reply=t});undefined")
            context.checkpoint()
            assert context.eval("reply") == "portable-http-ok"
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({"python": "passed", "exception_recovery": "passed",
                      "http": "passed", "fetch": "passed", "http_requests": Handler.requests,
                      "scheduling": "passed", "resources_and_headers": "passed",
                      "embedded_python": sys.version.split()[0]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
