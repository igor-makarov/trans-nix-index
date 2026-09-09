#!/usr/bin/env python3
"""Offline discovery bounds and full fold coverage."""
import importlib.util
import json
import io
import tarfile
from unittest.mock import patch
from urllib.error import HTTPError
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
    release = {
        "26.05": {
            "rev": "a" * 40,
            "date": "2026-06-01",
            "build": 1000,
            "name": "nixos-26.05.1000." + "a" * 12,
        }
    }
    discovery.prefixes = lambda prefix: {
        "nixos/": ["12.10", "26.05-small", "26.05", "26.11", "unstable"],
        "nixos/26.05/": [
            "nixos-26.05.999." + "b" * 7,
            release["26.05"]["name"],
            "nixos-26.05beta2000." + "b" * 12,
        ],
        "nixos/26.11/": ["nixos-26.11beta3000." + "b" * 12],
    }[prefix]
    discovery.get = lambda url: (
        ("a" * 40).encode()
        if url.endswith("/git-revision")
        else json.dumps(
            {"sha": "a" * 40, "commit": {"committer": {"date": "2026-06-01T00:00:00Z"}}}
        ).encode()
    )
    assert discovery.release_tips() == release
    # Older channels lack git-revision and have ambiguous short API hashes.
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:xz") as archive:
        member = tarfile.TarInfo(release["26.05"]["name"] + "/nixpkgs/.git-revision")
        member.size = 40
        archive.addfile(member, io.BytesIO(b"a" * 40))

    def legacy_get(url):
        if url.endswith("/git-revision"):
            raise HTTPError(url, 404, "missing", {}, None)
        if url.endswith("/" + "a" * 12):
            raise HTTPError(url, 422, "ambiguous", {}, None)
        assert url.endswith("/" + "a" * 40)
        return json.dumps(
            {"sha": "a" * 40, "commit": {"committer": {"date": "2026-06-01T00:00:00Z"}}}
        ).encode()

    discovery.get = legacy_get
    with patch.object(
        discovery.urllib.request, "urlopen", return_value=io.BytesIO(payload.getvalue())
    ):
        assert discovery.release_tips() == release
    discovery.get = lambda url: b"bad-sha"
    try:
        discovery.release_tips()
    except ValueError:
        pass
    else:
        raise AssertionError("invalid release revision accepted")
    discovery.release_tips = lambda: release
    discovery.channels = lambda: [r["name"] for r in reversed(revs)]
    requests = []

    def get(url):
        requests.append(url)
        if url.endswith("/git-revision"):
            return next(r["rev"].encode() for r in revs if r["name"] in url)
        return json.dumps(
            {
                "commit": {
                    "committer": {
                        "date": next(r["date"] for r in revs if r["rev"] in url)
                    }
                }
            }
        ).encode()

    discovery.get = get
    discovery.discover(root / "fresh", 1)
    fresh = fold.read(root / "fresh/manifest.json")
    assert fresh["revisions"] == revs[-1:]
    assert fresh["releases"] == release
    assert len(requests) == 2
    discovery.discover(root / "larger", 3)
    assert fold.read(root / "larger/manifest.json")["revisions"] == revs
    assert fold.read(root / "larger/matrix.json") == {
        "include": [{"rev": r["rev"], "name": r["name"]} for r in revs]
    }
    discovery.discover(root / "maximum", 200)
    assert fold.read(root / "maximum/manifest.json")["revisions"] == revs
    discovery.discover(root / "unlimited")
    assert fold.read(root / "unlimited/manifest.json")["revisions"] == revs
    discovery.discover(root / "large-limit", 1000)
    assert fold.read(root / "large-limit/manifest.json")["revisions"] == revs
    for limit in (0, -1, 1.5, True, "200"):
        try:
            discovery.discover(root / "bad", limit)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid limit accepted")
print(
    "full fold, disappearance/reappearance, deterministic repeat, exact input coverage, bounded discovery: OK"
)
