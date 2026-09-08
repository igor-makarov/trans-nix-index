#!/usr/bin/env python3
"""Materialize the observation interface from combined revision artifacts."""
import json
from pathlib import Path
import sys

files = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
out.mkdir()
for rev, path in files.items():
    data = json.loads(Path(path).read_text())
    assert data["schema"] == 1 and data["rev"] == rev
    for system, counts in data["systems"].items():
        attrs = {}
        for attr, entry in data["attrs"].items():
            value = entry["systems"].get(system, {})
            if "outputs" in value:
                attrs[attr] = {
                    "name": value.get("name", entry.get("name")),
                    "outputs": value["outputs"],
                }
        (out / f"{rev}.{system}.pure.json").write_text(
            json.dumps(
                {"rev": rev, "system": system, **counts, "attrs": attrs}, sort_keys=True
            )
            + "\n"
        )
