#!/usr/bin/env python3
"""Run an evaluator with periodic progress, keeping logs out of its data output."""
import json
from pathlib import Path
import subprocess
import sys
import time

command = sys.argv[1:]
start = time.monotonic()
with open("jobs.jsonl", "w") as jobs, open("evaluation.log", "w") as log:
    process = subprocess.Popen(command, stdout=jobs, stderr=log)
    try:
        while True:
            try:
                status = process.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                count, last = 0, None
                with open("jobs.jsonl") as stream:
                    for line in stream:
                        try:
                            last = json.loads(line).get("attr")
                            count += 1
                        except json.JSONDecodeError:
                            break
                print(
                    f"evaluation: {count} attributes, last={last}, elapsed={time.monotonic()-start:.0f}s",
                    flush=True,
                )
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
if status:
    print(
        "\n".join(Path("evaluation.log").read_text().splitlines()[-60:]),
        file=sys.stderr,
    )
raise SystemExit(status)
