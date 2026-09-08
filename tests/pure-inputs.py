#!/usr/bin/env python3
"""Offline discovery bounds and full fold coverage."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(sys.argv[1]) / f"{name}.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fold = module("merge-revisions")
discovery = module("discover-pipeline")
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    revs = [
        {
            "rev": str(i) * 40,
            "date": f"2026-01-0{i}",
            "name": f"nixos-26.05pre{i}.{str(i) * 12}",
        }
        for i in range(1, 4)
    ]
    manifest = {
        "schema": 1,
        "revisions": revs,
        "releases": {},
    }
    files = {}
    for r, attrs in zip(revs, [{"a": "1", "b": "1"}, {"a": "2"}, {"a": "1", "b": "1"}]):
        file = root / r["rev"]
        file.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "rev": r["rev"],
                    "attrs": {a: {"version": v} for a, v in attrs.items()},
                }
            )
        )
        files[r["rev"]] = str(file)
    whole = fold.merge(manifest, files)
    assert whole == fold.merge(manifest, files)
    assert whole[1]["attrs"]["a"]["1"] == [[0, 0], [2, None]]
    assert whole[1]["attrs"]["b"]["1"] == [[0, 0], [2, None]]
    for bad_manifest, bad_files in [
        (manifest, {}),
        (manifest, {r["rev"]: files[r["rev"]] for r in revs[1:]}),
        (dict(manifest, revisions=revs[:1]), files),
        (dict(manifest, revisions=[revs[0], revs[0]]), files),
    ]:
        try:
            fold.merge(bad_manifest, bad_files)
        except ValueError:
            pass
        else:
            raise AssertionError("missing, extra, or duplicate inputs accepted")
    discovery.channels = lambda: [r["name"] for r in reversed(revs)]
    requests = []

    def get(url):
        requests.append(url)
        if url.endswith("/git-revision"):
            return next(r["rev"].encode() for r in revs if r["name"] in url)
        return json.dumps(
            {
                "commit": {
                    "committer": {
                        "date": next(r["date"] for r in revs if r["rev"] in url)
                    }
                }
            }
        ).encode()

    discovery.get = get
    discovery.discover(root / "fresh", 1)
    fresh = fold.read(root / "fresh/manifest.json")
    assert fresh["revisions"] == revs[-1:]
    assert len(requests) == 2
    discovery.discover(root / "larger", 3)
    assert fold.read(root / "larger/manifest.json")["revisions"] == revs
    assert fold.read(root / "larger/matrix.json") == {
        "include": [{"rev": r["rev"], "name": r["name"]} for r in revs]
    }
    for limit in (0, 9, 1000):
        try:
            discovery.discover(root / "bad", limit)
        except ValueError:
            pass
        else:
            raise AssertionError("unbounded discovery allowed")
print(
    "full fold, disappearance/reappearance, deterministic repeat, exact input coverage, bounded discovery: OK"
)
