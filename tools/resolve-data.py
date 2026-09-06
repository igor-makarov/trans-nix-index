#!/usr/bin/env python3
"""Resolve one release once, verify its archive, and materialize a data snapshot."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request

from snapshot import checksum, unpack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "igor-makarov/trans-nix-index"),
    )
    parser.add_argument("--tag", help="Replay a specific release instead of latest")
    args = parser.parse_args()
    endpoint = f"tags/{args.tag}" if args.tag else "latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "trans-nix-index"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{args.repo}/releases/{endpoint}", headers=headers
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.load(response)
    asset = next(a for a in release["assets"] if a["name"] == "data.tar.gz")
    digest = asset.get("digest", "")
    if not digest or not digest.startswith("sha256:"):
        raise ValueError("release asset has no SHA-256 digest")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.destination.parent) as temporary:
        temporary = Path(temporary)
        archive = temporary / "data.tar.gz"
        # Public download: do not forward API credentials across CDN redirects.
        with urllib.request.urlopen(
            asset["browser_download_url"], timeout=120
        ) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = checksum(archive)
        if digest != f"sha256:{actual}":
            raise ValueError("snapshot archive checksum mismatch")
        snapshot = temporary / "snapshot"
        snapshot.mkdir()
        unpack(archive, snapshot)
        if args.destination.exists():
            shutil.rmtree(args.destination)
        snapshot.rename(args.destination)
    print(f"Resolved {release['tag_name']} ({digest})", flush=True)


if __name__ == "__main__":
    main()
