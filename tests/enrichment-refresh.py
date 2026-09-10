#!/usr/bin/env python3
"""Guard the pipeline's fresh-observation boundary, not the crawler's resume API."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
for name in ("enrich-pure", "enrich-shard"):
    script = (root / "scripts/ci" / name).read_text()
    reset = 'rm -rf "$MULTIVERSE_ROOT/index/.outpaths"'
    assert "PIPELINE_PREVIOUS" not in script
    assert "restore-outpaths-state" not in script
    assert "bash tools/update-outpaths.sh --full" in script
    assert script.index(reset) < script.index("bash tools/update-outpaths.sh --full")
    # Exercise the actual reset command against both old graph verdicts and
    # derived state; immutable evaluation inputs must survive.
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        state = work / "index/.outpaths"
        state.mkdir(parents=True)
        (state / "graph.jsonl").write_text("old successes and 404s\n")
        (state / "data").mkdir()
        (state / "data/misses.json").write_text("{}")
        evaluations = work / "index/.eval"
        evaluations.mkdir()
        subprocess.run(
            ["bash", "-eu", "-c", reset],
            env={**os.environ, "MULTIVERSE_ROOT": tmp},
            check=True,
        )
        assert not state.exists()
        assert evaluations.is_dir()

workflow = (root / ".github/workflows/pipeline-enrich.yml").read_text()
assert "pull-previous" not in workflow
assert "PREVIOUS" not in workflow
assert "pipeline-artifact.py check enriched-snapshot" in workflow
assert "if: needs.plan.outputs.run == 'true'" in workflow
print(
    "Enrichment: fresh state on execution, immutable inputs retained, stage skip preserved: OK"
)
