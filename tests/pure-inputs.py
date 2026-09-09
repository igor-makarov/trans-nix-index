#!/usr/bin/env python3
"""Offline discovery bounds and full fold coverage."""
import importlib.util
import json
import io
import tarfile
from pathlib import Path
import tempfile
import sys


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(sys.argv[1]) / f"{name}.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fold = module("merge-revisions")
discovery = module("discover-pipeline")
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    revs = [
        {
            "rev": str(i) * 40,
            "date": f"2026-01-0{i}",
            "name": f"nixos-26.05pre{i}.{str(i) * 12}",
        }
        for i in range(1, 4)
    ]
    manifest = {
        "schema": 1,
        "revisions": revs,
        "releases": {},
    }
    files = {}
    for r, attrs in zip(revs, [{"a": "1", "b": "1"}, {"a": "2"}, {"a": "1", "b": "1"}]):
        file = root / r["rev"]
        file.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "rev": r["rev"],
                    "attrs": {a: {"version": v} for a, v in attrs.items()},
                }
            )
        )
        files[r["rev"]] = str(file)
    whole = fold.merge(manifest, files)
    assert whole == fold.merge(manifest, files)
    assert whole[1]["attrs"]["a"]["1"] == [[0, 0], [2, None]]
    assert whole[1]["attrs"]["b"]["1"] == [[0, 0], [2, None]]
    for bad_manifest, bad_files in [
        (manifest, {}),
        (manifest, {r["rev"]: files[r["rev"]] for r in revs[1:]}),
        (dict(manifest, revisions=revs[:1]), files),
        (dict(manifest, revisions=[revs[0], revs[0]]), files),
    ]:
        try:
            fold.merge(bad_manifest, bad_files)
        except ValueError:
            pass
        else:
            raise AssertionError("missing, extra, or duplicate inputs accepted")
    import asyncio
    import httpx

    async def check():
        def handle(request):
            path = request.url.path
            if request.url.host == "nix-releases.s3.amazonaws.com":
                prefix = request.url.params["prefix"]
                names = (
                    [r["name"] for r in revs]
                    if prefix == "nixos/unstable/"
                    else (
                        ["26.05"]
                        if prefix == "nixos/"
                        else ["nixos-26.05.1000." + "a" * 12]
                    )
                )
                body = (
                    "<ListBucketResult><IsTruncated>false</IsTruncated>"
                    + "".join(
                        f"<CommonPrefixes><Prefix>{prefix}{n}/</Prefix></CommonPrefixes>"
                        for n in names
                    )
                    + "</ListBucketResult>"
                )
                return httpx.Response(200, text=body)
            if path.endswith("/git-revision"):
                sha = next((r["rev"] for r in revs if r["name"] in path), "a" * 40)
                return httpx.Response(200, text=sha)
            sha = path.rsplit("/", 1)[1]
            return httpx.Response(
                200,
                json={
                    "sha": sha,
                    "commit": {"committer": {"date": "2026-01-01T00:00:00Z"}},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            d = discovery.Discovery(client)
            assert len(await d.unstable(None)) == 3
            assert len(await d.unstable(1)) == 1
            releases = await d.releases()
            assert releases["26.05"]["build"] == 1000
            assert releases["26.05"]["rev"] == "a" * 40
        name = "nixos-14.04.630." + "a" * 7
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:xz") as archive:
            member = tarfile.TarInfo(name + "/nixpkgs/.git-revision")
            member.size = 40
            archive.addfile(member, io.BytesIO(b"a" * 40))

        def legacy(request):
            if request.url.path.endswith("/git-revision"):
                return httpx.Response(404)
            if request.url.path.endswith(".tar.xz"):
                return httpx.Response(200, content=payload.getvalue())
            return httpx.Response(
                200,
                json={"sha": "a" * 40, "commit": {"committer": {"date": "2014-01-01"}}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(legacy)) as client:
            d = discovery.Discovery(client)
            assert (await d.revision("14.04", name, release=True))["rev"] == "a" * 40
            try:
                await d.revision("unstable", name)
            except httpx.HTTPStatusError as error:
                assert error.response.status_code == 404
            else:
                raise AssertionError("unstable 404 must not use archive fallback")
        for limit in (0, -1, True, "200"):
            try:
                await discovery.discover(root / "bad", limit)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid limit accepted")

    asyncio.run(check())
print("fold and async discovery: OK")
