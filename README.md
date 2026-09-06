# trans-nix-index

Historical nixpkgs package versions and binary-cache availability, as a website
and downloadable data. Adapted from
[nixpkgs-multiverse](https://github.com/fzakaria/nixpkgs-multiverse), with a focus
on independently published, self-contained snapshots rather than generated data
in Git.

[Browse the website](https://igor-makarov.github.io/trans-nix-index/) ·
[Browse releases](https://github.com/igor-makarov/trans-nix-index/releases)

## Get the data

Download the [latest data.tar.gz](https://github.com/igor-makarov/trans-nix-index/releases/latest/download/data.tar.gz):

```sh
curl -fL -o data.tar.gz \
  https://github.com/igor-makarov/trans-nix-index/releases/latest/download/data.tar.gz
mkdir -p data
tar -xzf data.tar.gz -C data
```

Each complete snapshot includes package versions, history, revision metadata,
store-path and availability data, crawl state, and a checksum manifest.
No older release or upstream data download is needed. The archive is roughly 1 GB.
For a fixed snapshot, use a specific release tag instead of `latest`.

See [building and recovery](docs/building-the-index.md) and
[publication](docs/ci.md) for implementation details.

[MIT](LICENSE). Based on work by Farid Zakaria and contributors.
