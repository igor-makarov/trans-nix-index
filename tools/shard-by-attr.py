#!/usr/bin/env python3
"""Split an {"attrs": {...}} index file into per-attribute-prefix shards.

Sharded under pkgs/<parent attributes>/ by the first two characters of the
final attribute name, so a package page
fetches only the shard holding the one attribute it is about. history.json and
versions.json have the same shape and both go through here.

A timeline needs the history of exactly one attribute, and a version table
needs the versions of exactly one attribute; serving either whole file to
render one package would cost more than every other request on the page
combined. Two characters puts the median history shard at 2 KB and the median
versions shard at 1.4 KB.

Build artifacts rather than snapshot members: the snapshot keeps the complete
files, and the deploy gets the pieces. Splitting does not alter the snapshot.

    shard-by-attr.py <src.json> <dest-dir>
"""
import json
import os
import sys

from shard_paths import shard_key

src, dest = sys.argv[1:3]
data = json.load(open(src))
os.makedirs(dest, exist_ok=True)

# Everything that is not the per-attribute map is small and gets copied into
# every shard, so a shard stands on its own.
common = {k: v for k, v in data.items() if k != "attrs"}

buckets = {}
for attr, vers in data["attrs"].items():
    key = shard_key(attr)
    buckets.setdefault(key, {})[attr] = vers

for key, attrs in buckets.items():
    os.makedirs(os.path.dirname(os.path.join(dest, key + ".json")), exist_ok=True)
    json.dump(
        {**common, "attrs": attrs},
        open(os.path.join(dest, key + ".json"), "w"),
        separators=(",", ":"),
        sort_keys=True,
    )
print(f"sharded {len(data['attrs'])} attrs into {len(buckets)} files")
