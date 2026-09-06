#!/usr/bin/env python3
"""Extract in bounded batches so one revision does not exhaust a small VM."""
import json
import subprocess
import sys
from pathlib import Path

extractor, nested_sets, source, system, output = sys.argv[1:]
command = [
    "nix-instantiate",
    "--eval",
    "--strict",
    "--json",
    "--readonly-mode",
    "--option",
    "build-users-group",
    "",
    "--argstr",
    "system",
    system,
    "--argstr",
    "revPath",
    source,
    extractor,
]


def evaluate(args):
    result = subprocess.run(command + args, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


batch = Path(output).resolve().with_suffix(".attrs.json")
try:
    names = evaluate(["--arg", "namesOnly", "true"])
    versions = {}
    for start in range(0, len(names), 250):
        batch.write_text(json.dumps(names[start : start + 250]))
        versions.update(
            evaluate(
                [
                    "--arg",
                    "attrs",
                    f"builtins.fromJSON (builtins.readFile {json.dumps(str(batch))})",
                    "--arg",
                    "nestedSets",
                    "[]",
                ]
            )
        )
    # Nested sets are deliberately a short allow-list, evaluated separately.
    versions.update(
        evaluate(
            [
                "--arg",
                "attrs",
                "[]",
                "--arg",
                "nestedSets",
                f"import {nested_sets}",
            ]
        )
    )
    Path(output).write_text(json.dumps(versions, sort_keys=True) + "\n")
    print(f"extracted {len(versions)} attributes", flush=True)
except subprocess.CalledProcessError as error:
    print(error.stderr, file=sys.stderr)
    raise SystemExit(f"Nix extraction failed (exit {error.returncode})") from error
finally:
    batch.unlink(missing_ok=True)
