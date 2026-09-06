#!/usr/bin/env python3
"""Self-contained release archives: local files, checksums, no remote pins."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

INDEX_FILES = {
    "versions.json",
    "history.json",
    "stats.json",
    "revisions.json",
    "releases.json",
}


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def allowed(name):
    parts = PurePosixPath(name).parts
    if name in INDEX_FILES or name == "manifest.json":
        return True
    return (
        len(parts) == 2
        and parts[0] in {"artifacts", "state"}
        and parts[1] not in {".", ".."}
        and name == "/".join(parts)
        and parts[1].endswith((".json", ".jsonl"))
    )


def inventory(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise ValueError(f"snapshot contains symlink: {path}")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if not allowed(name):
            raise ValueError(f"unexpected snapshot file: {name}")
        if name != "manifest.json":
            result[name] = checksum(path)
    return result


def verify(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("schema") != 2 or manifest.get("files") != inventory(root):
        raise ValueError("snapshot manifest/checksum mismatch")
    required = INDEX_FILES | {"state/graph.jsonl", "artifacts/outs-indexed.json"}
    if not required <= manifest["files"].keys():
        raise ValueError("snapshot missing required index or crawl data")


def pack(root, output):
    root = Path(root)
    files = inventory(root)
    (root / "manifest.json").write_text(
        json.dumps({"schema": 2, "files": files}, indent=2, sort_keys=True) + "\n"
    )
    verify(root)
    with tarfile.open(output, "w:gz") as archive:
        for name in sorted(files.keys() | {"manifest.json"}):
            archive.add(root / name, arcname=name, recursive=False)


def unpack(archive, destination):
    destination = Path(destination)
    with tarfile.open(archive, "r:gz") as source:
        seen = set()
        for member in source:
            name = member.name
            if not allowed(name) or name in seen or not member.isfile():
                raise ValueError(f"unexpected snapshot member: {name}")
            seen.add(name)
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as stream, path.open("wb") as output:
                shutil.copyfileobj(stream, output)
    verify(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        type=Path,
        help="Staging directory containing only plain JSON/JSONL files",
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pack(args.root, args.output)
