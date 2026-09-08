#!/usr/bin/env python3
"""Partition actual revision derivation dependencies into extraction lanes."""
from pathlib import Path
import sys

from importlib.util import module_from_spec, spec_from_file_location

spec = spec_from_file_location(
    "prepare_merge", Path(__file__).with_name("prepare-merge.py")
)
nix = module_from_spec(spec)
spec.loader.exec_module(nix)


def lanes(recipes, dependencies):
    heavy, light = set(), set()
    for recipe in recipes.values():
        selected_heavy, selected_light = set(), set()
        for path in nix.dependencies(recipe):
            name = dependencies[path].get("env", {}).get("name", "")
            if name.startswith("outputs-"):
                selected_heavy.add(path)
            elif name.startswith("versions-"):
                selected_light.add(path)
        if not selected_heavy or len(selected_light) != 1:
            raise ValueError(
                "expected output evaluations and exactly one version extraction per revision"
            )
        heavy.update(selected_heavy)
        light.update(selected_light)
    return heavy, light


if __name__ == "__main__":
    root = Path(sys.argv[1])
    recipes = nix.show(sys.argv[2:])
    dependencies = nix.show({p for r in recipes.values() for p in nix.dependencies(r)})
    heavy, light = lanes(recipes, dependencies)
    for name, paths in (("heavy", heavy), ("light", light)):
        (root / name).write_text("".join(p + "^*\n" for p in sorted(paths)))
