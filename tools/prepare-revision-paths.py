#!/usr/bin/env python3
"""Validate shard receipts against the full manifest; fetch only cached JSONs."""
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
    args.roots.mkdir(parents=True, exist_ok=True)
    for rev, path in sorted(paths.items()):
        subprocess.run(
            [
                "nix-store",
                "--realise",
                path,
                "--max-jobs",
                "0",
                "--builders",
                "",
                "--add-root",
                str((args.roots / rev).absolute()),
                "--indirect",
            ],
            check=True,
        )
        data = json.loads(Path(path).read_text())
        if data.get("schema") != 1 or data.get("rev") != rev:
            raise ValueError("revision JSON identity mismatch")
    (args.inputs / "revision-files.json").write_text(
        json.dumps(paths, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
