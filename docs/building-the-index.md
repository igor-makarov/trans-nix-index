# Building the index

Install [mise](https://mise.jdx.dev/), review `mise.toml` and `mise.lock`, then
install the configured tools with `mise install`.

With mise activated in your shell, its PATH configuration makes `nix` resolve to
`scripts/nix`. All Nix commands run in disposable `nixos/nix:latest` Docker
containers. Without shell activation, use `mise exec -- nix …` instead.
Run these commands from the repository root:

```sh
nix build '.#checks-smoke' --no-link -L
# Requires _ci/pure/enriched-snapshot.tar.gz; see below.
nix develop --command bash scripts/ci/pages-pure
```

The wrapper shares persistent Nix store/cache volumes. On macOS it uses Colima;
CI uses Linux ARM and Docker directly. Keep the shared volumes for local tests;
there is no reset task.

For a local preview with Python 3 on the host:

```sh
SITE_ROOT="$PWD/_site" python3 tools/serve-site.py 8000
```

Open `http://127.0.0.1:8000` while the server is running.

## Pure pipeline site builds

Use `.github/workflows/pipeline-site.yml`, not the deleted legacy Pages workflow.
Pull the named GHCR `enriched-snapshot` artifact by digest into a fresh directory,
then copy its archive to `_ci/pure/enriched-snapshot.tar.gz`.
[The pipeline reference](pure-pipeline.md) gives exact local creation and pull commands.
Local pure enrichment produces the same archive.

[The pure Pages script](../scripts/ci/pages-pure) verifies and unpacks that archive
into `_ci/pure/pages-snapshot`, validates the data, builds the site with an explicit
snapshot path and NAR hash, copies the result into `_site`, and runs browser tests.
It does not deploy when run locally. Each run replaces the previous unpacked
`_ci/pure/pages-snapshot` directory automatically, preserving the archive and Nix cache.
Do not fetch a GHCR snapshot as a fallback for local verification.

To rerun just the browser tests:

```sh
nix develop --command bash -c 'SITE_ROOT="$PWD/_site" nix run ".#test-site"'
```

## Legacy OCI snapshot builds

The following describes the old publication path, not the supported local verification path.

[The resolver](../tools/resolve-data.py) resolves the GHCR `latest` tag once to an immutable OCI digest,
downloads the self-contained `data.tar.gz`, verifies its SHA-256 digest, and unpacks
the index, store-data artifacts, crawl state, and per-file checksum manifest.
[Validation](../tools/validate-data.py) checks that revision offsets and histories agree.
[The site build](../nix/site-build.nix) takes that directory and its NAR hash explicitly.
There is no mutable network lookup inside Nix evaluation and no historical extraction during a site build.
All artifacts are local files inside that snapshot; no upstream release downloads occur.

Pass `--tag <registry-tag>` or `--digest sha256:<digest>` to `scripts/ci/pages` to replay a snapshot.
Generated files stay under ignored `_ci/` and `_site/` directories.

## Browser shard layout

The site build splits versions, history, metadata, and reverse dependencies
under a conventional `pkgs/` root. Parent attribute names become directories;
the final name's first two characters select the shard:

```text
versions/pkgs/fi.json                         # firefox
versions/pkgs/jetbrains/id.json               # jetbrains.idea
versions/pkgs/foo/bar/pa.json                 # foo.bar.package (illustrative)
```

The same layout applies under `history/`, `meta/`, `revdeps/`, and the
`meta-<system>/` and `revdeps-<system>/` directories. JSON keys retain their full
dotted attribute names, without an added `pkgs.` prefix. Arbitrary directory
depth is supported, but this does not expand which package sets are indexed.
Unsafe filename characters fold to underscores; any collisions group attributes
in one shard without changing their distinct JSON keys.
Hash-prefix `identify/` shards and complete snapshot datasets are unchanged.

## Incremental generation

[The updater](../scripts/ci/update) restores the latest snapshot into `_ci/work`,
discovers new nixpkgs revisions, and verifies that existing revision offsets have not changed.
It evaluates only new revisions, in bounded attribute batches, then merges versions and history and regenerates stats.
Old per-revision extraction caches are not required.

History retains removed versions and gaps. Census records binary availability separately;
it does not delete historical package entries. Timeout results are unknown, not proof of disappearance.
Census regenerates availability artifacts and publishes a complete snapshot without evaluating nixpkgs.

## Recovery

For pure Pages builds, select a successful enriched snapshot digest and repeat
the site build above, or manually dispatch `pipeline-resume` starting at `site`.

For the legacy OCI pipeline only, restore any complete OCI snapshot of ours by passing `--tag <tag>` or
`--digest sha256:<digest>` to `scripts/ci/pages` or `scripts/ci/update`.
Updates from an older snapshot publish a new complete snapshot; they do not modify the old one.

For manual emergency reseeding from upstream's latest:

```sh
nix develop --command python3 tools/import-seed.py _ci/emergency-seed
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
