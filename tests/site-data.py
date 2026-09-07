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
    names = {
        "foo.bar.hello": target,
        "jetbrains.idea": "b" * 32,
        **{f"a{i:03}": f"{i:032x}" for i in range(301)},
    }

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
        {
            d: [target + "-foo.bar.hello-1"] * 2
            for a, d in names.items()
            if a != "foo.bar.hello"
        },
    )
    put(data / "closures.json", {d: [100, 1, 0] for d in names.values()})
    put(data / "outs-indexed.json", {})
    for stem in ["outpaths", "tip-outpaths"]:
        (data / f"{stem}-aarch64-linux.json").write_bytes(
            (data / f"{stem}-x86_64-linux.json").read_bytes()
        )
    subprocess.run(["python3", sys.argv[1], str(root), str(data), str(out)], check=True)
    for directory in ["meta", "meta-aarch64-linux"]:
        assert (
            "jetbrains.idea"
            in json.loads((out / directory / "pkgs/jetbrains/id.json").read_text())[
                "attrs"
            ]
        )
    assert (
        "foo.bar.hello"
        in json.loads((out / "revdeps-aarch64-linux/pkgs/foo/bar/he.json").read_text())[
            "attrs"
        ]
    )
    dependencies = json.loads((out / "revdeps/pkgs/foo/bar/he.json").read_text())[
        "attrs"
    ]["foo.bar.hello"]["1"]
    assert dependencies["c"] == 302
    assert dependencies["l"] == [[f"a{i:03}", "1"] for i in range(200)]
    assert (
        json.loads((out / "meta/pkgs/a0.json").read_text())["attrs"]["a000"]["1"]["ns"]
        == 100
    )
print(
    "site data: streamed shards, disk-backed references, deduplication, and exact capped counts: OK"
)
