#!/usr/bin/env python3
"""Partition package attributes; validate and merge observation artifacts, never Nix recipes."""
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import random

from narinfo_queue import load_records


def assignment(index, shard, count):
    if not 1 <= count <= 256 or not 0 <= shard < count:
        raise ValueError("invalid shard count or identity")
    attrs = sorted(index["attrs"])
    # Every runner derives the same shuffle from the immutable full input index.
    random.Random(identity(index)).shuffle(attrs)
    return attrs[shard::count]


def identity(index):
    return hashlib.sha256(json.dumps(index, sort_keys=True).encode()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def partition(index, shard, count, work):
    attrs = assignment(index, shard, count)
    put(
        work / "index/versions.json",
        {**index, "attrs": {a: index["attrs"][a] for a in attrs}},
    )
    put(
        work / "shard.json",
        {
            "schema": 1,
            "shard": shard,
            "count": count,
            "index": identity(index),
            "attrs": attrs,
        },
    )


def merge(index, count, inputs, output, systems):
    directories = [p.parent for p in inputs.rglob("shard.json")]
    shards = {}
    for directory in directories:
        receipt = json.loads((directory / "shard.json").read_text())
        shard = receipt["shard"]
        if (
            receipt.get("schema") != 1
            or receipt["count"] != count
            or receipt["index"] != identity(index)
            or shard in shards
            or receipt["attrs"] != assignment(index, shard, count)
        ):
            raise ValueError("invalid, duplicate or mismatched enrichment shard")
        shards[shard] = directory
    if set(shards) != set(range(count)):
        raise ValueError("missing enrichment shards")
    data = output / "data"
    data.mkdir(parents=True, exist_ok=True)
    owned = {shard: set(assignment(index, shard, count)) for shard in shards}
    totals = ("vouchedByListing", "vouchedByCacheProbe", "carriedFromPreviousCut")
    for system in systems:
        for prefix in ("outpaths", "tip-outpaths"):
            combined = {
                "revisionCount": index["revisionCount"],
                "system": system,
                "source": "eval",
                "attrs": {},
                **dict.fromkeys(totals, 0),
            }
            for shard, directory in sorted(shards.items()):
                doc = json.loads(
                    (directory / "data" / f"{prefix}-{system}.json").read_text()
                )
                if any(
                    doc[k] != combined[k] for k in ("revisionCount", "system", "source")
                ):
                    raise ValueError("incompatible enrichment headers")
                if not set(doc["attrs"]) <= owned[shard]:
                    raise ValueError("attribute outside shard")
                combined["attrs"].update(doc["attrs"])
                for key in totals:
                    combined[key] += doc[key]
            put(data / f"{prefix}-{system}.json", combined)
        outs, misses = {}, []
        for shard, directory in sorted(shards.items()):
            for digest, siblings in json.loads(
                (directory / "data" / f"outs-{system}.json").read_text()
            ).items():
                target = outs.setdefault(digest, {})
                for suffix, value in siblings.items():
                    if suffix in target and target[suffix] != value:
                        raise ValueError("conflicting output observations")
                    target[suffix] = value
            rows = json.loads(
                (directory / "data" / f"misses-{system}.json").read_text()
            )
            if any(row[0] not in owned[shard] for row in rows):
                raise ValueError("miss outside shard")
            misses.extend(rows)
        put(data / f"outs-{system}.json", outs)
        put(data / f"misses-{system}.json", sorted(misses))
    graph, meta = {}, {}
    for directory in shards.values():
        if not (directory / "graph.jsonl").is_file():
            raise ValueError("missing shard graph")
        for digest, record in load_records(directory / "graph.jsonl").items():
            if digest in graph and graph[digest] != record:
                raise ValueError(f"conflicting narinfo observations for {digest}")
            graph[digest] = record
        path = directory / "data/manifest-meta.pkl"
        if path.exists():
            with path.open("rb") as f:
                for digest, record in pickle.load(f).items():
                    if digest in meta and meta[digest] != record:
                        raise ValueError("conflicting manifest metadata")
                    meta[digest] = record
    with (output / "graph.jsonl").open("w") as f:
        for digest in sorted(graph):
            f.write(json.dumps(graph[digest], sort_keys=True) + "\n")
    if meta:
        with (data / "manifest-meta.pkl").open("wb") as f:
            pickle.dump(meta, f, protocol=4)
    print(f"merged {count} enrichment shards; {len(graph)} unique graph records")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["partition", "merge"])
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--shards", type=int, required=True)
    parser.add_argument("--shard", type=int)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--systems", default="x86_64-linux,aarch64-linux,aarch64-darwin"
    )
    args = parser.parse_args()
    index = json.loads(args.index.read_text())
    if args.command == "partition":
        partition(index, args.shard, args.shards, args.output)
    else:
        merge(index, args.shards, args.inputs, args.output, args.systems.split(","))


if __name__ == "__main__":
    main()
