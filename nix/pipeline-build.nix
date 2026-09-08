# Local/CI entry point: read the full manifest from the discovery artifact.
{
  inputs,
  system ? builtins.currentSystem,
}:
let
  bundle = /. + inputs;
  manifest = builtins.fromJSON (builtins.readFile (bundle + "/manifest.json"));
  pkgs = import ./pkgs.nix { inherit system; };
in
import ./pipeline.nix { inherit pkgs manifest; }
