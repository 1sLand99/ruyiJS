"""Compare captured descriptors without treating interface presence as behavior parity."""
import json
from pathlib import Path


def object_diff(path, reference, current, rows):
    if reference.get("chain") != current.get("chain"):
        rows.append({"kind": "prototype_chain", "path": path,
                     "firefox": reference.get("chain"), "ruyijs": current.get("chain")})
    left, right = reference["properties"], current["properties"]
    for name in sorted(set(left) - set(right)):
        rows.append({"kind": "missing_property", "path": path + "." + name,
                     "firefox": left[name]})
    for name in sorted(set(right) - set(left)):
        rows.append({"kind": "extra_property", "path": path + "." + name,
                     "ruyijs": right[name]})
    for name in sorted(set(left) & set(right)):
        if left[name] != right[name]:
            rows.append({"kind": "descriptor", "path": path + "." + name,
                         "firefox": left[name], "ruyijs": right[name]})
    common = set(left) & set(right)
    order1 = [key for key in reference["order"] if key in common]
    order2 = [key for key in current["order"] if key in common]
    if order1 != order2:
        rows.append({"kind": "property_order", "path": path,
                     "firefox": order1, "ruyijs": order2})


def compare(reference, current):
    rows = []
    object_diff("window", reference["globals"], current["globals"], rows)
    for section in ("interfaces", "instances", "chains"):
        left, right = reference[section], current[section]
        for name in sorted(set(left) - set(right)):
            rows.append({"kind": "missing_object", "path": section + "." + name,
                         "firefoxPropertyCount": len(left[name]["properties"])})
        for name in sorted(set(right) - set(left)):
            rows.append({"kind": "extra_object", "path": section + "." + name})
        for name in sorted(set(left) & set(right)):
            object_diff(section + "." + name, left[name], right[name], rows)
    counts = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return {"counts": counts, "differences": rows,
            "firefoxErrors": reference["errors"], "ruyijsErrors": current["errors"]}


def write_report(folder):
    folder = Path(folder)
    metadata = json.loads((folder / "metadata.json").read_text("utf-8"))
    report, lines = {}, ["# Firefox / ruyijs surface comparison", "",
        "These captures describe observable own properties, descriptors and prototype chains.",
        "Presence does not prove method behavior, receiver checks, permissions or event semantics.",
        "Counts include repeated views of the same owner; they are not unique API counts.", "",
        f"Firefox: `{metadata['firefox']}`", f"ruyijs SHA256: `{metadata['shellSHA256']}`", "",
        "| Context | Firefox globals | ruyijs globals | Missing | Extra | Descriptor | Order | Chain |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for key in ("http-main", "http-frame", "secure-main", "secure-frame"):
        reference = json.loads((folder / ("firefox-" + key + ".json")).read_text("utf-8"))
        current = json.loads((folder / ("ruyijs-" + key + ".json")).read_text("utf-8"))
        report[key] = compare(reference, current)
        counts = report[key]["counts"]
        lines.append(f"| {key} | {len(reference['globals']['properties'])} | "
            f"{len(current['globals']['properties'])} | {counts.get('missing_property', 0)} | "
            f"{counts.get('extra_property', 0)} | {counts.get('descriptor', 0)} | "
            f"{counts.get('property_order', 0)} | {counts.get('prototype_chain', 0)} |")
    lines.extend(["", "## Missing Window globals by context", ""])
    for key, data in report.items():
        missing = [row["path"].removeprefix("window.") for row in data["differences"]
                   if row["kind"] == "missing_property" and row["path"].startswith("window.")]
        lines.extend([f"### {key}", "", ", ".join(f"`{name}`" for name in missing) or "None", ""])
        errors = data["firefoxErrors"] + data["ruyijsErrors"]
        if errors:
            lines.extend([f"Capture errors: {len(errors)} (see differences.json).", ""])
    (folder / "differences.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (folder / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    return {key: data["counts"] for key, data in report.items()}
