# Deliberate build-toolchain pin; this is source configuration, not index data.
{
  system,
  self ? { },
  snapshot ? null,
}:
let
  source = builtins.fetchTree {
    type = "github";
    owner = "NixOS";
    repo = "nixpkgs";
    rev = "6713828a351efa628b025a1adf7f43cbf8597513";
    narHash = "sha256-Fd3OB8J9JhgliQwOKcqx4M672CInxi1I5VnwsaXeSQo=";
  };
in
import source.outPath {
  inherit system;
  overlays = [ (import ./overlay.nix { inherit self snapshot; }) ];
}
