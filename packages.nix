{
  system ? builtins.currentSystem,
  self ? { },
}:
let
  pkgs = import ./nix/pkgs.nix { inherit self system; };
  checks = import ./nix/checks.nix { inherit pkgs system; };
in
rec {
  checks-smoke = pkgs.linkFarm "site-data-checks" (
    pkgs.lib.mapAttrsToList (name: path: { inherit name path; }) checks
  );
  default = checks-smoke;
}
