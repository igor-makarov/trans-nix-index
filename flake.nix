{
  description = "Historical nixpkgs website and incremental release-data pipeline";
  # nix develop resolves its interactive Bash from this input, not mkShell attrs.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/6713828a351efa628b025a1adf7f43cbf8597513";
  outputs =
    { self, ... }:
    let
      systems = [
        "aarch64-linux"
        "x86_64-linux"
      ];
      eachSystem =
        f:
        builtins.listToAttrs (
          map (system: {
            name = system;
            value = f system;
          }) systems
        );
      pkgsFor = system: import ./nix/pkgs.nix { inherit self system; };
    in
    {
      packages = eachSystem (system: import ./packages.nix { inherit self system; });
      checks = eachSystem (
        system:
        import ./nix/checks.nix {
          pkgs = pkgsFor system;
          inherit system;
        }
      );
      formatter = eachSystem (system: (pkgsFor system).multiverse-formatter);
      devShells = eachSystem (system: import ./nix/dev-shells.nix { pkgs = pkgsFor system; });
      apps = eachSystem (system: {
        test-site = {
          type = "app";
          program = "${(pkgsFor system).multiverse-site-tests}/bin/test-site";
          meta.description = "Run browser tests against SITE_ROOT";
        };
      });
    };
}
