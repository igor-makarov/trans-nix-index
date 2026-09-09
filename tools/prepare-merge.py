#!/usr/bin/env python3
"""Preflight one exact merge .drv using Nix's dry-run build plan.

Only recipes explicitly marked as merge computations may build. No downloads
or builds are performed by this check.
"""
import argparse
import json
import os
import re
import subprocess
import sys

MARKER = "transNixIndexMerge"
PATH = r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[^\s/]+"


def parse_plan(text):
    builds, fetches = [], []
    section = None
    expected = 0
    for line in text.splitlines():
        if not line.strip() or line.startswith("warning:"):
            continue
        header = re.fullmatch(
            r"(?:this (derivation|path)|these (\d+) (derivations|paths)) will be (built|fetched)(?: \([^\n]*\))?:",
            line,
        )
        if header:
            if expected:
                raise ValueError("truncated dry-run plan")
            section = builds if header[4] == "built" else fetches
            expected = int(header[2]) if header[2] else 1
        elif section is not None and expected and re.fullmatch(r"  " + PATH, line):
            path = line.strip()
            if section is builds and not path.endswith(".drv"):
                raise ValueError("build plan contains a non-derivation")
            section.append(path)
            expected -= 1
        else:
            raise ValueError(f"unrecognized dry-run output: {line}")
    if expected:
        raise ValueError("truncated dry-run plan")
    return builds, fetches


def store_path(path):
    return path if path.startswith("/nix/store/") else "/nix/store/" + path


def show(paths):
    data = json.loads(
        subprocess.check_output(
            ["nix", "derivation", "show", *sorted(paths)], text=True
        )
    )
    # Current Nix wraps derivations and uses basename keys; older Nix does not.
    return {store_path(k): v for k, v in data.get("derivations", data).items()}


def allowed(builds, recipes):
    def marker(recipe):
        if "structuredAttrs" in recipe:
            return recipe["structuredAttrs"].get(MARKER)
        env = recipe.get("env", {})
        if "__json" in env:
            return json.loads(env["__json"]).get(MARKER)
        return env.get(MARKER)

    forbidden = [p for p in builds if marker(recipes[p]) != "1"]
    if forbidden:
        raise ValueError(
            "Merge requires prebuilt inputs; refusing to build:\n"
            + "\n".join(forbidden)
        )


def dependencies(recipe):
    if "inputs" in recipe:
        result = {}
        for path, selection in recipe["inputs"]["drvs"].items():
            if selection.get("dynamicOutputs"):
                raise ValueError("dynamic derivation inputs are not supported")
            result[store_path(path)] = selection["outputs"]
        return result
    return recipe["inputDrvs"]


def prepare(drv):
    if not re.fullmatch(PATH + r"\.drv", drv):
        raise ValueError("expected a merge derivation store path")
    plan = subprocess.run(
        ["nix-store", "--realise", "--dry-run", drv],
        text=True,
        capture_output=True,
        check=True,
        env=dict(os.environ, LC_ALL="C", NO_COLOR="1"),
    )
    print(plan.stderr, file=sys.stderr, end="")
    builds, fetches = parse_plan(plan.stderr)
    if plan.stdout.strip():
        raise ValueError("unexpected dry-run stdout")
    recipes = show(set(builds) | {drv})
    allowed([drv, *builds], recipes)
    print(
        f"Preflight passed: {len(builds)} merge builds; {len(fetches)} planned downloads",
        file=sys.stderr,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("derivation")
    args = parser.parse_args()
    prepare(args.derivation)
