# Standalone revision entry point: no discovery manifest or batch inputs.
{
  name,
  rev,
  tree ? null,
  system ? builtins.currentSystem,
}:
assert builtins.match "[0-9a-f]{40}" rev != null;
assert builtins.match "[A-Za-z0-9][A-Za-z0-9._+-]*" name != null;
let
  pkgs = import ./pkgs.nix { inherit system; };
  source =
    if tree != null then
      import ./fetch-git-tree.nix { inherit pkgs rev tree; }
    else
      builtins.fetchTree {
        type = "github";
        owner = "NixOS";
        repo = "nixpkgs";
        inherit rev;
      };
in
import ./revision.nix {
  inherit pkgs;
  revision = { inherit name rev; };
  source = source.outPath;
}
