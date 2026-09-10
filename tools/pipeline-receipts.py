#!/usr/bin/env python3
"""Select the latest successful receipt per shard, including partial job reruns."""
import json
import os
import re
import sys
from urllib.request import Request, urlopen


def select(artifacts, prefix, count):
    selected = {}
    for artifact in artifacts:
        match = re.fullmatch(re.escape(prefix) + r"-(\d+)-(\d+)", artifact["name"])
        if not match:
            continue
        shard, attempt = map(int, match.groups())
        if not 0 <= shard < count:
            raise ValueError("unexpected shard receipt")
        previous = selected.get(shard)
        if previous is None or attempt > previous[0]:
            selected[shard] = (attempt, artifact)
        elif attempt == previous[0]:
            raise ValueError("duplicate shard receipt")
    if set(selected) != set(range(count)) or any(
        item[1].get("expired") for item in selected.values()
    ):
        raise ValueError("missing or expired shard receipts")
    return ",".join(str(selected[i][1]["id"]) for i in range(count))


def main():
    prefix = sys.argv[1]
    count = len(json.loads(os.environ["MATRIX"])["include"])
    if not 1 <= count <= 256:
        raise ValueError("invalid shard count")
    artifacts = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}/artifacts?per_page=100&page={page}"
        request = Request(
            url,
            headers={
                "Authorization": "Bearer " + os.environ["GH_TOKEN"],
                "Accept": "application/vnd.github+json",
            },
        )
        with urlopen(request, timeout=60) as response:
            batch = json.load(response)["artifacts"]
        artifacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    print("ids=" + select(artifacts, prefix, count))


if __name__ == "__main__":
    main()
