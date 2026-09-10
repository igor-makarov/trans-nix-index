#!/usr/bin/env python3
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

spec = importlib.util.spec_from_file_location("trees", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    src = root / "upstream"

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(src), *args], text=True
        ).strip()

    src.mkdir()
    git("init", "-q")
    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("config", "uploadpack.allowFilter", "true")
    (src / "file").write_text("content\n")
    git("add", ".")
    git("commit", "-qm", "first")
    rev = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    repo = root / "commits"
    assert m.discover([rev, rev], repo, src.as_uri()) == {rev: tree}
    objects = subprocess.check_output(
        [
            "git",
            "--git-dir",
            str(repo),
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objecttype)",
        ],
        text=True,
    )
    assert objects.splitlines() == ["commit"], objects
    assert not (repo / "FETCH_HEAD").exists()
    for bad in ([], ["HEAD"], ["a" * 39]):
        try:
            m.discover(bad, root / "bad")
        except ValueError:
            pass
        else:
            raise AssertionError("bad commit accepted")
print("Commit-only tree discovery: hashes, no trees/blobs/refs, validation: OK")
