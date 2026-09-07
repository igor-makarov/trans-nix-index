#!/usr/bin/env python3
"""Cheap anonymous GHCR existence check for Pages after an updater run."""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def published(tag):
    repository = "igor-makarov/trans-nix-index-data"
    query = urllib.parse.urlencode(
        {"service": "ghcr.io", "scope": f"repository:{repository}:pull"}
    )
    with urllib.request.urlopen(
        f"https://ghcr.io/token?{query}", timeout=60
    ) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{repository}/manifests/{urllib.parse.quote(tag, safe='')}",
        method="HEAD",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.manifest.v1+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60):
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


if __name__ == "__main__":
    print("true" if published(sys.argv[1]) else "false")
