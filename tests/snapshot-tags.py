#!/usr/bin/env python3
import io
import json
from pathlib import Path
import runpy
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import urllib.error

sys.path.insert(0, sys.argv[1])
from snapshot_tags import snapshot_tag, matches_run

stamp = datetime(2026, 9, 7, 8, 30, tzinfo=timezone(timedelta(hours=2)))
tag = snapshot_tag(stamp, "123", "2")
assert tag == "2026-09-07T06-30-00Z-run-123-2"
for valid in [tag, "data-123-2", "data-20260907-123-2"]:
    assert matches_run(valid, "123", "2")
for invalid in ["latest", tag + "0", tag + "-extra", "prefix-123-2"]:
    assert not matches_run(invalid, "123", "2")
assert not matches_run(tag, "123", "1")
try:
    snapshot_tag(datetime(2026, 9, 7), "123", "1")
except ValueError:
    pass
else:
    raise AssertionError("naive timestamp accepted")

published = runpy.run_path(str(Path(sys.argv[1]) / "check-publication.py"))["published"]


def response(value, link=""):
    result = io.BytesIO(json.dumps(value).encode())
    result.headers = {"Link": link}
    return result


with patch(
    "urllib.request.urlopen",
    side_effect=[
        response({"token": "anonymous"}),
        response(
            {"tags": ["latest"]},
            '</v2/igor-makarov/trans-nix-index-data/tags/list?n=100&last=latest>; rel="next"',
        ),
        response({"tags": [tag]}),
    ],
) as requests:
    assert published("123", "2")
    assert requests.call_count == 3
with patch(
    "urllib.request.urlopen",
    side_effect=[response({"token": "anonymous"}), response({"tags": [tag]})],
):
    assert not published("123", "1")
with patch(
    "urllib.request.urlopen",
    side_effect=[
        response({"token": "anonymous"}),
        urllib.error.HTTPError("url", 403, "denied", {}, None),
    ],
):
    try:
        published("123", "2")
    except urllib.error.HTTPError:
        pass
    else:
        raise AssertionError("registry failure treated as no publication")
print(
    "UTC snapshot names, run/attempt matching, pagination, and fail-closed preflight: OK"
)
