#!/usr/bin/env python3
"""Digest pinning and archive validation without network access."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
from oci import ARTIFACT_TYPE, Registry

registry = object.__new__(Registry)
registry.repository = "ghcr.io/example/snapshots"
payload = b"test archive bytes"
digest = "sha256:" + hashlib.sha256(payload).hexdigest()
manifest_digest = "sha256:" + "a" * 64
manifest = {
    "artifactType": ARTIFACT_TYPE,
    "layers": [
        {
            "mediaType": "application/gzip",
            "digest": digest,
            "size": len(payload),
            "annotations": {"org.opencontainers.image.title": "data.tar.gz"},
        }
    ],
}
commands = []


def run(*args, **kwargs):
    commands.append(args)
    if args[0] == "resolve":
        return manifest_digest
    if args[:2] == ("manifest", "fetch"):
        return json.dumps(manifest)
    if args[:2] == ("blob", "fetch"):
        Path(args[args.index("--output") + 1]).write_bytes(payload)
        return ""
    raise AssertionError(args)


registry.run = run
with tempfile.TemporaryDirectory() as temporary:
    archive = Path(temporary) / "data.tar.gz"
    pinned = registry.resolve("latest")
    registry.download(pinned, archive)
    assert archive.read_bytes() == payload
    assert commands[1][2].endswith("@" + manifest_digest)
    assert commands[2][2].endswith("@" + digest)
    assert registry.resolve(manifest_digest) == manifest_digest
    assert commands[-1][1].endswith("@" + manifest_digest)
    for field, bad in [
        ("size", 0),
        ("digest", "sha256:" + "b" * 64),
        ("mediaType", "text/plain"),
    ]:
        old = manifest["layers"][0][field]
        manifest["layers"][0][field] = bad
        try:
            registry.download(pinned, archive)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid {field} accepted")
        manifest["layers"][0][field] = old
    manifest["layers"].append(manifest["layers"][0])
    try:
        registry.descriptor(pinned)
    except ValueError:
        pass
    else:
        raise AssertionError("multi-file artifact accepted")
print(
    "OCI: digest-pinned requests, checksum/size verification, single-archive enforcement: OK"
)
