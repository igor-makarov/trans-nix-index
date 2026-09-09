#!/usr/bin/env python3
"""Validate manifest receipt coverage and batch-fetch JSONs; merge checks contents."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def collect(manifest, receipts):
    expected = {r["rev"]: r["name"] for r in manifest["revisions"]}
    if not expected or len(expected) != len(manifest["revisions"]):
        raise ValueError("empty or duplicate manifest revisions")
    paths = {}
    for receipt in receipts:
        for rev, path in receipt.items():
            if rev not in expected or rev in paths:
                raise ValueError("unknown or duplicate revision receipt")
            pattern = (
                r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-revision-"
                + re.escape(expected[rev])
                + r"\.json"
            )
            if not isinstance(path, str) or not re.fullmatch(pattern, path):
                raise ValueError("invalid revision output path")
            paths[rev] = path
    if paths.keys() != expected.keys():
        raise ValueError("missing revision receipts")
    return paths


def fetch(paths, roots):
    roots.mkdir(parents=True, exist_ok=True)
    # One invocation lets Nix schedule substitutions; no extraction may build.
    # Nix creates numbered roots when realising multiple paths.
    subprocess.run(
        [
            "nix-store",
            "--realise",
            *sorted(paths.values()),
            "--max-jobs",
            "0",
            "--builders",
            "",
            "--add-root",
            str((roots / "revision").resolve()),
            "--indirect",
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("roots", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.inputs / "manifest.json").read_text())
    paths = collect(
        manifest,
        [
            json.loads(p.read_text())
            for p in sorted((args.inputs / "revision-paths").glob("*.json"))
        ],
    )
    fetch(paths, args.roots)
    (args.inputs / "revision-files.json").write_text(
        json.dumps(paths, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
