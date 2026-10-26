"""Generate a durable deduplicated surface-gap index from existing captures."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from owners import owner_record, source_index

ROOT = Path(__file__).resolve().parents[2]


def canonical_objects(capture):
    objects = {"WindowGlobal": capture["globals"], **capture["interfaces"]}
    for name, value in capture["chains"].items():
        objects.setdefault(name, value)
    # Explicit instance own members are retained once; duplicate Window is excluded.
    for name in ("navigator", "document", "location", "history", "screen", "performance",
                 "crypto", "console", "localStorage", "sessionStorage", "customElements", "visualViewport"):
        if name in capture["instances"] and capture["instances"][name]["properties"]:
            objects["instance:" + name] = capture["instances"][name]
    return objects


def build(folder):
    metadata = json.loads((folder / "metadata.json").read_text("utf-8"))
    sources = source_index(ROOT)
    entries, contexts = {}, {}

    def add(kind, object_name, property_name, mode, firefox, ruyijs=None):
        target = object_name + ("." + property_name if property_name else "")
        key = kind + ":" + target
        if key not in entries:
            entries[key] = {"kind": kind, "target": target,
                **owner_record(object_name, property_name, sources), "contexts": {}}
        if kind in ("missing_object", "extra_object"):
            def shape(value):
                return None if value is None else {"members": sorted(value["properties"]),
                                                   "chain": value.get("chain")}
            firefox, ruyijs = shape(firefox), shape(ruyijs)
        elif kind == "property_order":
            def order(value):
                return {"count": len(value), "sha256": sha256(json.dumps(value).encode()).hexdigest()}
            firefox, ruyijs = order(firefox), order(ruyijs)
        entries[key]["contexts"][mode] = {"firefox": firefox, "ruyijs": ruyijs}

    for mode in ("http", "secure"):
        left_capture = json.loads((folder / f"firefox-{mode}-main.json").read_text("utf-8"))
        right_capture = json.loads((folder / f"ruyijs-{mode}-main.json").read_text("utf-8"))
        left, right = canonical_objects(left_capture), canonical_objects(right_capture)
        contexts[mode] = {"firefox": left_capture["metadata"], "ruyijs": right_capture["metadata"],
            "firefoxGlobals": len(left["WindowGlobal"]["properties"]),
            "ruyijsGlobals": len(right["WindowGlobal"]["properties"])}
        for name in sorted(set(left) - set(right)):
            add("missing_object", name, "", mode, left[name])
        for name in sorted(set(right) - set(left)):
            add("extra_object", name, "", mode, None, right[name])
        for name in sorted(set(left) & set(right)):
            lp, rp = left[name]["properties"], right[name]["properties"]
            for member in sorted(set(lp) - set(rp)):
                add("missing_global" if name == "WindowGlobal" else "missing_member", name, member, mode, lp[member])
            for member in sorted(set(rp) - set(lp)):
                add("extra_global" if name == "WindowGlobal" else "extra_member", name, member, mode, None, rp[member])
            for member in sorted(set(lp) & set(rp)):
                if lp[member] != rp[member]:
                    add("descriptor", name, member, mode, lp[member], rp[member])
            if left[name].get("chain") != right[name].get("chain"):
                add("prototype_chain", name, "", mode, left[name].get("chain"), right[name].get("chain"))
            common = set(lp) & set(rp)
            lo = [key for key in left[name]["order"] if key in common]
            ro = [key for key in right[name]["order"] if key in common]
            if lo != ro:
                add("property_order", name, "", mode, lo, ro)
    values = sorted(entries.values(), key=lambda row: (row["owner"], row["kind"], row["target"]))
    counts = dict(sorted(Counter(row["kind"] for row in values).items()))
    owners = {}
    for row in values:
        owners.setdefault(row["owner"], Counter())[row["kind"]] += 1
    return {"schema": 1, "generatedFrom": folder.relative_to(ROOT).as_posix(),
        "baseline": metadata, "contexts": contexts, "uniqueDifferenceCount": len(values),
        "counts": counts, "owners": {name: dict(count) for name, count in sorted(owners.items())},
        "deduplication": "Main realms only; canonical interface+prototype names; chains merged; no element instance repetitions. Dynamic WindowGlobal.0 retained as indexed frame exposure.",
        "completion": "baseline_only; no behavior, worker, cross-origin or permissions completion implied",
        "entries": values}


def write_docs(data, destination):
    cap = data["baseline"]["capabilities"]["capabilities"]
    counts = data["counts"]
    lines = ["# Firefox 接口对齐基线", "",
        f"2026-10-18 实测 Firefox **{cap['browserVersion']}**，build ID **{cap['moz:buildID']}**。",
        "旧 owner 文档中的 Firefox 157 与旧测试路径保留为历史记录；本轮以此 158 实际产物为准。",
        "当前状态是缺口基线，尚未声明完整对齐。Worker、跨源 iframe、权限授予/拒绝、设备与事件行为未覆盖。", "",
        "完整机器索引：[firefox-parity-baseline.json](../profiles/firefox-parity-baseline.json)。",
        f"完整采集：[report.md](../{data['generatedFrom']}/report.md)。", "",
        "## 唯一缺口统计", "",
        "对普通 HTTP 与安全 localhost 的主 realm 取并集；同一目标的环境差异存入 contexts。",
        "构造器/原型只计一次，链表复用同名对象；不重复计 iframe 和元素实例继承的成员。",
        "WindowGlobal.0 是 iframe 索引属性能力，仍单独保留。缺失对象与它的 Window 暴露是不同检查点，",
        "因此下表是去重后的检查目标数量，不是可直接相加的独立浏览器 API 数量。", "",
        "| 检查类别 | 唯一目标数 |", "| --- | ---: |"]
    for kind, count in counts.items():
        lines.append(f"| {kind} | {count} |")
    lines.extend(["", "## 按既有 owner 路由", "",
        "路由优先采用源码既有接口字符串与原 owner 文档。新家族只有候选边界，实施前仍需记录",
        "state/factory/installer/realm/C-Python parity 与测试；owner_review 表示尚未明确归属。",
        "禁止从此索引生成 JS 覆盖层或批量空函数。每次推进单一 API 域。", "",
        "| owner | missing global | missing member | descriptor | missing object |", "| --- | ---: | ---: | ---: | ---: |"])
    for owner, values in data["owners"].items():
        lines.append(f"| {owner} | {values.get('missing_global',0)} | {values.get('missing_member',0)} | {values.get('descriptor',0)} | {values.get('missing_object',0)} |")
    lines.extend(["", "## 环境与行为验收", "",
        "普通 HTTP 的真实 Firefox 未暴露的 secure-only API 在 ruyijs 仍有额外暴露；安全上下文",
        "缺失清单另存 contexts，不能以全局统一安装代替两种环境。每个目标还要验证",
        "descriptor、constructor/prototype、非法 receiver、主/子 realm 工厂、状态来源与实际生产调用路径。", "",
        "当前第一片聚焦 DocumentModel ParentNode.replaceChildren：方法存在不代表行为一致。",
        "该行为问题不由表面缺失统计自动识别，单独用真实 Firefox 同 JS focused 测试记录。",
        "生产修改仍需实际 C DLL 重建及身份、Python/C 路径、必要回归与同部署 Google 重放。", "",
        "采集：`python -B tools/firefox_parity/collect.py`；",
        "聚焦：`python -B tools/firefox_parity/collect.py --probe tests/firefox_parity/replace_children.js`。",
        "重新生成索引：`python -B tools/firefox_parity/index.py CAPTURE_DIRECTORY`。", ""])
    destination.write_text("\n".join(lines), "utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    data = build(args.capture.resolve())
    target = ROOT / "profiles/firefox-parity-baseline.json"
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    write_docs(data, ROOT / "docs/FIREFOX_ALIGNMENT.md")
    print(json.dumps({"unique": data["uniqueDifferenceCount"], "counts": data["counts"],
                      "bytes": target.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
