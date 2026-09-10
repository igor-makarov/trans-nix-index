#!/usr/bin/env python3
"""A partial rerun reuses completed shards, never ambiguous/expired receipts."""
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location(
    "receipts", Path(sys.argv[1]) / "pipeline-receipts.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
artifacts = [
    {"id": 1, "name": "observations-0-1"},
    {"id": 2, "name": "observations-1-1"},
    {"id": 3, "name": "observations-1-2"},
    {"id": 4, "name": "unrelated"},
]
assert m.select(artifacts, "observations", 2) == "1,3"
for bad in [
    artifacts[:1],
    artifacts + [artifacts[2]],
    artifacts + [{"id": 5, "name": "observations-2-1"}],
    artifacts + [{"id": 6, "name": "observations-1-3", "expired": True}],
]:
    try:
        m.select(bad, "observations", 2)
        raise AssertionError("bad receipt coverage accepted")
    except ValueError:
        pass
print(
    "Partial reruns: latest receipt per shard, exact coverage, duplicates and expiry rejected: OK"
)
