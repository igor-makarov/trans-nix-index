#!/usr/bin/env python3
"""Python/JS path parity, containment, and end-to-end attribute sharding."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
from shard_paths import shard_key

cases = {
    "firefox": "pkgs/fi",
    "jetbrains.idea": "pkgs/jetbrains/id",
    "haskell.packages.ghc98.aeson": "pkgs/haskell/packages/ghc98/ae",
    "pkgsCross.aarch64-multiplatform.hello": "pkgs/pkgsCross/aarch64-multiplatform/he",
    "foo.bar.package": "pkgs/foo/bar/pa",
    "foo/bar.package": "pkgs/foo_bar/pa",
    "foo_bar.package": "pkgs/foo_bar/pa",
    "..x": "pkgs/_/_/x",
    "": "pkgs/_",
    "foo.": "pkgs/foo/_",
    "a.😀x": "pkgs/a/_x",
    "é.foo": "pkgs/_/fo",
    "İx": "pkgs/i_x",
}
for attr, expected in cases.items():
    assert shard_key(attr) == expected, (attr, shard_key(attr))
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    module = root / "shard-path.mjs"
    module.write_bytes(Path(sys.argv[2]).read_bytes())
    program = f"import {{ shardKey }} from {json.dumps(module.as_uri())}; console.log(JSON.stringify({json.dumps(list(cases))}.map(shardKey)));"
    actual = json.loads(
        subprocess.check_output(
            ["node", "--input-type=module", "-e", program], text=True
        )
    )
    assert actual == list(cases.values())
    source = root / "index.json"
    attrs = {attr: {"1": [0, 1]} for attr in cases}
    source.write_text(json.dumps({"revisionCount": 2, "attrs": attrs}))
    for kind in ["versions", "history"]:
        out = root / kind
        subprocess.run(
            [
                "python3",
                str(Path(sys.argv[1]) / "shard-by-attr.py"),
                str(source),
                str(out),
            ],
            check=True,
        )
        for attr, path in cases.items():
            shard = json.loads((out / f"{path}.json").read_text())
            assert shard["attrs"][attr] == attrs[attr]
            assert shard["revisionCount"] == 2
        assert {p.relative_to(out).as_posix() for p in out.rglob("*.json")} == {
            p + ".json" for p in cases.values()
        }
print(
    "hierarchical shard paths: Python/JS parity, arbitrary depth, safe names and grouping: OK"
)
