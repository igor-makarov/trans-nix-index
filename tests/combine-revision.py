#!/usr/bin/env python3
"""Redact references in errors without changing actual package output paths."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    digest = "0123456789abcdfghijklmnpqrsvwxyz"
    path = f"/nix/store/{digest}-source"
    error = f"error at {path}/default.nix:1; also {digest}-source/file.nix"
    (root / "versions").write_text(json.dumps({"pkg": "1"}))
    (root / "outputs.json").write_text(
        json.dumps(
            {
                "rev": "revision",
                "system": "system",
                "attrCount": 1,
                "errorCount": 1,
                "attrs": {"pkg": {"name": "pkg-1", "outputs": {"out": path}}},
            }
        )
    )
    (root / "errors.json").write_text(json.dumps({"broken": error}))
    subprocess.run(
        [
            sys.executable,
            sys.argv[1],
            str(root / "versions"),
            json.dumps({"system": directory}),
            "revision",
            str(root / "result"),
        ],
        check=True,
    )
    result = json.loads((root / "result").read_text())
    assert result["attrs"]["broken"]["systems"]["system"]["error"] == error.replace(
        digest, "e" * 32
    )
    assert result["attrs"]["pkg"]["systems"]["system"]["outputs"]["out"] == path
    assert json.loads((root / "errors.json").read_text())["broken"] == error
print("Error hashes redacted, output paths and raw extraction errors unchanged: OK")
