#!/usr/bin/env python3
"""One-time, non-destructive migration of release archives to OCI artifacts."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from oci import Registry
from snapshot import checksum


def api(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    latest = api(f"repos/{repo}/releases/latest")["tag_name"]
    releases = []
    page = 1
    while True:
        batch = api(f"repos/{repo}/releases?per_page=100&page={page}")
        if not batch:
            break
        releases.extend(r for r in batch if not r["draft"])
        page += 1
    registry = Registry()
    migrated = {}
    try:
        for release in releases:
            tag = release["tag_name"]
            assets = release["assets"]
            if len(assets) != 1 or assets[0]["name"] != "data.tar.gz":
                raise ValueError(
                    f"unexpected assets on {tag}; refusing partial migration"
                )
            asset = assets[0]
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                archive = directory / "data.tar.gz"
                print(f"Migrating {tag}", flush=True)
                subprocess.run(
                    [
                        "gh",
                        "release",
                        "download",
                        tag,
                        "--repo",
                        repo,
                        "--pattern",
                        "data.tar.gz",
                        "--dir",
                        str(directory),
                    ],
                    check=True,
                )
                expected = asset.get("digest")
                if expected != f"sha256:{checksum(archive)}":
                    raise ValueError(f"release checksum mismatch: {tag}")
                digest = registry.push(tag, archive)
                restored = directory / "verified.tar.gz"
                registry.download(digest, restored)
                if checksum(restored) != checksum(archive):
                    raise ValueError(f"OCI round-trip mismatch: {tag}")
                migrated[tag] = {"digest": digest, "archiveDigest": expected}
                print(f"Verified {tag} -> {registry.repository}@{digest}", flush=True)
        registry.tag_latest(migrated[latest]["digest"])
        print(
            json.dumps({"latest": latest, "snapshots": migrated}, indent=2), flush=True
        )
        print(
            "Migration verified. Releases and Git tags have NOT been deleted.",
            flush=True,
        )
    finally:
        registry.close()


if __name__ == "__main__":
    main()
