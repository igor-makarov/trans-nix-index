# Resolve/download outside Nix once, then admit only the exact hashed snapshot.
{
  snapshot,
  snapshotHash,
  system ? builtins.currentSystem,
}:
let
  data = builtins.path {
    path = /. + snapshot;
    sha256 = snapshotHash;
    name = "site-data-snapshot";
  };
  pkgs = import ./pkgs.nix {
    inherit system;
    snapshot = data;
  };
in
pkgs.multiverse-site
