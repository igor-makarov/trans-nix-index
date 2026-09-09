#!/usr/bin/env python3
"""External channel discovery. Emit a bounded, immutable input bundle for Nix."""
import argparse
import json
import os
from pathlib import Path
import re
import tarfile
import urllib.error
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


def prefixes(prefix):
    marker = ""
    while True:
        query = urllib.parse.urlencode(
            {"prefix": prefix, "delimiter": "/", "marker": marker}
        )
        root = ET.fromstring(get(BASE + "?" + query))
        prefixes = [e.text for e in root.findall("{*}CommonPrefixes/{*}Prefix")]
        yield from (p.rstrip("/").split("/")[-1] for p in prefixes)
        if root.findtext("{*}IsTruncated") != "true":
            break
        if not prefixes:
            raise ValueError("truncated listing without pagination cursor")
        marker = prefixes[-1]


def channels():
    return prefixes("nixos/unstable/")


def release_tips():
    """Release-branch pointers, deliberately outside the extraction matrix."""
    releases = {}
    for release in sorted(prefixes("nixos/")):
        if not re.fullmatch(r"\d{2}\.\d{2}", release) or release < "13.10":
            continue
        pattern = rf"nixos-{re.escape(release)}\.(\d+)\.([0-9a-f]{{7,12}})"
        published = [
            (int(match[1]), name, match[2])
            for name in prefixes(f"nixos/{release}/")
            if (match := re.fullmatch(pattern, name))
        ]
        if not published:
            continue  # A beta-only channel has not shipped yet.
        build, name, short = max(published)
        try:
            sha = get(BASE + f"nixos/{release}/{name}/git-revision").decode().strip()
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            # Older archives lack git-revision; resolve their recorded hash.
            sha = short
        else:
            if not re.fullmatch(r"[0-9a-f]{40}", sha) or not sha.startswith(short):
                raise ValueError("invalid release git-revision")
        api = "https://api.github.com/repos/NixOS/nixpkgs/commits/"
        try:
            commit = json.loads(get(api + sha))
        except urllib.error.HTTPError as error:
            if error.code != 422 or sha != short:
                raise
            # Old seven-character hashes collide across GitHub's fork network.
            # Read the archive's authoritative metadata, without extracting it.
            url = BASE + f"nixos/{release}/{name}/nixexprs.tar.xz"
            with urllib.request.urlopen(url, timeout=90) as response:
                with tarfile.open(fileobj=response, mode="r|xz") as archive:
                    sha = next(
                        archive.extractfile(member).read(128).decode().strip()
                        for member in archive
                        if member.isfile()
                        and member.name
                        in (f"{name}/.git-revision", f"{name}/nixpkgs/.git-revision")
                    )
            if not re.fullmatch(r"[0-9a-f]{40}", sha) or not sha.startswith(short):
                raise ValueError("invalid archived release git-revision")
            commit = json.loads(get(api + sha))
        sha = commit["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or not sha.startswith(short):
            raise ValueError("release commit identity mismatch")
        releases[release] = {
            "rev": sha,
            "date": commit["commit"]["committer"]["date"][:10],
            "build": build,
            "name": name,
        }
    if not releases:
        raise ValueError("no releases discovered")
    return releases


def channel_key(name):
    match = re.fullmatch(r"nixos-(\d+)\.(\d+)pre(\d+)\.([0-9a-f]{7,12})", name)
    return tuple(map(int, match.groups()[:3])) if match else None


def discover(destination, limit=None):
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("limit must be a positive integer or omitted")
    releases = release_tips()
    candidates = sorted((n for n in channels() if channel_key(n)), key=channel_key)
    # Select a complete dataset, not an incremental tail.
    if limit is not None:
        candidates = candidates[-limit:]
    added = []
    for name in candidates:
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
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    discover(args.destination, args.limit)
