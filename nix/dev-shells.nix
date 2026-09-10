{ pkgs }:
{
  default = pkgs.mkShellNoCC {
    packages = pkgs.multiverse-tools.deps;
  };
}
