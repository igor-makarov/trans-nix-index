#!/usr/bin/env python3
import importlib.util
import sys
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch

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
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    paths = a | b
    with patch.object(m.subprocess, "run") as run, patch.object(
        Path, "read_text", side_effect=AssertionError("fetch must not parse JSONs")
    ):
        m.fetch(paths, root)
        assert run.call_count == 1
        command = run.call_args.args[0]
        assert command[:4] == ["nix-store", "--realise", *sorted(paths.values())]
        assert command[command.index("--max-jobs") + 1] == "0"
        assert command[command.index("--builders") + 1] == ""
        assert "--add-root" in command and "--indirect" in command
    with patch.object(
        m.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "nix-store")
    ), patch.object(Path, "read_text") as read_mock:
        try:
            m.fetch(paths, root)
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError("fetch failure ignored")
        read_mock.assert_not_called()
print(
    "Revision receipts: exact coverage, batched fetch-only realisation, no duplicate JSON parsing and fetch failures: OK"
)
