#!/usr/bin/env python3
"""Continuously crawl narinfo references, checkpointing completed requests.

The append-only graph contains only observed 200/404 responses. Transient
failures remain retryable on the next run. Resumption includes unfinished
references from saved records, not just newly added seeds.
"""
import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
from pathlib import Path
import time

from narinfo import fetch


def load_seeds(files):
    return {
        entry[0]
        for file in files
        for versions in json.loads(Path(file).read_text())["attrs"].values()
        for entry in versions.values()
    }


def load_records(path):
    records = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            try:
                rec = json.loads(line)
                if not rec.get("err"):
                    records[rec["d"]] = rec
            except (ValueError, KeyError):
                continue
    return records


def crawl(seeds, graph, threads=64, max_fetch=3_000_000, recheck_dead=False, get=fetch):
    if threads < 1 or max_fetch < 0:
        raise ValueError("invalid crawl limits")
    records = load_records(graph)
    references = {d for rec in records.values() for d in rec.get("refs", [])}
    frontier = (seeds | references) - records.keys()
    if recheck_dead:
        frontier |= {d for d in seeds if d in records and not records[d]["ok"]}
    queue = deque(sorted(frontier))
    seen = set(records) | frontier
    fetched = errors = 0
    start = time.monotonic()
    with ThreadPoolExecutor(threads) as pool, open(graph, "a") as out:
        # Repair an interrupted final line before appending another record.
        out.write("\n")
        pending = {}
        while queue or pending:
            while (
                queue and len(pending) < threads and fetched + len(pending) < max_fetch
            ):
                digest = queue.popleft()
                pending[pool.submit(get, digest)] = digest
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                del pending[future]
                rec = future.result()
                fetched += 1
                if rec.get("err"):
                    errors += 1
                    continue
                out.write(json.dumps(rec, separators=(",", ":")) + "\n")
                for digest in rec.get("refs", []):
                    if digest not in seen:
                        seen.add(digest)
                        queue.append(digest)
            out.flush()
            if fetched and fetched % 10000 == 0:
                print(
                    f"{fetched} crawled ({fetched / (time.monotonic() - start):.0f}/s)",
                    flush=True,
                )
    result = dict(
        fetched=fetched,
        errors=errors,
        frontier=len(queue),
        elapsedSeconds=round(time.monotonic() - start, 3),
        threads=threads,
    )
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--threads", type=int, default=64)
    parser.add_argument("--max-fetch", type=int, default=3_000_000)
    parser.add_argument("--recheck-dead", action="store_true")
    args = parser.parse_args()
    crawl(
        load_seeds(args.seeds),
        args.graph,
        args.threads,
        args.max_fetch,
        args.recheck_dead,
    )


if __name__ == "__main__":
    main()
