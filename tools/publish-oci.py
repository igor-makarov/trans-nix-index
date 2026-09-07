#!/usr/bin/env python3
"""Publish one snapshot, then advance latest only after digest verification."""
import sys
import os
from datetime import datetime, timezone
from oci import Registry
from snapshot_tags import snapshot_tag

registry = Registry()
try:
    archive = sys.argv[1]
    tag = (
        sys.argv[2]
        if len(sys.argv) > 2
        else snapshot_tag(
            datetime.now(timezone.utc),
            os.environ.get("GITHUB_RUN_ID", "local"),
            os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        )
    )
    digest = registry.push(tag, archive)
    registry.tag_latest(digest)
    print(f"Published {registry.repository}:{tag} ({digest})", flush=True)
finally:
    registry.close()
