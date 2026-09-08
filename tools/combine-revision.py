#!/usr/bin/env python3
"""Combine independent evaluations into one self-contained revision JSON."""
import json
from pathlib import Path
import sys

versions, outputs, rev, destination = sys.argv[1:]
attrs = {
    a: {"version": v, "systems": {}}
    for a, v in json.loads(Path(versions).read_text()).items()
}
systems = {}
for system, path in json.loads(outputs).items():
    data = json.loads((Path(path) / "outputs.json").read_text())
    assert data["rev"] == rev and data["system"] == system
    systems[system] = {k: data[k] for k in ("attrCount", "errorCount")}
    for attr, entry in data["attrs"].items():
        attrs.setdefault(attr, {"systems": {}})["systems"][system] = entry
    for attr, error in json.loads((Path(path) / "errors.json").read_text()).items():
        attrs.setdefault(attr, {"systems": {}})["systems"].setdefault(system, {})[
            "error"
        ] = error
for entry in attrs.values():
    names = {v["name"] for v in entry["systems"].values() if "name" in v}
    if len(names) == 1:
        entry["name"] = names.pop()
        for value in entry["systems"].values():
            value.pop("name", None)
Path(destination).write_text(
    json.dumps(
        {"schema": 1, "rev": rev, "systems": systems, "attrs": attrs},
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n"
)
