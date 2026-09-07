"""Site shard paths: pkgs/<parent attributes>/<leaf prefix>, without .json.

Keep in sync with site/js/shard-path.js. Full attribute keys remain in JSON;
unsafe characters fold to underscores, so any filename collisions merely group
more attributes in the same shard rather than overwriting their entries.
"""

import re


def shard_key(attr):
    *parents, leaf = attr.split(".")
    directories = [re.sub(r"[^A-Za-z0-9_-]", "_", part) or "_" for part in parents]
    prefix = re.sub(r"[^a-z0-9]", "_", leaf[:2].lower()) or "_"
    return "/".join(["pkgs", *directories, prefix])
