"""Stream a Firefox domtrace run into a compact parity inventory.

This deliberately reads JSONL line by line; it never loads the ~1 GB trace.
"""
from __future__ import annotations

import argparse
import collections
import json
import urllib.parse
from pathlib import Path


def safe_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    parts = ["{opaque}" if len(part) > 48 else part for part in parsed.path.split("/")]
    path = "/".join(parts)
    if parsed.netloc == "fundingchoicesmessages.google.com" and path.startswith("/f/"):
        path = "/f/{opaque}"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def read_jsonl(path: Path, callback):
    lines = 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_no, line in enumerate(stream, 1):
            lines += 1
            try:
                callback(json.loads(line), line_no)
            except json.JSONDecodeError:
                callback({"type": "__json_error__"}, line_no)
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--parity", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.trace
    result = {"schema": "ruyijs.fp-trace-inventory.v1", "trace": str(root)}
    files, type_counts, hosts = [], collections.Counter(), collections.Counter()
    api, api_by_site, evidence, scripts, writers = collections.Counter(), collections.defaultdict(collections.Counter), {}, {}, {}
    request_hosts, env_surfaces = collections.Counter(), {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        kind = directory.name
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            item = {"path": str(path.relative_to(root)), "bytes": path.stat().st_size}
            if path.suffix == ".jsonl":
                def consume(obj, line_no, kind=kind, path=path):
                    typ = obj.get("type", obj.get("kind", ""))
                    type_counts[typ] += 1
                    if typ == "__json_error__":
                        source_kinds["json_errors"] += 1
                    stack = obj.get("stack") or []
                    source = next((x.get("file", x.get("url", ""))
                                   for x in stack if x.get("file", x.get("url", "")).startswith(("http://", "https://"))), "")
                    if source:
                        host = urllib.parse.urlsplit(source).netloc
                        hosts[host] += 1
                    if kind == "domtrace":
                        if typ in ("get", "set", "call") and source:
                            key = "%s|%s|%s" % (obj.get("interface"), obj.get("member"), typ)
                            api[key] += 1
                            api_by_site[host][key] += 1
                            evidence.setdefault(key, {"file": str(path.relative_to(root)), "line": line_no,
                                                       "seq": obj.get("seq"), "source": safe_url(source)})
                        if typ in ("fetch", "xhrNative", "request_construct"):
                            url = obj.get("url", "")
                            if url:
                                request_hosts[urllib.parse.urlsplit(url).netloc] += 1
                        if typ == "script_root" and obj.get("url", "").startswith(("http://", "https://")):
                            url = obj["url"]
                            scripts.setdefault(safe_url(url), {"file": str(path.relative_to(root)), "line": line_no,
                                                     "kind": obj.get("script_kind")})
                    if typ == "domtrace_writer_stats":
                        writers[str(obj.get("pid", ""))] = {k: obj.get(k) for k in
                            ("attempted", "enqueued", "dropped_full", "dropped_oom", "io_errors")}
                item["jsonl_lines"] = read_jsonl(path, consume)
            elif kind == "env" and path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    surface = {"global": data.get("global"), "pid": data.get("pid"),
                               "process_type": data.get("processType"),
                               "interfaces": len(data.get("interfaces", {})),
                               "window_props": len(data.get("window_props", [])),
                               "disabled": len(data.get("disabled", []))}
                    item["surface"] = surface
                    env_surfaces[item["path"]] = surface
                except (OSError, json.JSONDecodeError):
                    item["surface"] = "unreadable"
            files.append(item)
    result.update({"files": files, "record_count": sum(type_counts.values()),
                   "record_types": dict(type_counts), "http_hosts": hosts,
                   "dom_api_count": len(api), "dom_apis": dict(api),
                   "api_evidence": evidence, "apis_by_caller_host":
                       {host: dict(methods) for host, methods in api_by_site.items()},
                   "script_roots": scripts, "environment_surfaces": env_surfaces,
                   "writer_stats": writers, "request_hosts": request_hosts,
                   "source_boundaries": {
                       "web_hosts": sorted(hosts), "web_script_filter": "web",
                       "google_host_observed": "www.google.com" in request_hosts,
                       "google_search_observed": any("/search" in url for url in scripts),
                       "browser_scan_observed": any("browserscan.net" in s for s in scripts),
                   }})
    if args.parity:
        parity = {}
        run = args.parity
        ff = json.loads((run / "firefox.json").read_text(encoding="utf-8"))
        ry = json.loads((run / "ruyijs.json").read_text(encoding="utf-8"))
        differing = sorted(k for k in set(ff) | set(ry) if ff.get(k, "<missing>") != ry.get(k, "<missing>"))
        parity.update({"run": str(run), "keys_firefox": len(ff), "keys_ruyijs": len(ry),
                       "matches": len(ff) - len([k for k in differing if k in ff]),
                       "differences": len(differing), "difference_keys": differing})
        parity["groups"] = dict(collections.Counter(k.split(".", 1)[0] for k in differing))
        result["parity"] = parity
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
