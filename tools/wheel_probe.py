"""Release integration probe: python -I -B wheel_probe.py [site-packages].

Run outside the checkout after installing the wheel. An explicit site-packages
path also permits probing the same installed wheel from an embedded Python.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from threading import Thread
from time import monotonic


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        self.requests.append(self.path)
        body = b"installed-wheel-http-ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


TLS_PROBE = '''
import json, ssl, sys
from pathlib import Path
import certifi, necko
from necko._nss import Context
from necko._transport import _load_library
root = Path(sys.argv[1]).resolve()
assert Path(sys.executable).resolve().is_relative_to(root)
assert Path(necko.__file__).resolve().is_relative_to(root)
assert Path(certifi.where()).resolve().is_relative_to(root)
tls = ssl.create_default_context(cafile=certifi.where())
assert tls.verify_mode == ssl.CERT_REQUIRED and tls.check_hostname
assert tls.cert_store_stats()["x509_ca"] > 0
native = _load_library()
assert native.necko_tls_nss_version() == b"3.130"
assert Context(True, None).store is not None
print(json.dumps({"tls_ca_count": tls.cert_store_stats()["x509_ca"],
                  "nss": "3.130", "firefox_roots": "passed"}))
'''


def main():
    assert sys.flags.isolated, "Run with -I"
    assert not Path.cwd().resolve().is_relative_to(Path(__file__).resolve().parents[1]), "Run outside checkout"
    for key in list(os.environ):
        if key.upper().startswith(("RUYIJS", "PYTHON", "NECKO")):
            del os.environ[key]
    sys.dont_write_bytecode = True
    expected = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if expected:
        assert expected.name == "site-packages", expected
        sys.path.insert(0, str(expected))
    import ruyijs
    from ruyijs import Context, JSError, UNDEFINED

    package = Path(ruyijs.__file__).resolve().parent
    assert package.parent.name == "site-packages", package
    if expected:
        assert package.parent == expected, package
    source_version = Path(__file__).resolve().parents[1] / "python/ruyijs/_version.py"
    expected_version = re.search(r'__version__ = "([^"]+)"', source_version.read_text(encoding="utf-8"))[1]
    assert ruyijs.__version__ == metadata.version("ruyijs") == expected_version
    distribution = metadata.distribution("ruyijs")
    assert "Tag: py3-none-win_amd64" in distribution.read_text("WHEEL")
    runtime = ruyijs.get_runtime_path().resolve()
    assert runtime == package / "_runtime", runtime
    inventory = set()
    for entry in (runtime / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = entry.split("  ", 1)
        item = (runtime / name).resolve()
        assert item.is_relative_to(runtime) and name not in inventory, name
        assert hashlib.sha256(item.read_bytes()).hexdigest() == digest, name
        inventory.add(name)
    actual = {p.relative_to(runtime).as_posix() for p in runtime.rglob("*")
              if p.is_file() and p.name != "SHA256SUMS" and "__pycache__" not in p.parts}
    assert actual == inventory, (actual - inventory, inventory - actual)
    assert "dist/js.exe" in inventory
    embedded = runtime / "vendor/necko-derived/python/python.exe"
    assert embedded.is_file()

    with Context(timeout=20) as context:
        assert context.shell == runtime / "dist/js.exe"
        context.eval("let count = 40")
        assert context.eval("count += 2") == 42
        assert context.eval("count") == 42
        assert context.eval("undefined") is UNDEFINED
        assert context.eval("9007199254740993n") == 9007199254740993
        context.set("config", {"offset": 2})
        add = context.eval("value => value + config.offset", to_py=False)
        assert add(40) == 42
        context.expose(lambda a, b: a + b, "hostAdd")
        assert context.eval("hostAdd(20, 22)") == 42
        try:
            context.eval("throw new TypeError('wheel probe')", filename="probe.js")
        except JSError as error:
            assert error.name == "TypeError" and error.message == "wheel probe"
        else:
            raise AssertionError("Expected JavaScript error")
        assert context.eval("6 * 7") == 42

    with Context(timeout=20) as context:
        context.configure_fingerprint({"navigator": {"language": "zh-CN"},
                                       "screen": {"width": 1920}})
        context.configure_clock("logical", epoch_ms=1700000000000)
        context.put_resource("https://example.test/app.js", "window.answer = 42")
        context.load_page("https://example.test/",
                          '<script src="/app.js"></script><p id="x">hello</p>')
        assert context.eval("[navigator.language, screen.width]") == ["zh-CN", 1920]
        assert context.eval("[answer, document.querySelector('#x').textContent]") == [42, "hello"]
        context.eval("globalThis.order=[]; setTimeout(() => {order.push('timer');"
                     "queueMicrotask(() => order.push('microtask'))}, 10); undefined")
        context.advance(10)
        assert context.eval("order") == ["timer", "microtask"]
        assert context.eval("Date.now()") == 1700000000010

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        with Context(timeout=20) as context:
            context.load_page(origin + "/", "")
            value = context.eval("(() => {const x = new XMLHttpRequest();"
                                 "x.open('GET', '/xhr', false); x.send();"
                                 "return [x.status, x.responseText]})()")
            assert value == [200, "installed-wheel-http-ok"], value
            context.eval("globalThis.reply=null;fetch('/fetch').then(async r=>"
                         "[r.status,await r.text()]).then(v=>{reply=v})"
                         ".catch(e=>{reply={error:String(e)}});undefined")
            deadline = monotonic() + 20
            while context.eval("reply") is None:
                assert monotonic() < deadline, "fetch deadline exceeded"
                context.advance(10)
            assert context.eval("reply") == [200, "installed-wheel-http-ok"]
        assert Handler.requests == ["/xhr", "/fetch"], Handler.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    child = subprocess.run([str(embedded), "-I", "-B", "-c", TLS_PROBE, str(runtime)],
                           capture_output=True, text=True, timeout=30, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    result = {"version": ruyijs.__version__, "python": sys.version.split()[0],
              "module": str(package), "runtime": str(runtime), "runtime_files": len(inventory),
              "javascript": "passed", "dom": "passed", "timers": "passed",
              "xhr": "passed", "fetch": "passed", "tls": json.loads(child.stdout)}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
