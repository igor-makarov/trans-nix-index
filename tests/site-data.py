#!/usr/bin/env python3
"""Bounded metadata generation preserves exact dependency counts and examples."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / "index").mkdir()
    data = root / "artifacts"
    data.mkdir()
    out = root / "site"
    target = "a" * 32
    names = {"hello": target, **{f"a{i:03}": f"{i:032x}" for i in range(301)}}

    def put(path, value):
        path.write_text(json.dumps(value))

    put(root / "revisions.json", [{"date": "2026-01-01", "rev": "a"}])
    put(
        root / "index/versions.json",
        {"revisionCount": 1, "attrs": {a: {"1": None} for a in names}},
    )
    put(
        root / "index/history.json",
        {"revisionCount": 1, "attrs": {a: {"1": [0, None]} for a in names}},
    )
    put(
        data / "outpaths-x86_64-linux.json",
        {
            "revisionCount": 1,
            "attrs": {a: {"1": [d, a + "-1"]} for a, d in names.items()},
        },
    )
    put(data / "tip-outpaths-x86_64-linux.json", {"revisionCount": 1, "attrs": {}})
    put(
        data / "info-indexed.json",
        {d: [1, 100, 50, a + "-1", ""] for a, d in names.items()},
    )
    put(
        data / "refs-indexed.json",
        {d: [target + "-hello-1"] * 2 for a, d in names.items() if a != "hello"},
    )
    put(data / "closures.json", {d: [100, 1, 0] for d in names.values()})
    put(data / "outs-indexed.json", {})
    subprocess.run(["python3", sys.argv[1], str(root), str(data), str(out)], check=True)
    dependencies = json.loads((out / "revdeps/he.json").read_text())["attrs"]["hello"][
        "1"
    ]
    assert dependencies["c"] == 301
    assert dependencies["l"] == [[f"a{i:03}", "1"] for i in range(200)]
    assert (
        json.loads((out / "meta/a0.json").read_text())["attrs"]["a000"]["1"]["ns"]
        == 100
    )
print(
    "site data: streamed shards, disk-backed references, deduplication, and exact capped counts: OK"
)
