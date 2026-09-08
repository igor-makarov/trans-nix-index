#!/usr/bin/env python3
"""Pure fold of explicit per-revision version files; never consult a cache."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def merge(manifest, files):
    revs = manifest["revisions"]
    if not revs or len({r["rev"] for r in revs}) != len(revs):
        raise ValueError("revisions must be nonempty and unique")
    versions, history = {}, {}
    expected = {r["rev"] for r in revs}
    if set(files) != expected:
        raise ValueError("extraction inputs do not exactly match manifest revisions")
    for off in range(len(revs)):
        data = read(files[revs[off]["rev"]])
        if data["schema"] != 1 or data["rev"] != revs[off]["rev"]:
            raise ValueError("revision artifact identity mismatch")
        attrs = {a: d["version"] for a, d in data["attrs"].items() if "version" in d}
        if not attrs or not all(isinstance(v, str) for v in attrs.values()):
            raise ValueError("empty or invalid revision extraction")
        for attr, version in attrs.items():
            versions.setdefault(attr, {})[version] = off
            runs = history.setdefault(attr, {}).setdefault(version, [])
            if runs and runs[-1][1] == off - 1:
                runs[-1][1] = off
            else:
                runs.append([off, off])
    tip = len(revs) - 1
    for vs in versions.values():
        for version, off in vs.items():
            vs[version] = None if off == tip else off
    for vs in history.values():
        for version, runs in vs.items():
            packed = [[start, None if end == tip else end] for start, end in runs]
            vs[version] = packed[0] if len(packed) == 1 else packed
    return (
        {"revisionCount": len(revs), "attrs": versions},
        {"revisionCount": len(revs), "skipped": [], "attrs": history},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("files", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    manifest = read(args.manifest)
    versions, history = merge(manifest, read(args.files))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in {
        "revisions": manifest["revisions"],
        "releases": manifest["releases"],
        "versions": versions,
        "history": history,
    }.items():
        (args.out / f"{name}.json").write_text(json.dumps(data, sort_keys=True) + "\n")
