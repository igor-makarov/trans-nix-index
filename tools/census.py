#!/usr/bin/env python3
"""The weekly census: is every indexed store path still downloadable?

For every digest named by the seed files, GET the narinfo and then HEAD the
NAR payload it points at. The narinfo says the cache remembers the path; the
HEAD says the bytes are actually there. Both checks matter — the prototype
found narinfos whose NAR had been garbage-collected exactly never, but that
is a claim to keep re-earning, not to assume.

Outputs:
  census-results.json   {at, total, narinfoOk, narOk, missingNarinfo: [...],
                         missingNar: [...]} — the snapshot the rolling
                         release publishes.
  --graph (optional)    liveness changes are appended to the crawl graph as
                         {"d": ..., "ok": bool} records, so the next
                         consolidation sees them without a re-crawl. Both
                         directions: consolidation carries a verdict forward
                         until a fetch contradicts it, and this is the sweep
                         that fetches.
"""
import argparse
import asyncio
import httpx
import json
import sys
import time

CACHE_HOST = "cache.nixos.org"
USER_AGENT = "nixpkgs-multiverse-census"
RETRIES = 3
# Between attempts, multiplied by the attempt number.
RETRY_BACKOFF_SECONDS = 0.5
TIMEOUT_SECONDS = 30


def dead_digests(graph):
    """Digests the crawl graph currently records as gone.

    Only these can be resurrected, which is the whole reason to read a 500 MB
    file here: appending an alive record for each of the 600k paths that
    answered would say nothing the graph does not already hold."""
    dead = set()
    with open(graph, "rt") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("ok"):
                dead.discard(rec["d"])
            else:
                dead.add(rec["d"])
    return dead


def load_seeds(seed_files):
    seed = set()
    for f in seed_files:
        data = json.load(open(f))
        for vers in data["attrs"].values():
            for entry in vers.values():
                seed.add(entry[0])
    return seed


class Census:
    def __init__(self, client):
        self.client = client
        self.retries = {}

    async def request(self, method, path):
        for attempt in range(RETRIES):
            try:
                response = await self.client.request(method, path)
                if response.status_code in (200, 404):
                    return response.status_code, response.content
                reason = f"HTTP {response.status_code}"
            except httpx.TransportError as error:
                reason = type(error).__name__
            if attempt + 1 < RETRIES:
                self.retries[reason] = self.retries.get(reason, 0) + 1
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        return None, b""

    async def check(self, digest):
        status, body = await self.request("GET", f"/{digest}.narinfo")
        if status != 200:
            return {"d": digest, "narinfo": False, "nar": False, "err": status is None}
        try:
            fields = dict(
                line.split(": ", 1)
                for line in body.decode().splitlines()
                if ": " in line
            )
            nar_url = fields["URL"]
            # Never let cache metadata redirect probes to another host.
            if not nar_url.startswith("nar/") or ".." in nar_url.split("/"):
                raise ValueError("invalid payload URL")
        except (UnicodeError, KeyError, ValueError):
            return {"d": digest, "narinfo": True, "nar": False, "err": True}
        status, _ = await self.request("HEAD", f"/{nar_url}")
        return {
            "d": digest,
            "narinfo": True,
            "nar": status == 200,
            "err": status is None,
        }


async def scan(digests):
    started = time.monotonic()
    results = []
    async with httpx.AsyncClient(
        http2=True,
        base_url=f"https://{CACHE_HOST}",
        timeout=httpx.Timeout(TIMEOUT_SECONDS, pool=None),
        headers={"User-Agent": USER_AGENT},
    ) as client:
        census = Census(client)
        # No semaphore/task cap: HTTPX defaults and server stream limits govern transport.
        tasks = [asyncio.create_task(census.check(d)) for d in digests]
        try:
            for task in asyncio.as_completed(tasks):
                results.append(await task)
                if len(results) % 10000 == 0:
                    print(
                        f"  {len(results)} checked ({len(results)/(time.monotonic()-started):.0f}/s)",
                        flush=True,
                    )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    return results, {"retries": census.retries, "t0": started}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", nargs="+", required=True, help="outpaths json files")
    ap.add_argument("--out", required=True, help="census-results.json")
    ap.add_argument(
        "--graph", help="crawl graph to append liveness changes to (optional)"
    )
    ap.add_argument("--date", required=True, help="the snapshot's date, YYYY-MM-DD")
    args = ap.parse_args()

    digests = sorted(load_seeds(args.seeds))
    print(f"{len(digests)} digests to check", flush=True)

    results, stats = asyncio.run(scan(digests))

    # A digest that timed out through every retry is unknown, not dead; it is
    # excluded from the missing lists so a flaky hour cannot declare a
    # massacre, and the count is reported so a flaky hour is still visible.
    elapsed = time.monotonic() - stats["t0"]
    print(
        f"checked {len(results)} in {elapsed / 60:.1f} min "
        f"({len(results) / elapsed:.0f}/s)",
        flush=True,
    )
    if stats["retries"]:
        total = sum(stats["retries"].values())
        detail = ", ".join(f"{n}x {why}" for why, n in sorted(stats["retries"].items()))
        print(f"retried {total} requests: {detail}", flush=True)

    errors = [r for r in results if r.get("err")]
    checked = [r for r in results if not r.get("err")]
    missing_narinfo = sorted(r["d"] for r in checked if not r["narinfo"])
    missing_nar = sorted(r["d"] for r in checked if r["narinfo"] and not r["nar"])

    summary = {
        "at": args.date,
        "total": len(digests),
        "checked": len(checked),
        "unreachable": len(errors),
        "narinfoOk": sum(1 for r in checked if r["narinfo"]),
        "narOk": sum(1 for r in checked if r["nar"]),
        "missingNarinfo": missing_narinfo,
        "missingNar": missing_nar,
    }
    json.dump(summary, open(args.out, "w"), indent=1, sort_keys=True)
    print(
        f"census: {summary['narOk']}/{summary['checked']} fully alive, "
        f"{len(missing_narinfo)} narinfos missing, {len(missing_nar)} NARs "
        f"missing, {len(errors)} unreachable",
        flush=True,
    )

    # Feed the changes back into the graph so consolidation sees them. Deaths,
    # because a missing NAR is a dead path even though its narinfo lingers —
    # and resurrections, because consolidation carries a verdict forward
    # until a fetch contradicts it, and this is the sweep that fetches.
    #
    # The records carry liveness alone. Sizes, name and references stay
    # whatever the crawl recorded: this is a liveness sweep, and it read the
    # narinfo of a path it already knows.
    if args.graph:
        was_dead = dead_digests(args.graph)
        newly_dead = sorted(set(missing_narinfo + missing_nar) - was_dead)
        alive_again = sorted(
            {r["d"] for r in checked if r["narinfo"] and r["nar"]} & was_dead
        )
        changed = [{"d": d, "ok": False} for d in newly_dead]
        changed += [{"d": d, "ok": True} for d in alive_again]
        if changed:
            with open(args.graph, "at") as f:
                for rec in changed:
                    f.write(json.dumps(rec) + "\n")
        print(
            f"{len(newly_dead)} newly dead and {len(alive_again)} resurrected "
            f"digests appended to {args.graph}",
            flush=True,
        )


if __name__ == "__main__":
    sys.exit(main())
