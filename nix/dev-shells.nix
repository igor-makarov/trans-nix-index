{ pkgs }:
{
  default = pkgs.mkShellNoCC {
    packages = pkgs.multiverse-tools.deps;
    # Prevent nix develop from resolving its shell via the global registry.
    bashInteractive = pkgs.bashInteractive;
  };
}
