#!/usr/bin/env python3
"""Offline coverage of continuous crawling, resume, and probe metadata reuse."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(sys.argv[1]) / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crawler = load("crawl-narinfos")
join = load("join-eval-listing")
with tempfile.TemporaryDirectory() as tmp:
    graph = Path(tmp) / "graph.jsonl"
    child_started = threading.Event()
    calls = []

    def get(d):
        calls.append(d)
        if d == "slow":
            assert child_started.wait(5), "wave barrier prevented child scheduling"
        if d == "child":
            child_started.set()
        return {"d": d, "ok": True, "refs": ["child"] if d == "fast" else []}

    crawler.crawl({"fast", "slow"}, graph, threads=2, get=get)
    assert sorted(calls) == ["child", "fast", "slow"]
    calls.clear()
    crawler.crawl({"fast", "slow"}, graph, threads=2, get=get)
    assert not calls

    graph.write_text(
        json.dumps({"d": "parent", "ok": True, "refs": ["child"]}) + "\n{broken"
    )
    crawler.crawl({"parent"}, graph, max_fetch=0, get=get)
    assert not calls
    crawler.crawl({"parent"}, graph, max_fetch=1, get=get)
    assert calls == ["child"]
    assert "child" in crawler.load_records(graph)

    graph.write_text("")
    crawler.crawl({"retry"}, graph, get=lambda d: {"d": d, "ok": False, "err": True})
    assert not crawler.load_records(graph)
    crawler.crawl({"retry"}, graph, get=lambda d: {"d": d, "ok": False})
    assert crawler.load_records(graph)["retry"]["ok"] is False
    crawler.crawl({"retry"}, graph, recheck_dead=True, get=get)
    assert crawler.load_records(graph)["retry"]["ok"] is True

    graph.write_text("")
    join._probe_graph = str(graph)
    with patch.object(
        join,
        "fetch_narinfo",
        return_value={"d": "parent", "ok": True, "refs": ["child"]},
    ):
        assert join.in_cache("parent")
    calls.clear()
    crawler.crawl({"parent"}, graph, get=get)
    assert calls == ["child"], "successful probe fetched twice"
    with patch.object(
        join, "fetch_narinfo", return_value={"d": "bad", "ok": False, "err": True}
    ):
        try:
            join.in_cache("bad")
        except RuntimeError:
            pass
        else:
            raise AssertionError("transport failure treated as absence")
    assert "bad" not in crawler.load_records(graph)
# A platform cannot block another's primary checks; duplicates across phases
# and platforms are fetched once under one global worker limit.
calls = []
active = peak = 0
lock = threading.Lock()
both = threading.Barrier(2)


def probe(d):
    global active, peak
    with lock:
        calls.append(d)
        active += 1
        peak = max(peak, active)
    if d in {"linux", "mac"}:
        both.wait(timeout=5)
    with lock:
        active -= 1
    return d != "missing"


def platform(primary):
    verdicts = yield {primary, "shared"}
    assert verdicts[primary] and verdicts["shared"]
    verdicts = yield {"shared", "sibling", "missing"}
    assert verdicts["sibling"] and not verdicts["missing"]


join.run_joins([platform("linux"), platform("mac")], 2, probe)
assert sorted(calls) == ["linux", "mac", "missing", "shared", "sibling"]
assert peak == 2
print(
    "Enrichment: continuous queue, deduplication, budgets, resume, retries, probe reuse: OK"
)

from narinfo_queue import NarinfoQueue

with tempfile.TemporaryDirectory() as tmp:
    graph = Path(tmp) / "unified.jsonl"
    calls = []
    child_started = threading.Event()

    def unified_get(d):
        calls.append(d)
        if d == "slow":
            assert child_started.wait(5), "crawl blocked behind probe barrier"
        if d == "child":
            child_started.set()
        return {"d": d, "ok": d != "missing", "refs": ["child"] if d == "fast" else []}

    queue = NarinfoQueue(graph, 2, get=unified_get)
    fast = queue.request("fast")
    slow = queue.request("slow")
    assert queue.request("fast") is fast
    assert slow.result(timeout=10)["ok"]
    assert queue.request("child").result()["ok"]
    missing = queue.request("missing")
    assert not missing.result()["ok"]
    assert queue.request("missing") is missing
    queue.close()
    assert sorted(calls) == ["child", "fast", "missing", "slow"]
    calls.clear()
    queue = NarinfoQueue(graph, 2, get=unified_get)
    queue.seed({"fast", "slow"})
    assert queue.request("fast").result()["ok"]  # Fresh root probe on a new run.
    queue.close()
    assert calls == ["fast"]
print(
    "Unified queue: live dependency expansion, single-flight, cached 404s, resume: OK"
)

# Equal-size multi-output candidates must be independent of arrival order.
import subprocess

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    seeds = root / "seeds.json"
    seeds.write_text(json.dumps({"attrs": {"pkg": {"1": ["root"]}}}))
    rows = [dict(d=d, ok=True, name="pkg-1-doc", ns=10, refs=[]) for d in ["a", "b"]]
    outputs = []
    for index, records in enumerate([rows, rows[::-1]]):
        graph = root / f"graph-{index}"
        graph.write_text("".join(json.dumps(r) + "\n" for r in records))
        out = root / f"out-{index}"
        subprocess.run(
            [
                sys.executable,
                str(Path(sys.argv[1]) / "extract-outputs.py"),
                "--seeds",
                str(seeds),
                "--graph",
                str(graph),
                "--out",
                str(out),
            ],
            check=True,
        )
        outputs.append(json.loads(out.read_text()))
    assert outputs[0] == outputs[1]
print("Output representative is independent of request completion order: OK")
