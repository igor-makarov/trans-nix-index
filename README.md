# trans-nix-index

Historical nixpkgs package versions and binary-cache availability, as a website
and downloadable data. Adapted from
[nixpkgs-multiverse](https://github.com/fzakaria/nixpkgs-multiverse), with a focus
on independently published, self-contained snapshots rather than generated data
in Git.

[Browse the website](https://igor-makarov.github.io/trans-nix-index/) ·
[Browse snapshots](https://github.com/users/igor-makarov/packages/container/package/trans-nix-index-data)

## Get the data

Download the latest public snapshot with [ORAS](https://oras.land/):

```sh
oras pull ghcr.io/igor-makarov/trans-nix-index-data:latest -o download
mkdir -p data
tar -xzf download/data.tar.gz -C data
```

Each snapshot includes package versions, history, revision metadata, store-path
and availability data, crawl state, and a checksum manifest. No older snapshot
or upstream data download is needed. The archive is roughly 1 GB.

For an immutable snapshot, use `ghcr.io/igor-makarov/trans-nix-index-data@sha256:<digest>`
instead of `:latest`. These are OCI data artifacts, not runnable container images;
no Git tags or GitHub Releases are used.

See [building and recovery](docs/building-the-index.md) and
[publication](docs/ci.md) for implementation details.

[MIT](LICENSE). Based on work by Farid Zakaria and contributors.
