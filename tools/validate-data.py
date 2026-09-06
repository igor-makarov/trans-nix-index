#!/usr/bin/env python3
"""Validate snapshot consistency before publishing or building a site."""
import json
from pathlib import Path
import sys
from snapshot import verify


def validate(root):
    root = Path(root)
    verify(root)
    read = lambda name: json.loads((root / f"{name}.json").read_text())
    revisions, versions, history, stats = map(
        read, ["revisions", "versions", "history", "stats"]
    )
    n = len(revisions)
    assert n > 0
    assert len({r["rev"] for r in revisions}) == n
    assert [r["date"] for r in revisions] == sorted(r["date"] for r in revisions)
    assert versions["revisionCount"] == history["revisionCount"] == n
    assert stats["totals"]["revisions"] == n
    assert versions["attrs"].keys() == history["attrs"].keys()
    for attr, values in history["attrs"].items():
        assert values.keys() == versions["attrs"][attr].keys(), attr
        for version, raw in values.items():
            runs = raw if isinstance(raw[0], list) else [raw]
            previous = -1
            for first, last in runs:
                last = n - 1 if last is None else last
                assert isinstance(first, int) and isinstance(last, int)
                assert previous < first <= last < n, (attr, version, runs)
                previous = last
            offset = versions["attrs"][attr][version]
            assert (n - 1 if offset is None else offset) == previous, (attr, version)
    assert all(isinstance(i, int) and 0 <= i < n for i in history["skipped"])
    assert isinstance(read("releases"), dict)
    artifacts = root / "artifacts"
    outpaths = list(artifacts.glob("outpaths-*.json"))
    assert outpaths, "missing per-system store paths"
    for path in outpaths:
        system = path.name.removeprefix("outpaths-").removesuffix(".json")
        assert isinstance(
            json.loads((artifacts / f"outs-{system}.json").read_text()), dict
        )
        for prefix in ("outpaths", "tip-outpaths"):
            data = json.loads((artifacts / f"{prefix}-{system}.json").read_text())
            assert 0 < data["revisionCount"] <= n, path
    for stem in ("info-indexed", "refs-indexed", "closures"):
        assert list(artifacts.glob(f"{stem}*.json")), stem
    print(f"Validated {n} revisions and {len(versions['attrs'])} attributes")


if __name__ == "__main__":
    validate(sys.argv[1])
