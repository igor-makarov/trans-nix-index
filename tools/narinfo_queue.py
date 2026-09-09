"""Async recursive queue and checkpoint loading."""

import json
from pathlib import Path


def NarinfoQueue(graph, threads=2048, get=None):
    from async_crawler import AsyncCrawler

    return AsyncCrawler(graph, threads, get)


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
