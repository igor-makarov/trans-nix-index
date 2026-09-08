#!/usr/bin/env python3
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("paths", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
manifest = {
    "revisions": [
        {"rev": "a" * 40, "name": "trial-a"},
        {"rev": "b" * 40, "name": "trial-b"},
    ]
}
a = {"a" * 40: "/nix/store/" + "a" * 32 + "-revision-trial-a.json"}
b = {"b" * 40: "/nix/store/" + "b" * 32 + "-revision-trial-b.json"}
assert m.collect(manifest, [b, a]) == a | b
for receipts in (
    [a],
    [a, a, b],
    [a, b, {"c" * 40: next(iter(a.values()))}],
    [a, {"b" * 40: "/tmp/file.json"}],
    [a, {"b" * 40: next(iter(a.values()))}],
):
    try:
        m.collect(manifest, receipts)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid receipts accepted")
print(
    "Revision receipts: exact coverage, duplicates, unknown revisions, unsafe/mismatched paths: OK"
)
