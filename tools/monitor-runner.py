#!/usr/bin/env python3
"""Run a CI command and sample host utilization without changing its resources."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)


def sample():
    cpu = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
    mem = {
        line.split(":")[0]: int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
    }
    return cpu, mem


start = time.monotonic()
previous, _ = sample()
process = subprocess.Popen(sys.argv[2:])
with output.open("w") as stream:
    while True:
        try:
            code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            code = None
        cpu, mem = sample()
        delta = [a - b for a, b in zip(cpu, previous)]
        total = sum(delta)
        row = {
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "elapsedSeconds": round(time.monotonic() - start, 2),
            "cpus": os.cpu_count(),
            "cpuBusyPercent": (
                round(100 * (total - delta[3] - delta[4]) / total, 2) if total else 0
            ),
            "ioWaitPercent": round(100 * delta[4] / total, 2) if total else 0,
            "memoryUsedKiB": mem["MemTotal"] - mem["MemAvailable"],
            "memoryTotalKiB": mem["MemTotal"],
            "swapUsedKiB": mem["SwapTotal"] - mem["SwapFree"],
        }
        stream.write(json.dumps(row) + "\n")
        stream.flush()
        print("runner:", json.dumps(row), flush=True)
        previous = cpu
        if code is not None:
            break
sys.exit(code)
