#!/usr/bin/env python3
"""Dry-run parser and derivation-driven preflight checks, no network/builds."""
import importlib.util
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
try:
    m.allowed([dep], {dep: {"env": {"name": "revision-index"}}})
except ValueError:
    pass
else:
    raise AssertionError("name alone allowed an input build")
assert m.dependencies(recipe) == {dep: ["out"]}
assert m.dependencies({"inputDrvs": {dep: ["out"]}}) == {dep: ["out"]}
with tempfile.TemporaryDirectory() as tmp:
    for fetch_fails in (False, True):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if "--dry-run" in command:
                assert command[-1] == drv
                return subprocess.CompletedProcess(command, 0, "", plan)
            assert command[:3] == ["nix-store", "--realise", out]
            assert command[command.index("--max-jobs") + 1] == "0"
            assert command[command.index("--builders") + 1] == ""
            assert "--add-root" in command
            if fetch_fails:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(m.subprocess, "run", side_effect=run), patch.object(
            m,
            "show",
            side_effect=[
                {drv: recipe},
                {dep: {"outputs": {"out": {"path": out.split("/")[-1]}}}},
            ],
        ):
            try:
                m.prepare(drv, Path(tmp))
            except subprocess.CalledProcessError:
                assert fetch_fails
            else:
                assert not fetch_fails
            assert len(calls) == 2
print(
    "merge preflight: exact drv plan, fail-closed parsing, recipe markers, fetch-only rooted inputs and fetch failure: OK"
)
