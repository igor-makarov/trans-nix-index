#!/usr/bin/env python3
"""Manual emergency reseeding from upstream's latest commit; never a fallback."""
import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from snapshot import INDEX_FILES, checksum, pack


def api(url):
    headers = {"User-Agent": "trans-nix-index"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=60
    ) as response:
        return json.load(response)


def download(url, path):
    with urllib.request.urlopen(url, timeout=180) as response, path.open(
        "wb"
    ) as output:
        shutil.copyfileobj(response, output)


def expand(path):
    """Upstream import is the only place individual gzip files are accepted."""
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream, path.with_suffix("").open("wb") as output:
            shutil.copyfileobj(stream, output)
        path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destination", type=Path, help="New snapshot directory; must not exist"
    )
    parser.add_argument("--upstream", default="fzakaria/nixpkgs-multiverse")
    args = parser.parse_args()
    if args.destination.exists():
        parser.error("destination already exists; choose a new directory")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    base = f"https://api.github.com/repos/{args.upstream}"
    commit = api(f"{base}/commits/main")["sha"]
    raw = f"https://raw.githubusercontent.com/{args.upstream}/{commit}"
    # Resolve the mutable graph once as well; a replacement during download
    # fails its digest check rather than silently mixing observations.
    graph = next(
        a
        for a in api(f"{base}/releases/tags/data-rolling")["assets"]
        if a["name"] == "graph.jsonl.gz"
    )
    if not (graph.get("digest") or "").startswith("sha256:"):
        raise ValueError("upstream graph has no SHA-256 digest")
    with tempfile.TemporaryDirectory(dir=args.destination.parent) as temporary:
        root = Path(temporary) / "snapshot"
        (root / "artifacts").mkdir(parents=True)
        (root / "state").mkdir()
        for name in sorted(INDEX_FILES):
            prefix = (
                "index/"
                if name in {"versions.json", "history.json", "stats.json"}
                else ""
            )
            download(f"{raw}/{prefix}{name}", root / name)
        pins_path = Path(temporary) / "pins.json"
        download(f"{raw}/data-pins.json", pins_path)
        pins = json.loads(pins_path.read_text())

        def artifact(item):
            name, pin = item
            if Path(name).name != name:
                raise ValueError(f"unsafe artifact name: {name}")
            path = root / "artifacts" / name
            download(f"{pin.get('baseUrl', pins['baseUrl'])}/{pin['tag']}/{name}", path)
            actual = subprocess.check_output(
                ["nix", "hash", "path", "--sri", str(path)], text=True
            ).strip()
            if actual != pin["narHash"]:
                raise ValueError(f"artifact checksum mismatch: {name}")
            expand(path)
            print(f"Verified {name}", flush=True)

        with ThreadPoolExecutor(max_workers=6) as executor:
            list(executor.map(artifact, pins["files"].items()))
        graph_path = root / "state/graph.jsonl.gz"
        download(graph["browser_download_url"], graph_path)
        if f"sha256:{checksum(graph_path)}" != graph["digest"]:
            raise ValueError("crawl graph changed; retry the manual reseed")
        expand(graph_path)
        (root / "state/seed-origin.json").write_text(
            json.dumps(
                {
                    "upstream": args.upstream,
                    "commit": commit,
                    "graphDigest": graph["digest"],
                }
            )
            + "\n"
        )
        archive = Path(temporary) / "data.tar.gz"
        pack(root, archive)
        subprocess.run(
            ["python3", str(Path(__file__).with_name("validate-data.py")), str(root)],
            check=True,
        )
        # Nothing is published automatically. Inspect/test before releasing.
        root.rename(args.destination)
        archive.rename(args.destination.with_suffix(".tar.gz"))
    print(f"Seeded {args.destination} from {args.upstream}@{commit}")


if __name__ == "__main__":
    main()
