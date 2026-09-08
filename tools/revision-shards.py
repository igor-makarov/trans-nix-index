#!/usr/bin/env python3
"""Bounded job matrix, unlimited revisions per shard; GitHub owns job queuing."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def rows_from(plan):
    rows = plan["include"]
    if not rows or len({r["rev"] for r in rows}) != len(rows):
        raise ValueError("empty or duplicate revision plan")
    for row in rows:
        if not re.fullmatch(r"[0-9a-f]{40}", row["rev"]) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+-]*", row["name"]
        ):
            raise ValueError("invalid revision identity")
    return rows


def matrix(rows):
    return {"include": [{"shard": i} for i in range(min(256, len(rows)))]}


def assigned(rows, shard):
    count = min(256, len(rows))
    if not 0 <= shard < count:
        raise ValueError("invalid shard")
    return rows[shard::count]


def fetch(url):
    response = subprocess.check_output(
        [
            "curl",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            "60",
            "--write-out",
            "\n%{http_code}",
            url,
        ]
    )
    body, status = response.rsplit(b"\n", 1)
    if status == b"404":
        return None
    if status != b"200":
        raise RuntimeError(f"cache probe HTTP {status.decode()}: {url}")
    return body.decode()


def cached(root, get=fetch):
    """Metadata-only availability hint; Nix verifies actual downloads at merge.

    Only 404 means missing. Network/auth/server errors fail the job instead of
    silently launching expensive builds. Never follow payload URLs.
    """
    pending = [root]
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        if not re.fullmatch(
            r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=-]+", path
        ):
            raise ValueError("invalid store path")
        seen.add(path)
        hash_part = path.split("/")[3][:32]
        for cache in ("https://trans-nix-index.cachix.org", "https://cache.nixos.org"):
            info = get(f"{cache}/{hash_part}.narinfo")
            if info is not None:
                fields = dict(
                    line.split(": ", 1) for line in info.splitlines() if ": " in line
                )
                if fields.get("StorePath") != path:
                    raise ValueError("cache metadata path mismatch")
                pending.extend(
                    "/nix/store/" + p for p in fields.get("References", "").split()
                )
                break
        else:
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "build"])
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    rows = rows_from(json.loads(args.plan.read_text()))
    if args.command == "plan":
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(
                "matrix=" + json.dumps(matrix(rows), separators=(",", ":")) + "\n"
            )
        return
    for row in assigned(rows, int(os.environ["PIPELINE_SHARD"])):
        path = subprocess.check_output(
            [
                "nix",
                "eval",
                "--raw",
                "--file",
                "nix/revision-build.nix",
                "--argstr",
                "name",
                row["name"],
                "--argstr",
                "rev",
                row["rev"],
                "all.outPath",
            ],
            text=True,
        ).strip()
        if cached(path):
            print(f"Cached; skipping {row['name']}: {path}", flush=True)
            continue
        print(f"Building {row['name']}", flush=True)
        env = dict(
            os.environ, PIPELINE_REVISION=row["rev"], PIPELINE_REVISION_NAME=row["name"]
        )
        subprocess.run(["bash", "scripts/ci/build-revision"], env=env, check=True)


if __name__ == "__main__":
    main()
