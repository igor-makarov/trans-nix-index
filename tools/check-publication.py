#!/usr/bin/env python3
"""Cheap anonymous GHCR tag check for Pages after an updater run."""
import json
import re
import sys
import urllib.parse
import urllib.request

from snapshot_tags import matches_run


def published(run_id, attempt):
    repository = "igor-makarov/trans-nix-index-data"
    query = urllib.parse.urlencode(
        {"service": "ghcr.io", "scope": f"repository:{repository}:pull"}
    )
    with urllib.request.urlopen(
        f"https://ghcr.io/token?{query}", timeout=60
    ) as response:
        token = json.load(response)["token"]
    url = f"https://ghcr.io/v2/{repository}/tags/list?n=100"
    seen = set()
    while url:
        if url in seen:
            raise ValueError("registry pagination loop")
        seen.add(url)
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            tags = json.load(response).get("tags") or []
            if any(matches_run(tag, run_id, attempt) for tag in tags):
                return True
            link = response.headers.get("Link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        next_url = urllib.parse.urljoin(url, match[1]) if match else None
        if next_url and not next_url.startswith(
            f"https://ghcr.io/v2/{repository}/tags/list?"
        ):
            raise ValueError("unexpected registry pagination URL")
        url = next_url
    return False


if __name__ == "__main__":
    print("true" if published(*sys.argv[1:]) else "false")
