#!/usr/bin/env python3
"""Stage identity, fail-closed lookups, canonical archives, and safe unpacking."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "pipeline_artifact", Path(sys.argv[1]) / "pipeline-artifact.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
A, B = ("sha256:" + c * 64 for c in "ab")


class Fake(m.PipelineRegistry):
    def __init__(self):
        self.repository = "ghcr.io/example/pipeline-trial"
        self.tags = {}
        self.manifests = {}
        self.operations = []
        self.break_verification = False

    def run(self, *args, cwd=None):
        self.operations.append(args)
        if args[0] == "resolve":
            tag = args[1].split(":")[-1]
            if tag not in self.tags:
                raise subprocess.CalledProcessError(
                    1, args, stderr="Error: manifest: not found"
                )
            return self.tags[tag]
        if args[:2] == ("manifest", "fetch"):
            return json.dumps(self.manifests[args[2].split("@")[1]])
        if args[0] == "push":
            archive = Path(cwd) / "data.tar.gz"
            annotations = dict(
                args[i + 1].split("=", 1)
                for i, x in enumerate(args)
                if x == "--annotation"
            )
            layer = {
                "mediaType": "application/gzip",
                "size": archive.stat().st_size,
                "digest": "sha256:" + m.checksum(archive),
            }
            self.manifests[B] = {
                "artifactType": m.TYPE,
                "layers": [layer],
                "annotations": annotations,
            }
            if self.break_verification:
                layer["digest"] = A
            self.tags[args[1].split(":")[-1]] = B
            return ""
        if args[0] == "tag":
            self.tags[args[2]] = args[1].split("@")[1]
            return ""
        raise AssertionError(args)


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    data = root / "data"
    data.mkdir()
    (data / "b").write_text("two")
    (data / "a").write_text("one")
    m.pack(data, root / "one.gz")
    os.utime(data / "a", (100, 100))
    os.chmod(data / "b", 0o600)
    m.pack(data, root / "two.gz")
    assert (root / "one.gz").read_bytes() == (root / "two.gz").read_bytes()
    m.unpack(root / "one.gz", root / "unpacked")
    assert (root / "unpacked/a").read_text() == "one"
    for name, kind in [
        ("../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("link", tarfile.SYMTYPE),
    ]:
        with tarfile.open(root / "bad.gz", "w:gz") as archive:
            info = tarfile.TarInfo(name)
            info.type = kind
            archive.addfile(info, io.BytesIO())
        try:
            m.unpack(root / "bad.gz", root / "bad")
            raise AssertionError("unsafe member accepted")
        except ValueError:
            assert not (root / "bad").exists()
    registry = Fake()
    assert m.reusable(registry, "revision-index", A) is None
    assert registry.publish("revision-index", data, A) == B
    assert m.reusable(registry, "revision-index", A) == B
    assert m.reusable(registry, "revision-index", B) is None
    assert m.reusable(registry, "revision-index", A, True) is None
    assert registry.manifest(B)["annotations"][m.INPUT] == A
    for failure in [
        "401 Unauthorized",
        "403 Forbidden",
        "500 Internal Server Error",
        "connection reset",
        "timeout",
    ]:
        with patch.object(
            registry,
            "run",
            side_effect=subprocess.CalledProcessError(1, [], stderr=failure),
        ):
            try:
                registry.lookup("revision-index")
                raise AssertionError("transport error treated as a miss")
            except subprocess.CalledProcessError:
                pass
    broken = Fake()
    broken.break_verification = True
    try:
        broken.publish("revision-index", data, A)
        raise AssertionError("verification failure accepted")
    except ValueError:
        assert "revision-index" not in broken.tags
    try:
        registry.manifest(B, "site")
        raise AssertionError("wrong stage accepted")
    except ValueError:
        pass
print(
    "Pipeline artifacts: stable archives, input-based reuse, force, failures retry, digest validation, safe extraction: OK"
)
