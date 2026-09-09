#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "shards", Path(sys.argv[1]) / "enrichment-shards.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
index = {"revisionCount": 8, "attrs": {f"pkg{i}": {"1": None} for i in range(100)}}
parts = [m.assignment(index, s, 4) for s in range(4)]
assert sorted(sum(parts, [])) == sorted(index["attrs"])
assert all(len(p) == 25 for p in parts)
assert parts[0] != sorted(index["attrs"])[::4]
assert parts == [m.assignment(index, s, 4) for s in range(4)]
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    for s in range(4):
        p = root / "inputs" / str(s)
        m.partition(index, s, 4, p)
        for prefix in ["outpaths", "tip-outpaths"]:
            m.put(
                p / "data" / f"{prefix}-system.json",
                dict(
                    revisionCount=8,
                    system="system",
                    source="eval",
                    vouchedByListing=25,
                    vouchedByCacheProbe=0,
                    carriedFromPreviousCut=0,
                    attrs={a: {"1": ["digest"]} for a in parts[s]},
                ),
            )
        m.put(p / "data/outs-system.json", {"digest": {"doc": "child"}})
        m.put(p / "data/misses-system.json", [])
        m.put(p / "graph.jsonl", {"d": "digest", "ok": True, "refs": []})
    m.merge(index, 4, root / "inputs", root / "result", ["system"])
    doc = json.loads((root / "result/data/outpaths-system.json").read_text())
    assert set(doc["attrs"]) == set(index["attrs"]) and doc["vouchedByListing"] == 100
    assert len((root / "result/graph.jsonl").read_text().splitlines()) == 1
    m.put(root / "inputs/0/graph.jsonl", {"d": "digest", "ok": False})
    try:
        m.merge(index, 4, root / "inputs", root / "result", ["system"])
    except ValueError:
        pass
    else:
        raise AssertionError("conflicting graph accepted")
    (root / "inputs/0/shard.json").unlink()
    try:
        m.merge(index, 4, root / "inputs", root / "result", ["system"])
    except ValueError:
        pass
    else:
        raise AssertionError("missing shard accepted")
print(
    "Enrichment shards: deterministic shuffle, exact coverage, merged counters, graph deduplication, conflicts/missing shards rejected: OK"
)
