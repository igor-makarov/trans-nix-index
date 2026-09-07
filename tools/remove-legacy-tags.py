#!/usr/bin/env python3
"""One-time removal of legacy aliases without deleting snapshot versions."""
import json
import os
import re
import subprocess
import time

from oci import Registry
from snapshot_tags import matches_run


def api(path, method="GET"):
    result = subprocess.check_output(["gh", "api", "--method", method, path], text=True)
    return json.loads(result) if result.strip() else None


registry = Registry()
try:
    tags = registry.run("repo", "tags", registry.repository).splitlines()
    old = {
        tag: registry.resolve(tag)
        for tag in tags
        if re.fullmatch(r"data-(?:\d{8}-)?\d+-\d+", tag)
    }
    protected = {tag: registry.resolve(tag) for tag in tags if tag not in old}
    assert "latest" in protected
    for tag, digest in old.items():
        run, attempt = tag.rsplit("-", 2)[-2:]
        if not any(
            matches_run(alias, run, attempt) and value == digest
            for alias, value in protected.items()
        ):
            raise ValueError(f"no verified timestamp alias for {tag}")
    if old:
        temporary = f"cleanup-legacy-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
        registry.run(
            "push",
            f"{registry.repository}:{temporary}",
            "--artifact-type",
            "application/vnd.trans-nix-index.tag-cleanup.v1",
            "--annotation",
            f"cleanup-run={temporary}",
        )
        disposable = registry.resolve(temporary)
        if disposable in set(protected.values()) | set(old.values()):
            raise ValueError("refusing to delete a real snapshot digest")
        endpoint = "users/igor-makarov/packages/container/trans-nix-index-data/versions"
        try:
            for tag in old:
                registry.run("tag", f"{registry.repository}@{disposable}", tag)
            version = None
            for retry in range(30):
                page = 1
                while True:
                    versions = api(f"{endpoint}?per_page=100&page={page}")
                    if not versions:
                        break
                    version = next(
                        (v for v in versions if v["name"] == disposable), None
                    )
                    if version:
                        break
                    page += 1
                if version and set(version["metadata"]["container"]["tags"]) == set(
                    old
                ) | {temporary}:
                    break
                time.sleep(2)
            else:
                raise ValueError("disposable version metadata did not converge")
            for tag, digest in protected.items():
                if registry.resolve(tag) != digest:
                    raise ValueError(f"protected tag changed: {tag}")
            api(f"{endpoint}/{version['id']}", "DELETE")
        except Exception:
            # Restore aliases if cleanup fails; never leave old names pointing
            # at an empty artifact after a permission or transport failure.
            for tag, digest in old.items():
                registry.run("tag", f"{registry.repository}@{digest}", tag)
            raise
        for retry in range(30):
            remaining = set(
                registry.run("repo", "tags", registry.repository).splitlines()
            )
            if not remaining.intersection(set(old) | {temporary}):
                break
            time.sleep(2)
        else:
            raise ValueError("legacy aliases still listed after deletion")
    for tag, digest in protected.items():
        if registry.resolve(tag) != digest:
            raise ValueError(f"protected tag changed: {tag}")
        print(f"Preserved {tag} ({digest})", flush=True)
    print(f"Removed {len(old)} legacy aliases", flush=True)
finally:
    registry.close()
