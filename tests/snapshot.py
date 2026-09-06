#!/usr/bin/env python3
"""Archive integrity, safe extraction, and recovery without older releases."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(source / "tools"))
from snapshot import pack, unpack, verify

with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary)
    root = base / "seed"
    (root / "artifacts").mkdir(parents=True)
    (root / "state").mkdir()
    values = {
        "revisions.json": [{"rev": "a", "date": "2026-01-01"}],
        "releases.json": {},
        "versions.json": {"revisionCount": 1, "attrs": {"hello": {"1": None}}},
        "history.json": {
            "revisionCount": 1,
            "skipped": [],
            "attrs": {"hello": {"1": [0, None]}},
        },
        "stats.json": {"totals": {"revisions": 1}},
        "artifacts/outpaths-x86_64-linux.json": {"revisionCount": 1, "attrs": {}},
        "artifacts/tip-outpaths-x86_64-linux.json": {"revisionCount": 1, "attrs": {}},
        "artifacts/outs-x86_64-linux.json": {},
    }
    for name, value in values.items():
        (root / name).write_text(json.dumps(value))
    for stem in ("info-indexed", "refs-indexed", "closures", "outs-indexed"):
        (root / f"artifacts/{stem}.json").write_bytes(b"{}")
    (root / "state/graph.jsonl").write_bytes(b"")
    archive = base / "data.tar.gz"
    pack(root, archive)
    restored = base / "restored"
    restored.mkdir()
    unpack(archive, restored)
    subprocess.run(
        ["python3", str(source / "tools/validate-data.py"), str(restored)], check=True
    )
    work = base / "work"
    subprocess.run(
        ["bash", str(source / "tools/restore-outpaths-state.sh"), str(restored)],
        env={**os.environ, "MULTIVERSE_ROOT": str(work)},
        check=True,
    )
    assert (work / "index/.outpaths/graph.jsonl").is_file()
    assert not list(restored.rglob("*.gz"))
    with tarfile.open(archive, "r:gz") as contents:
        assert all(not member.name.endswith(".gz") for member in contents)
    assert (work / "index/.outpaths/data/prev/outpaths-x86_64-linux.json").is_file()
    (restored / "versions.json").write_text("{}")
    try:
        verify(restored)
    except ValueError:
        pass
    else:
        raise AssertionError("tampering accepted")
    for name, symlink in [
        ("../escape.json", False),
        ("/absolute.json", False),
        ("artifacts/../../escape.json", False),
        ("artifacts/link.json", True),
    ]:
        with tarfile.open(archive, "w:gz") as out:
            member = tarfile.TarInfo(name)
            if symlink:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../escape"
                out.addfile(member)
            else:
                member.size = 2
                out.addfile(member, io.BytesIO(b"{}"))
        try:
            unpack(archive, restored)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe member accepted: {name}")
print("snapshot recovery, checksums, validation, and unsafe archives: OK")
