"""Capture Firefox and current ruyijs surface evidence on local HTTP documents."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

from browser import Firefox
from fixture import Fixture, HTML, FRAME
from report import write_report

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(folder, name, value):
    path = folder / (name + ".json")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    summary = {"capture": name}
    if "globals" in value:
        summary.update(globals=len(value["globals"]["properties"]),
                       interfaces=len(value["interfaces"]), errors=len(value["errors"]))
    print(json.dumps(summary), flush=True)


def expressions(probe, focused=False):
    source = "(" + probe + ")(w)"
    if focused:
        source = "w.eval(" + json.dumps("(" + probe + ")(window)") + ")"
        source = "({metadata:{url:w.location.href,userAgent:w.navigator.userAgent," + \
            "secureContext:w.isSecureContext,crossOriginIsolated:w.crossOriginIsolated},value:" + source + "})"
    return {name: "JSON.stringify((w=>" + source + ")(" + window + "))"
            for name, window in {"main": "window",
                "frame": "document.querySelector('iframe').contentWindow"}.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firefox", type=Path,
        default=Path("D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe"))
    parser.add_argument("--shell", type=Path, default=ROOT / "dist/js.exe")
    parser.add_argument("--probe", type=Path,
                        help="JS function expression (window => JSON value), run in each target realm")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" /
                        ("firefox-parity-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        parser.error("--output must stay under project artifacts")
    output.mkdir(parents=True, exist_ok=False)
    probe_path = args.probe or Path(__file__).with_name("surface.js")
    probe = probe_path.read_text("utf-8")
    source = expressions(probe, focused=bool(args.probe))
    metadata = {"createdUTC": datetime.now(timezone.utc).isoformat(),
                "firefox": str(args.firefox.resolve()), "firefoxSHA256": digest(args.firefox),
                "shell": str(args.shell.resolve()), "shellSHA256": digest(args.shell),
                "probeSHA256": digest(probe_path), "fixtures": {"main": HTML, "frame": FRAME},
                "scope": "window, constructors, prototypes, selected instances; same-origin iframe"}
    with Fixture() as fixture:
        metadata["origins"] = fixture.origins
        with Firefox(args.firefox, output / "profile") as browser:
            metadata["capabilities"] = browser.capabilities
            for mode, origin in fixture.origins.items():
                browser.navigate(origin + "/")
                for realm, expression in source.items():
                    value = json.loads(browser.evaluate(expression))
                    save(output, f"firefox-{mode}-{realm}", value)
        for mode, origin in fixture.origins.items():
            with Context(shell=args.shell, timeout=120) as context:
                context.put_resource(origin + "/frame", FRAME,
                                     headers=[["Content-Type", "text/html; charset=utf-8"]])
                context.load_page(origin + "/", HTML)
                for realm, expression in source.items():
                    value = json.loads(context.eval(expression))
                    save(output, f"ruyijs-{mode}-{realm}", value)
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
    counts = write_report(output) if not args.probe else {}
    print(json.dumps({"output": str(output), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
