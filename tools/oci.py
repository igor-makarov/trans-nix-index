"""OCI transport for one self-contained data.tar.gz; never a container image."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from snapshot import checksum

ARTIFACT_TYPE = "application/vnd.trans-nix-index.snapshot.v1"
DEFAULT_REPOSITORY = "ghcr.io/igor-makarov/trans-nix-index-data"


class Registry:
    def __init__(self, repository=None):
        self.repository = repository or os.environ.get(
            "SNAPSHOT_REPOSITORY", DEFAULT_REPOSITORY
        )
        self.temporary = tempfile.TemporaryDirectory()
        self.config = str(Path(self.temporary.name) / "auth.json")
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            subprocess.run(
                [
                    "oras",
                    "login",
                    self.repository.split("/")[0],
                    "--registry-config",
                    self.config,
                    "--username",
                    os.environ.get("GITHUB_ACTOR", "igor-makarov"),
                    "--password-stdin",
                ],
                input=token,
                text=True,
                check=True,
                stdout=subprocess.DEVNULL,
            )

    def close(self):
        self.temporary.cleanup()

    def run(self, *args, cwd=None):
        return subprocess.check_output(
            ["oras", *args, "--registry-config", self.config], cwd=cwd, text=True
        ).strip()

    def resolve(self, reference="latest"):
        separator = "@" if reference.startswith("sha256:") else ":"
        return self.run("resolve", self.repository + separator + reference)

    def descriptor(self, digest):
        manifest = json.loads(
            self.run("manifest", "fetch", f"{self.repository}@{digest}")
        )
        layers = manifest.get("layers", [])
        if manifest.get("artifactType") != ARTIFACT_TYPE or len(layers) != 1:
            raise ValueError("not a single-archive snapshot artifact")
        layer = layers[0]
        if (
            layer.get("mediaType") != "application/gzip"
            or layer.get("annotations", {}).get("org.opencontainers.image.title")
            != "data.tar.gz"
        ):
            raise ValueError("unexpected snapshot layer")
        return layer

    def download(self, digest, destination):
        layer = self.descriptor(digest)
        self.run(
            "blob",
            "fetch",
            f"{self.repository}@{layer['digest']}",
            "--output",
            str(destination),
        )
        if (
            f"sha256:{checksum(destination)}" != layer["digest"]
            or Path(destination).stat().st_size != layer["size"]
        ):
            raise ValueError("OCI snapshot layer checksum/size mismatch")

    def push(self, tag, archive):
        archive = Path(archive).resolve()
        if archive.name != "data.tar.gz":
            raise ValueError("snapshot archive must be named data.tar.gz")
        source = os.environ.get("GITHUB_REPOSITORY", "igor-makarov/trans-nix-index")
        self.run(
            "push",
            f"{self.repository}:{tag}",
            "--artifact-type",
            ARTIFACT_TYPE,
            "--annotation",
            f"org.opencontainers.image.source=https://github.com/{source}",
            "--annotation",
            "org.opencontainers.image.description=Self-contained nixpkgs index and crawl state",
            "data.tar.gz:application/gzip",
            cwd=archive.parent,
        )
        digest = self.resolve(tag)
        if self.descriptor(digest)["digest"] != f"sha256:{checksum(archive)}":
            raise ValueError("published artifact does not match local snapshot")
        return digest

    def tag_latest(self, digest):
        self.run("tag", f"{self.repository}@{digest}", "latest")
