#!/usr/bin/env python3
"""Dry-run parser and derivation-driven preflight checks, no network/builds."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prepare", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
drv = "/nix/store/" + "a" * 32 + "-merge.drv"
dep = "/nix/store/" + "b" * 32 + "-revision.drv"
out = "/nix/store/" + "c" * 32 + "-revision"
plan = f"this derivation will be built:\n  {drv}\nthis path will be fetched (1 MiB download, 2 MiB unpacked):\n  {out}\n"
assert m.parse_plan(plan) == ([drv], [out])
assert m.parse_plan("") == ([], [])
assert m.parse_plan(f"these 2 derivations will be built:\n  {drv}\n  {dep}\n") == (
    [drv, dep],
    [],
)
for bad in (
    "unexpected format",
    "these 2 derivations will be built:\n",
    f"this derivation will be built:\n  {out}\n",
):
    try:
        m.parse_plan(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown/truncated plan accepted")
recipe = {
    "env": {m.MARKER: "1"},
    "inputs": {
        "drvs": {dep.split("/")[-1]: {"outputs": ["out"], "dynamicOutputs": {}}}
    },
}
m.allowed([drv], {drv: recipe})
m.allowed([drv], {drv: {"structuredAttrs": {m.MARKER: "1"}}})
m.allowed([drv], {drv: {"env": {"__json": json.dumps({m.MARKER: "1"})}}})
try:
    m.allowed([dep], {dep: {"env": {"name": "revision-index"}}})
except ValueError:
    pass
else:
    raise AssertionError("name alone allowed an input build")
assert m.dependencies(recipe) == {dep: ["out"]}
assert m.dependencies({"inputDrvs": {dep: ["out"]}}) == {dep: ["out"]}
for dry_plan, recipes in ((plan, {drv: recipe}), ("", {drv: recipe})):
    with patch.object(
        m.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, "", dry_plan),
    ) as run, patch.object(m, "show", return_value=recipes):
        m.prepare(drv)
        assert run.call_count == 1
        assert run.call_args.args[0] == ["nix-store", "--realise", "--dry-run", drv]
print(
    "merge preflight: fail-closed parsing, recipe markers, dry-run only including cache hits: OK"
)
