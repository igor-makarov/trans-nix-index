#!/usr/bin/env python3
"""Resolve an OCI tag once, then download and verify the immutable snapshot."""
import argparse
from pathlib import Path
import shutil
import tempfile

from oci import Registry
from snapshot import unpack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--repository", help="OCI repository (defaults to our public GHCR package)"
    )
    reference = parser.add_mutually_exclusive_group()
    reference.add_argument(
        "--tag", default="latest", help="Snapshot tag to resolve once"
    )
    reference.add_argument(
        "--digest", help="Replay an immutable sha256 manifest digest"
    )
    args = parser.parse_args()
    registry = Registry(args.repository)
    try:
        digest = registry.resolve(args.digest or args.tag)
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=args.destination.parent) as temporary:
            temporary = Path(temporary)
            archive = temporary / "data.tar.gz"
            registry.download(digest, archive)
            snapshot = temporary / "snapshot"
            snapshot.mkdir()
            unpack(archive, snapshot)
            if args.destination.exists():
                shutil.rmtree(args.destination)
            snapshot.rename(args.destination)
        print(f"Resolved {registry.repository}@{digest}", flush=True)
    finally:
        registry.close()


if __name__ == "__main__":
    main()
