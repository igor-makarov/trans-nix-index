# nixpkgs-multiverse website

Browse historical nixpkgs package versions, their revisions, and binary-cache availability.
This repository ships the website and its data pipeline, not the `mvs` CLI or a Nix package-selection API.
Package-selection examples refer to the [upstream project](https://github.com/fzakaria/nixpkgs-multiverse).

1. [Building the index](./building-the-index.md)
2. [CI and publication](./ci.md)

Generated JSON and crawl state live in [GitHub releases](https://github.com/igor-makarov/trans-nix-index/releases), never in Git.
The initial snapshot was seeded from upstream commit `5fed5dc8b395225a076ceca9cb451854f9566af5`.
Subsequent updates extend our latest successfully published snapshot.
