#!/usr/bin/env python3
"""Check lane partitioning against both supported derivation schemas."""
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location(
    "lanes", Path(sys.argv[1]) / "shard-build-lanes.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
deps = {
    p: {"env": {"name": name}}
    for p, name in {
        "/nix/store/h1": "outputs-one-linux",
        "/nix/store/h2": "outputs-two-linux",
        "/nix/store/l1": "versions-one-linux",
        "/nix/store/l2": "versions-two-linux",
        "/nix/store/tool": "python3",
    }.items()
}
recipes = {
    "one": {
        "inputDrvs": {
            p: ["out"] for p in ("/nix/store/h1", "/nix/store/l1", "/nix/store/tool")
        }
    },
    "two": {
        "inputs": {"drvs": {p: {"outputs": ["out"]} for p in ("h2", "l2", "tool")}}
    },
}
assert m.lanes(recipes, deps) == (
    {"/nix/store/h1", "/nix/store/h2"},
    {"/nix/store/l1", "/nix/store/l2"},
)
for paths in (
    ("/nix/store/tool",),
    ("/nix/store/h1",),
    ("/nix/store/h1", "/nix/store/l1", "/nix/store/l2"),
):
    try:
        m.lanes({"bad": {"inputDrvs": {p: ["out"] for p in paths}}}, deps)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid lane structure accepted")
print(
    "Heavy/light lanes: both schemas, exact coverage, tools excluded, invalid recipes rejected: OK"
)
