#!/usr/bin/env python3
"""Read root tree IDs from shallow, treeless commit objects; never check out files."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def discover(revisions, repository, url="https://github.com/NixOS/nixpkgs.git"):
    commits = sorted(set(revisions))
    if not commits or any(not re.fullmatch(r"[0-9a-f]{40}", r) for r in commits):
        raise ValueError("expected full commit SHAs")
    repository.mkdir(parents=True, exist_ok=False)

    def git(*args, **kwargs):
        return subprocess.check_output(
            ["git", "--git-dir", str(repository), *args], text=True, **kwargs
        )

    git("init", "--bare", str(repository))
    git("remote", "add", "origin", url)
    git("config", "remote.origin.promisor", "true")
    git("config", "remote.origin.partialclonefilter", "tree:0")
    git(
        "-c",
        "protocol.version=2",
        "fetch",
        "--depth=1",
        "--filter=tree:0",
        "--no-tags",
        "--no-write-fetch-head",
        "--stdin",
        "origin",
        input="\n".join(commits) + "\n",
    )
    result = {}
    for rev in commits:
        header = git("cat-file", "commit", rev).splitlines()[0]
        if not re.fullmatch(r"tree [0-9a-f]{40}", header):
            raise ValueError(f"invalid commit header: {rev}")
        result[rev] = header[5:]
    if git("for-each-ref").strip():
        raise ValueError("unexpected refs in commit-only fetch")
    print(f"Read {len(result)} tree hashes from commit-only fetch", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", type=Path)
    ap.add_argument("repository", type=Path)
    args = ap.parse_args()
    manifest = json.loads((args.inputs / "manifest.json").read_text())
    matrix = json.loads((args.inputs / "matrix.json").read_text())
    trees = discover([r["rev"] for r in manifest["revisions"]], args.repository)
    for r in manifest["revisions"]:
        r["tree"] = trees[r["rev"]]
    for r in matrix["include"]:
        r["tree"] = trees[r["rev"]]
    for name, value in (("manifest", manifest), ("matrix", matrix)):
        (args.inputs / f"{name}.json").write_text(
            json.dumps(value, sort_keys=True, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
