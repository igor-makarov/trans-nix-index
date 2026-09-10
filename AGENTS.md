## Verification

Run from the repository root; `nix` uses the Docker wrapper at `scripts/nix`.
Quote flake targets containing `#` so sandbox command matching works correctly.

```sh
# Check formatting.
nix fmt -- --ci

# Run data pipeline and tooling tests.
nix build '.#checks-smoke' --no-link -L

# Build and browser-test the pure pipeline's enriched snapshot.
# Requires _ci/pure/enriched-snapshot.tar.gz from a successful pure-index enrichment.
nix develop --command bash scripts/ci/pages-pure

# Optionally rerun browser tests against the built site.
nix develop --command bash -c 'SITE_ROOT="$PWD/_site" nix run ".#test-site"'
```

Use `.github/workflows/pipeline-site.yml` as the reference. Pull the named GHCR
`enriched-snapshot` artifact by immutable digest and place its
`enriched-snapshot.tar.gz` under `_ci/pure/`, or produce it locally through
pure enrichment (see `docs/pure-pipeline.md`). Do not use the legacy GHCR-backed
`scripts/ci/pages` for verification. Pipeline orchestration is manual-only;
`pipeline-resume` can rebuild/test an existing snapshot without discovery or enrichment.

## Guidelines

### Temp Roots

Use the real repository workspace and normal persistent Nix store for local
pipeline tests. Do not create alternate test roots, copied workspaces, or
symlinked repository replicas. To simulate missing paths, pre-delete only the
specific test inputs or outputs needed for that scenario.
Do not use broad garbage collection or temporary Nix stores.
