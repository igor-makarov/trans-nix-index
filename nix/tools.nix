# Runtime tools for scripts invoked via mise run nix -- develop --command ...
{ pkgs }:
{
  deps = with pkgs; [
    bash
    python3
    nix-eval-jobs
    gitMinimal
    gnutar
    gnugrep
    coreutils
    curl
    gzip
    gh
    cachix
  ];
}
