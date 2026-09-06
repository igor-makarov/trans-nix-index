#!/usr/bin/env python3
import json
from pathlib import Path
import runpy
import sys
import tempfile

module = runpy.run_path(sys.argv[1])
plan = module["plan"]
with tempfile.TemporaryDirectory() as temporary:
    previous, work = Path(temporary) / "previous", Path(temporary) / "work"
    (previous / "artifacts").mkdir(parents=True)
    (previous / "state").mkdir()
    work.mkdir()

    def put(path, value):
        path.write_text(json.dumps(value))

    revisions = [{"rev": "a"}]
    for root in (previous, work):
        put(root / "revisions.json", revisions)
        put(root / "releases.json", {"stable": "a"})
    for prefix in ("outpaths", "tip-outpaths"):
        put(previous / f"artifacts/{prefix}-x86_64-linux.json", {"revisionCount": 1})
    assert plan(previous, work) == "none"
    put(work / "releases.json", {"stable": "b"})
    assert plan(previous, work) == "metadata"
    put(work / "revisions.json", revisions + [{"rev": "b"}])
    assert plan(previous, work) == "update"
    put(work / "revisions.json", revisions)
    put(previous / "artifacts/outpaths-x86_64-linux.json", {"revisionCount": 0})
    assert plan(previous, work) == "update"
    put(previous / "artifacts/outpaths-x86_64-linux.json", {"revisionCount": 1})
    put(previous / "state/store-generator.json", {"version": 0})
    assert plan(previous, work) == "update"
    put(previous / "state/store-generator.json", {"version": module["STORE_GENERATOR"]})
    assert plan(previous, work) == "metadata"
    put(work / "revisions.json", [{"rev": "b"}])
    try:
        plan(previous, work)
    except ValueError:
        pass
    else:
        raise AssertionError("renumbered revisions accepted")
print(
    "update gate: no-op, metadata-only, new revisions, stale data, generator invalidation, offset protection: OK"
)
