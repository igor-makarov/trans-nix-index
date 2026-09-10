#!/usr/bin/env python3
"""Exercise real ORAS manifests/digests using an OCI layout, without publishing."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "pipeline_artifact", Path(sys.argv[1]) / "pipeline-artifact.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Layout(m.PipelineRegistry):
    def __init__(self, repository):
        self.repository = str(repository)

    def run(self, *args, cwd=None):
        return subprocess.check_output(
            ["oras", *args, "--oci-layout"], cwd=cwd, text=True, stderr=subprocess.PIPE
        ).strip()


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / "source"
    source.mkdir()
    (source / "manifest.json").write_text('{"revisions": ["abc"]}')
    registry = Layout(root / "layout")
    # Bootstrap a layout; real empty GHCR repositories are covered by lookup tests.
    first = registry.publish("revision-manifest", source, "")
    second = registry.publish("revision-manifest", source, "")
    assert first == second, (first, second)
    assert registry.lookup("revision-manifest") == first
    assert registry.lookup("revision-index") is None
    registry.download_stage(first, "revision-manifest", root / "restored")
    assert (root / "restored/manifest.json").read_bytes() == (
        source / "manifest.json"
    ).read_bytes()
    output = registry.publish("revision-index", source, first)
    assert m.reusable(registry, "revision-index", first) == output
    (source / "manifest.json").write_text('{"revisions": ["abc", "def"]}')
    changed = registry.publish("revision-manifest", source, "")
    assert changed != first
    assert m.reusable(registry, "revision-index", changed) is None
    assert registry.manifest(output)["annotations"][m.INPUT] == first
print(
    "Real ORAS: deterministic manifests, missing tags, pinned pull, named-tag movement, upstream acknowledgment: OK"
)
