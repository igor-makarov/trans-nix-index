#!/usr/bin/env python3
"""Discover published channels using multiplexed HTTP; emit immutable Nix inputs."""
import argparse
import asyncio
import io
import json
import lzma
import os
from pathlib import Path
import re
import tarfile
import time
import xml.etree.ElementTree as ET

import httpx

BASE = "https://nix-releases.s3.amazonaws.com/"
DOWNLOAD_BASE = "https://releases.nixos.org/"
API = "https://api.github.com/repos/NixOS/nixpkgs/commits/"


def channel_key(name):
    match = re.fullmatch(r"nixos-(\d+)\.(\d+)pre(\d+)\.([0-9a-f]{7,12})", name)
    return tuple(map(int, match.groups()[:3])) if match else None


def validate_sha(sha, short):
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not sha.startswith(short):
        raise ValueError(f"invalid commit identity: {sha!r}, expected prefix {short}")
    return sha


class Discovery:
    def __init__(self, client):
        self.client = client
        self.commits = {}

    async def get(self, url, **kwargs):
        headers = {}
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token and url.startswith(API):
            headers["Authorization"] = f"Bearer {token}"
        for attempt in range(3):
            try:
                response = await self.client.get(url, headers=headers, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                if (
                    error.response.status_code not in (429, 500, 502, 503, 504)
                    or attempt == 2
                ):
                    raise
            except httpx.TransportError:
                if attempt == 2:
                    raise
            await asyncio.sleep(0.5 * (attempt + 1))

    async def prefixes(self, prefix):
        marker, names = "", []
        while True:
            response = await self.get(
                BASE, params={"prefix": prefix, "delimiter": "/", "marker": marker}
            )
            root = ET.fromstring(response.content)
            entries = [e.text for e in root.findall("{*}CommonPrefixes/{*}Prefix")]
            names.extend(p.rstrip("/").split("/")[-1] for p in entries)
            if root.findtext("{*}IsTruncated") != "true":
                return names
            cursor = root.findtext("{*}NextMarker") or (
                entries[-1] if entries else None
            )
            if not cursor or cursor <= marker:
                raise ValueError("truncated listing without advancing cursor")
            marker = cursor

    async def commit(self, sha):
        if sha not in self.commits:
            self.commits[sha] = asyncio.create_task(self.get(API + sha))
        return (await self.commits[sha]).json()

    async def archived_sha(self, channel, name, short):
        # Incrementally decode only as far as the metadata member. Never extract
        # archive paths onto the filesystem. Release-only legacy fallback.
        url = DOWNLOAD_BASE + f"nixos/{channel}/{name}/nixexprs.tar.xz"
        decoder, data = lzma.LZMADecompressor(), bytearray()
        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                data.extend(decoder.decompress(chunk))
                if len(data) > 64 * 1024 * 1024:
                    raise ValueError("release metadata not found within 64 MiB")
                try:
                    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
                        for member in archive:
                            if member.isfile() and member.name in (
                                f"{name}/.git-revision",
                                f"{name}/nixpkgs/.git-revision",
                            ):
                                raw = archive.extractfile(member).read(128)
                                return validate_sha(raw.decode().strip(), short)
                except (tarfile.ReadError, EOFError):
                    pass  # Need more streamed bytes.
        raise ValueError(f"missing archived git-revision: {name}")

    async def revision(self, channel, name, release=False):
        short = name.rsplit(".", 1)[1]
        try:
            response = await self.get(
                DOWNLOAD_BASE + f"nixos/{channel}/{name}/git-revision"
            )
            sha = validate_sha(response.text.strip(), short)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404 or not release:
                raise
            sha = await self.archived_sha(channel, name, short)
        commit = await self.commit(sha)
        validate_sha(commit["sha"], sha)
        return {
            "rev": sha,
            "date": commit["commit"]["committer"]["date"][:10],
            "name": name,
        }

    async def release_tip(self, release):
        pattern = rf"nixos-{re.escape(release)}\.(\d+)\.([0-9a-f]{{7,12}})"
        builds = [
            (int(m[1]), name)
            for name in await self.prefixes(f"nixos/{release}/")
            if (m := re.fullmatch(pattern, name))
        ]
        if not builds:
            return release, None
        build, name = max(builds)
        record = await self.revision(release, name, release=True)
        return release, dict(record, build=build)

    async def releases(self):
        names = [
            n
            for n in await self.prefixes("nixos/")
            if re.fullmatch(r"\d{2}\.\d{2}", n) and n >= "13.10"
        ]
        result = dict(
            (k, v)
            for k, v in await asyncio.gather(
                *(self.release_tip(n) for n in sorted(names))
            )
            if v
        )
        if not result:
            raise ValueError("no releases discovered")
        return result

    async def unstable(self, limit):
        names = sorted(
            (n for n in await self.prefixes("nixos/unstable/") if channel_key(n)),
            key=channel_key,
        )
        if limit is not None:
            names = names[-limit:]
        records = await asyncio.gather(*(self.revision("unstable", n) for n in names))
        unique = {}
        for record in records:
            unique.setdefault(record["rev"], record)
        if not unique:
            raise ValueError("no revisions discovered")
        return sorted(unique.values(), key=lambda r: (r["date"], r["rev"]))


async def discover(destination, limit=None):
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("limit must be a positive integer or omitted")
    started = time.monotonic()
    async with httpx.AsyncClient(
        http2=True, timeout=120, headers={"User-Agent": "trans-nix-index"}
    ) as client:
        discovery = Discovery(client)
        revisions, releases = await asyncio.gather(
            discovery.unstable(limit), discovery.releases()
        )
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in {
        "manifest": {"schema": 1, "revisions": revisions, "releases": releases},
        "matrix": {
            "include": [{"rev": r["rev"], "name": r["name"]} for r in revisions]
        },
    }.items():
        (destination / f"{name}.json").write_text(
            json.dumps(value, sort_keys=True, indent=2) + "\n"
        )
    print(
        f"Discovered {len(revisions)} revisions and {len(releases)} releases in {time.monotonic()-started:.2f}s",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(discover(args.destination, args.limit))
