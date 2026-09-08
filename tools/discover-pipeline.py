#!/usr/bin/env python3
"""External channel discovery. Emit a bounded, immutable input bundle for Nix."""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://nix-releases.s3.amazonaws.com/"


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "trans-nix-index"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def channels():
    marker = ""
    while True:
        query = urllib.parse.urlencode(
            {"prefix": "nixos/unstable/", "delimiter": "/", "marker": marker}
        )
        root = ET.fromstring(get(BASE + "?" + query))
        prefixes = [e.text for e in root.findall("{*}CommonPrefixes/{*}Prefix")]
        yield from (p.rstrip("/").split("/")[-1] for p in prefixes)
        if root.findtext("{*}IsTruncated") != "true":
            break
        if not prefixes:
            raise ValueError("truncated listing without pagination cursor")
        marker = prefixes[-1]


def channel_key(name):
    match = re.fullmatch(r"nixos-(\d+)\.(\d+)pre(\d+)\.([0-9a-f]{7,12})", name)
    return tuple(map(int, match.groups()[:3])) if match else None


def discover(destination, limit):
    if not 1 <= limit <= 100:
        raise ValueError("trial limit must be between 1 and 100 new revisions")
    releases = {}
    candidates = sorted((n for n in channels() if channel_key(n)), key=channel_key)
    # Manual rollout selects a small complete dataset, not an incremental tail.
    candidates = candidates[-limit:]
    added = []
    for name in candidates:
        if len(added) >= limit:
            break
        sha = get(BASE + f"nixos/unstable/{name}/git-revision").decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("invalid git-revision")
        if any(r["rev"] == sha for r in added):
            continue
        commit = json.loads(
            get("https://api.github.com/repos/NixOS/nixpkgs/commits/" + sha)
        )
        added.append(
            {
                "rev": sha,
                "date": commit["commit"]["committer"]["date"][:10],
                "name": name,
            }
        )
    added.sort(key=lambda r: (r["date"], r["rev"]))
    revisions = added
    if not revisions:
        raise ValueError("no revisions discovered")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "revisions": revisions,
                "releases": releases,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    (destination / "matrix.json").write_text(
        json.dumps(
            {"include": [{"rev": r["rev"], "name": r["name"]} for r in revisions]},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    discover(args.destination, args.limit)
