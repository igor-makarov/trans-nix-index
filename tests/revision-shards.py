#!/usr/bin/env python3
"""Offline partition and metadata-only cache tests."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("shards", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
for n in (1, 3, 256, 257, 10000):
    rows = [{"name": f"revision-{i}", "rev": f"{i:040x}"} for i in range(n)]
    assert m.rows_from({"include": rows}) == rows
    jobs = m.matrix(rows)["include"]
    assert len(jobs) == min(n, 256)
    partitions = [m.assigned(rows, j["shard"]) for j in jobs]
    assert sorted(r["rev"] for p in partitions for r in p) == sorted(
        r["rev"] for r in rows
    )
    assert max(map(len, partitions)) - min(map(len, partitions)) <= 1
for bad in ([], [{"name": "x", "rev": "invalid"}], [{"name": "../x", "rev": "a" * 40}]):
    try:
        m.rows_from({"include": bad})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid plan accepted")
root = "/nix/store/" + "a" * 32 + "-root"
child = "/nix/store/" + "b" * 32 + "-child"
urls = []


def get(url):
    urls.append(url)
    assert url.endswith(".narinfo")
    if "a" * 32 in url:
        return f"StorePath: {root}\nReferences: {child.split('/')[-1]}\nURL: nar/never-download-this\n"
    if "cache.nixos.org" in url:
        return f"StorePath: {child}\nReferences: {child.split('/')[-1]}\n"
    return None


assert m.cached(root, get)
assert len(urls) == 3
assert not m.cached(root, lambda url: None)
assert not m.cached(root, lambda url: get(url) if "a" * 32 in url else None)
try:
    m.cached(root, lambda url: "StorePath: /nix/store/wrong\n")
except ValueError:
    pass
else:
    raise AssertionError("invalid metadata accepted")


def unavailable(url):
    raise RuntimeError("HTTP 503")


try:
    m.cached(root, unavailable)
except RuntimeError:
    pass
else:
    raise AssertionError("server error treated as cache miss")
with tempfile.TemporaryDirectory() as tmp:
    plan = Path(tmp) / "matrix.json"
    plan.write_text(json.dumps({"include": [{"name": "revision-1", "rev": "a" * 40}]}))
    for hit in (True, False):
        with (
            patch.object(sys, "argv", ["revision-shards", "build", str(plan)]),
            patch.dict(os.environ, {"PIPELINE_SHARD": "0"}),
            patch.object(m.subprocess, "check_output", return_value=root) as evaluate,
            patch.object(m, "cached", return_value=hit) as probe,
            patch.object(m.subprocess, "run") as build,
        ):
            m.main()
            assert evaluate.call_count == (1 if hit else 2)
            probe.assert_called_once_with(root)
            assert evaluate.call_args_list[0].args[0][-1] == "all.outPath"
            if hit:
                build.assert_not_called()
            else:
                build.assert_called_once()
                instantiate = evaluate.call_args_list[1].args[0]
                assert "--add-root" in instantiate and "--indirect" in instantiate
                assert build.call_args.args[0] == [
                    "bash",
                    "scripts/ci/build-shard",
                    root,
                ]
    plan.write_text(
        json.dumps(
            {
                "include": [
                    {"name": f"revision-{i}", "rev": f"{i:040x}"} for i in range(8)
                ]
            }
        )
    )
    original = json.loads(plan.read_text())["include"]
    output = Path(tmp) / "github-output"
    with (
        patch.object(
            sys, "argv", ["revision-shards", "plan", str(plan), "--shards", "2"]
        ),
        patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}),
        patch.object(
            m.random.SystemRandom, "shuffle", side_effect=lambda rows: rows.reverse()
        ),
    ):
        m.main()
    shuffled = m.rows_from(json.loads(plan.read_text()))
    assert shuffled == list(reversed(original))
    assert json.loads(output.read_text().removeprefix("matrix=")) == m.matrix(
        shuffled, 2
    )
    assert m.assigned(shuffled, 0, 2) != m.assigned(original, 0, 2)
    assert sorted(
        r["rev"] for i in range(2) for r in m.assigned(shuffled, i, 2)
    ) == sorted(r["rev"] for r in original)
    with (
        patch.object(
            sys, "argv", ["revision-shards", "build", str(plan), "--shards", "2"]
        ),
        patch.dict(os.environ, {"PIPELINE_SHARD": "0"}),
        patch.object(m.subprocess, "check_output", return_value=root),
        patch.object(m, "cached", side_effect=[False, True, False, True]),
        patch.object(m.subprocess, "run") as build,
    ):
        m.main()
        build.assert_called_once_with(
            ["bash", "scripts/ci/build-shard", root, root], check=True
        )
print(
    "shards: 10,000 revisions, balanced exact coverage, metadata-only hits/misses/dependencies/errors, cache hits skip and misses build: OK"
)
