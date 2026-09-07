#!/usr/bin/env python3
"""Publish one snapshot, then advance latest only after digest verification."""
import sys
from oci import Registry

registry = Registry()
try:
    archive, tag = sys.argv[1:]
    digest = registry.push(tag, archive)
    registry.tag_latest(digest)
    print(f"Published {registry.repository}:{tag} ({digest})", flush=True)
finally:
    registry.close()
