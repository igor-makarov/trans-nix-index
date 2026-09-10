#!/usr/bin/env python3
"""Bounded job matrix, unlimited revisions per shard; GitHub owns job queuing."""
import argparse
import json
import os
from pathlib import Path
import re
import random
import subprocess
import tempfile


def rows_from(plan):
    rows = plan["include"]
    if not rows or len({r["rev"] for r in rows}) != len(rows):
        raise ValueError("empty or duplicate revision plan")
    for row in rows:
        if "tree" in row and not re.fullmatch(r"[0-9a-f]{40}", row["tree"]):
            raise ValueError("invalid Git tree identity")
        if not re.fullmatch(r"[0-9a-f]{40}", row["rev"]) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+-]*", row["name"]
        ):
            raise ValueError("invalid revision identity")
    return rows


def matrix(rows, shards=256):
    if not 1 <= shards <= 256:
        raise ValueError("shard count must be between 1 and 256")
    return {"include": [{"shard": i} for i in range(min(shards, len(rows)))]}


def assigned(rows, shard, shards=256):
    count = len(matrix(rows, shards)["include"])
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
    parser.add_argument("--shards", type=int, default=256)
    args = parser.parse_args()
    rows = rows_from(json.loads(args.plan.read_text()))
    if args.command == "plan":
        # Persist once: every runner must partition the same shuffled sequence.
        random.SystemRandom().shuffle(rows)
        args.plan.write_text(json.dumps({"include": rows}, indent=2) + "\n")
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(
                "matrix="
                + json.dumps(matrix(rows, args.shards), separators=(",", ":"))
                + "\n"
            )
        return
    missing = []
    outputs = {}
    queue = assigned(rows, int(os.environ["PIPELINE_SHARD"]), args.shards)
    random.SystemRandom().shuffle(queue)
    roots = Path(
        tempfile.mkdtemp(prefix="revision-roots.", dir=args.plan.parent)
    ).resolve()
    for row in queue:
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
                *(["--argstr", "tree", row["tree"]] if "tree" in row else []),
                "all.outPath",
            ],
            text=True,
        ).strip()
        outputs[row["rev"]] = path
        if cached(path):
            print(f"Cached; skipping {row['name']}: {path}", flush=True)
            continue
        print(f"Queued for build: {row['name']}", flush=True)
        drv = subprocess.check_output(
            [
                "nix-instantiate",
                "nix/revision-build.nix",
                "--argstr",
                "name",
                row["name"],
                "--argstr",
                "rev",
                row["rev"],
                *(["--argstr", "tree", row["tree"]] if "tree" in row else []),
                "-A",
                "all",
                "--add-root",
                str(roots / row["rev"]),
                "--indirect",
            ],
            text=True,
        ).strip()
        missing.append(os.path.realpath(drv))
    if missing:
        subprocess.run(["bash", "scripts/ci/build-shard", *missing], check=True)
    destination = args.plan.parent / "revision-paths"
    destination.mkdir(exist_ok=True)
    (destination / (os.environ["PIPELINE_SHARD"] + ".json")).write_text(
        json.dumps(outputs, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
