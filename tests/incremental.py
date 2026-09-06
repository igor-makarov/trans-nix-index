#!/usr/bin/env python3
"""Incremental merges need the latest snapshot, not old extraction caches."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve()
key = hashlib.sha256(
    b"".join(
        (source / "nix" / p).read_bytes()
        for p in ["extract-versions.nix", "nested-sets.nix"]
    )
).hexdigest()[:8]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    cache = root / "index/.per-rev"
    cache.mkdir(parents=True)
    env = {
        **os.environ,
        "MULTIVERSE_ROOT": str(root),
        "MULTIVERSE_NIX": str(source / "nix"),
    }

    def put(path, value):
        (root / path).write_text(json.dumps(value))

    def read(path):
        return json.loads((root / path).read_text())

    def merge():
        subprocess.run(
            [
                "bash",
                str(source / "tools/build-index.sh"),
                "--incremental",
                "--merge-only",
            ],
            env=env,
            check=True,
        )
        subprocess.run(
            ["bash", str(source / "tools/build-history.sh"), "--incremental"],
            env=env,
            check=True,
        )

    put(
        "revisions.json",
        [{"rev": c, "date": f"2026-01-0{i+1}"} for i, c in enumerate("abc")],
    )
    put(
        "index/versions.json",
        {
            "revisionCount": 2,
            "attrs": {"hello": {"1": 0, "2": None}, "stable": {"1": None}},
        },
    )
    put(
        "index/history.json",
        {
            "revisionCount": 2,
            "skipped": [],
            "attrs": {
                "hello": {"1": [0, 0], "2": [1, None]},
                "stable": {"1": [0, None]},
            },
        },
    )
    put(f"index/.per-rev/c.{key}.json", {"hello": "1", "stable": "1"})
    merge()
    assert read("index/versions.json") == {
        "revisionCount": 3,
        "attrs": {"hello": {"1": None, "2": 1}, "stable": {"1": None}},
    }
    assert read("index/history.json") == {
        "revisionCount": 3,
        "skipped": [],
        "attrs": {
            "hello": {"1": [[0, 0], [2, None]], "2": [1, 1]},
            "stable": {"1": [0, None]},
        },
    }
    # Next run starts from the NEW snapshot, with no old cached extractions.
    for p in cache.iterdir():
        p.unlink()
    revisions = read("revisions.json") + [{"rev": "d", "date": "2026-01-04"}]
    put("revisions.json", revisions)
    put(f"index/.per-rev/d.{key}.json", {"stable": "1"})
    merge()
    assert read("index/versions.json")["attrs"]["hello"] == {"1": 2, "2": 1}
    assert read("index/history.json")["attrs"]["hello"]["1"] == [[0, 0], [2, 2]]
    before = read("index/history.json")
    # Exercise the real parallel driver with zero new revisions, not merge-only.
    subprocess.run(
        ["bash", str(source / "tools/build-index.sh"), "--incremental", "-j", "2"],
        env=env,
        check=True,
    )
    merge()
    assert read("index/history.json") == before
print("incremental merge, disappearance, gaps, latest-state reuse, and no-op: OK")
