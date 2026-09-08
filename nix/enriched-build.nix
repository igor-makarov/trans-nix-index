# Pure packaging of an already collected external observation dataset.
{
  pure,
  observations,
  system ? builtins.currentSystem,
}:
let
  pkgs = import ./pkgs.nix { inherit system; };
  base = /. + pure;
  data = /. + observations;
  snapshot = pkgs.runCommand "enriched-index-snapshot" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    mkdir "$out"
    cp -r ${data}/. "$out/"
    chmod -R u+w "$out"
    python3 ${../tools/snapshot.py} "$out" snapshot.tar.gz
    python3 ${../tools/validate-data.py} "$out"
  '';
in
pkgs.linkFarm "enriched-index-pipeline" [
  {
    name = "index";
    path = base + "/index";
  }
  {
    name = "evaluations";
    path = base + "/evaluations";
  }
  {
    name = "snapshot";
    path = snapshot;
  }
]
