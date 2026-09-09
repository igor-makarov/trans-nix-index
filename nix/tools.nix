# Runtime tools for scripts invoked via mise run nix -- develop --command ...
{ pkgs }:
{
  deps = with pkgs; [
    bash
    (python3.withPackages (p: [
      p.httpx
      p.h2
    ]))
    nix-eval-jobs
    gitMinimal
    gnutar
    gnugrep
    coreutils
    curl
    gzip
    gh
    oras
    cachix
  ];
}
