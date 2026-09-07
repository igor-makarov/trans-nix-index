#!/usr/bin/env python3
"""One-time naming migration; preserve all manifest digests and old aliases."""
from datetime import datetime
import json
import re

from oci import Registry
from snapshot_tags import snapshot_tag

registry = Registry()
try:
    latest = registry.resolve()
    for old in registry.run("repo", "tags", registry.repository).splitlines():
        match = re.fullmatch(r"data-(?:\d{8}-)?(\d+)-(\d+)", old)
        if not match:
            continue
        digest = registry.resolve(old)
        manifest = json.loads(
            registry.run("manifest", "fetch", f"{registry.repository}@{digest}")
        )
        created = datetime.fromisoformat(
            manifest["annotations"]["org.opencontainers.image.created"]
        )
        new = snapshot_tag(created, match[1], match[2])
        registry.run("tag", f"{registry.repository}@{digest}", new)
        if registry.resolve(new) != digest:
            raise ValueError("alias digest mismatch")
        print(f"{old} -> {new} ({digest})", flush=True)
    if registry.resolve() != latest:
        raise ValueError("latest unexpectedly changed")
finally:
    registry.close()
