#!/usr/bin/env python3
"""Named OCI stage artifacts. Only successful outputs acknowledge input digests."""
import argparse
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from oci import Registry
from snapshot import checksum

TYPE = "application/vnd.trans-nix-index.pipeline.v1"
INPUT = "io.trans-nix-index.input"
STAGE = "io.trans-nix-index.stage"
TAGS = {
    "revision-manifest",
    "revision-index",
    "enriched-snapshot",
    "site",
    "deployed-site",
}


def digest(value):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("expected immutable sha256 digest")
    return value


def pack(root, output):
    """Canonical archive: neither clock, ownership nor filesystem order affects it."""
    root = Path(root)
    with open(output, "wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0
    ) as zipped, tarfile.open(
        fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT
    ) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("symlink in stage artifact")
            if not path.is_file():
                continue
            info = tarfile.TarInfo(path.relative_to(root).as_posix())
            info.size = path.stat().st_size
            info.mode = 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)


def unpack(source, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("unpack destination already exists")
    destination.mkdir(parents=True)
    try:
        with tarfile.open(source, "r:gz") as archive:
            seen = set()
            for member in archive:
                parts = PurePosixPath(member.name).parts
                if (
                    not member.isfile()
                    or not parts
                    or member.name.startswith("/")
                    or ".." in parts
                    or member.name != "/".join(parts)
                    or member.name in seen
                ):
                    raise ValueError("unsafe or duplicate archive member")
                seen.add(member.name)
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    except Exception:
        shutil.rmtree(destination)
        raise


class PipelineRegistry(Registry):
    def lookup(self, tag):
        try:
            return digest(self.run("resolve", f"{self.repository}:{tag}"))
        except subprocess.CalledProcessError as error:
            message = error.stderr or ""
            # Only a definitive missing manifest/repository is a cache miss.
            if re.search(
                r"MANIFEST_UNKNOWN|NAME_UNKNOWN|response status code 404", message
            ) or message.rstrip().endswith(": not found"):
                return None
            raise

    def run(self, *args, cwd=None):
        return subprocess.check_output(
            ["oras", *args, "--registry-config", self.config],
            cwd=cwd,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

    def manifest(self, reference, stage=None):
        value = json.loads(
            self.run("manifest", "fetch", f"{self.repository}@{digest(reference)}")
        )
        layers = value.get("layers", [])
        if (
            value.get("artifactType") != TYPE
            or len(layers) != 1
            or layers[0].get("mediaType") != "application/gzip"
        ):
            raise ValueError("unexpected stage artifact")
        if stage and value.get("annotations", {}).get(STAGE) != stage:
            raise ValueError("wrong artifact stage")
        return value

    def download_stage(self, reference, stage, destination):
        layer = self.manifest(reference, stage)["layers"][0]
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "data.tar.gz"
            self.run(
                "blob",
                "fetch",
                f"{self.repository}@{digest(layer['digest'])}",
                "--output",
                str(archive),
            )
            if (
                archive.stat().st_size != layer["size"]
                or "sha256:" + checksum(archive) != layer["digest"]
            ):
                raise ValueError("stage archive checksum/size mismatch")
            unpack(archive, destination)

    def publish(self, stage, source, upstream):
        if upstream:
            digest(upstream)
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "data.tar.gz"
            pack(source, archive)
            # Never move the named tag until the uploaded candidate is verified.
            candidate = f"candidate-{os.environ.get('GITHUB_RUN_ID', 'local')}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}-{stage}"
            self.run(
                "push",
                f"{self.repository}:{candidate}",
                "--artifact-type",
                TYPE,
                "--annotation",
                "org.opencontainers.image.created=1970-01-01T00:00:00Z",
                "--annotation",
                f"org.opencontainers.image.source=https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'igor-makarov/trans-nix-index')}",
                "--annotation",
                f"{STAGE}={stage}",
                "--annotation",
                f"{INPUT}={upstream}",
                "data.tar.gz:application/gzip",
                cwd=temporary,
            )
            result = self.resolve(candidate)
            manifest = self.manifest(result, stage)
            if (
                manifest["layers"][0]["digest"] != "sha256:" + checksum(archive)
                or manifest["annotations"].get(INPUT) != upstream
            ):
                raise ValueError("published stage verification failed")
            self.run("tag", f"{self.repository}@{result}", stage)
            return result


def reusable(registry, stage, upstream, force=False, previous=None):
    if previous is None:
        previous = registry.lookup(stage)
    if (
        previous
        and not force
        and registry.manifest(previous, stage).get("annotations", {}).get(INPUT)
        == upstream
    ):
        return previous
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["check", "pull", "publish", "deployed", "deployment-check", "resolve"],
    )
    parser.add_argument("stage", choices=sorted(TAGS))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--input", default="")
    parser.add_argument("--digest")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    registry = PipelineRegistry(args.repository)
    try:
        if args.command == "resolve":
            print(registry.lookup(args.stage) or "")
        elif args.command == "deployment-check":
            print(
                json.dumps(
                    {"run": registry.lookup("deployed-site") != digest(args.digest)}
                )
            )
        elif args.command == "check":
            if args.input:
                digest(args.input)
            previous = registry.lookup(args.stage) or ""
            if previous:
                registry.manifest(previous, args.stage)
            result = reusable(registry, args.stage, args.input, args.force, previous)
            print(
                json.dumps(
                    {
                        "run": result is None,
                        "digest": result or "",
                        "previous": previous or "",
                    }
                )
            )
        elif args.command == "publish":
            print(registry.publish(args.stage, args.path, args.input))
        elif args.command == "pull":
            registry.download_stage(args.digest, args.stage, args.path)
        else:
            registry.manifest(args.digest, "site")
            if args.stage != "deployed-site":
                raise ValueError("invalid deployment marker")
            registry.run(
                "tag", f"{registry.repository}@{digest(args.digest)}", "deployed-site"
            )
    except subprocess.CalledProcessError as error:
        print(error.stderr or str(error), file=sys.stderr)
        raise SystemExit(error.returncode) from error
    finally:
        registry.close()


if __name__ == "__main__":
    main()
