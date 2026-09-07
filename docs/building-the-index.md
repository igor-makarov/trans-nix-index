# Building the index

Install [mise](https://mise.jdx.dev/), review `mise.toml` and `mise.lock`, then
install the configured tools with `mise install`.

All Nix commands run in disposable `nixos/nix:latest` Docker containers:

```sh
mise run nix -- build '.#checks-smoke' --no-link -L
mise run nix -- develop --command bash scripts/ci/pages
mise run nix -- develop --command bash -c 'SITE_ROOT="$PWD/_site" nix run ".#test-site"'
```

The wrapper shares persistent Nix store/cache volumes. On macOS it uses Colima;
CI uses Linux ARM and Docker directly. `mise run nix:reset` **deletes both shared
volumes**, discarding cached downloads and builds.

For a local preview with Python 3 on the host:

```sh
SITE_ROOT="$PWD/_site" python3 tools/serve-site.py 8000
```

Open `http://127.0.0.1:8000` while the server is running.

## Snapshot-based builds

[The resolver](../tools/resolve-data.py) resolves the GHCR `latest` tag once to an immutable OCI digest,
downloads the self-contained `data.tar.gz`, verifies its SHA-256 digest, and unpacks
the index, store-data artifacts, crawl state, and per-file checksum manifest.
[Validation](../tools/validate-data.py) checks that revision offsets and histories agree.
[The site build](../nix/site-build.nix) takes that directory and its NAR hash explicitly.
There is no mutable network lookup inside Nix evaluation and no historical extraction during a site build.
All artifacts are local files inside that snapshot; no upstream release downloads occur.

Pass `--tag <registry-tag>` or `--digest sha256:<digest>` to `scripts/ci/pages` to replay a snapshot.
Generated files stay under ignored `_ci/` and `_site/` directories.

## Incremental generation

[The updater](../scripts/ci/update) restores the latest snapshot into `_ci/work`,
discovers new nixpkgs revisions, and verifies that existing revision offsets have not changed.
It evaluates only new revisions, in bounded attribute batches, then merges versions and history and regenerates stats.
Old per-revision extraction caches are not required.

History retains removed versions and gaps. Census records binary availability separately;
it does not delete historical package entries. Timeout results are unknown, not proof of disappearance.
Census regenerates availability artifacts and publishes a complete snapshot without evaluating nixpkgs.

## Recovery

Restore any complete OCI snapshot of ours by passing `--tag <tag>` or
`--digest sha256:<digest>` to `scripts/ci/pages` or `scripts/ci/update`.
Updates from an older snapshot publish a new complete snapshot; they do not modify the old one.

For manual emergency reseeding from upstream's latest:

```sh
mise run nix -- develop --command python3 tools/import-seed.py _ci/emergency-seed
```

[The seed importer](../tools/import-seed.py) resolves upstream's main commit once,
imports its coherent JSON and hash-pinned artifacts, and verifies the crawl graph's
release-asset digest. It writes a self-contained snapshot directory and
`_ci/emergency-seed.tar.gz`. The destination must not already exist.
Review and test it before publishing. Rename the archive to `data.tar.gz`, then use
[the OCI publisher](../tools/publish-oci.py) with that path and a new registry tag.
It verifies the uploaded descriptor before advancing `latest`. Publishing requires
GHCR credentials with package-write access. No workflow automatically reseeds.

Rebuilding all history from original nixpkgs/NixOS sources is theoretically possible,
but a supported from-scratch bootstrap is deliberately out of scope.
