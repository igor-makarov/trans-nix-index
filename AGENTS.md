## Verification

Run from the repository root; all Nix commands use the mise wrapper.
Quote flake targets containing `#` so sandbox command matching works correctly.

```sh
# Check formatting.
mise run nix -- fmt -- --ci

# Run data pipeline and tooling tests.
mise run nix -- build '.#checks-smoke' --no-link -L

# Build the site from one published snapshot.
mise run nix -- develop --command bash scripts/ci/pages

# Run browser tests against the built site.
mise run nix -- develop --command bash -c 'SITE_ROOT="$PWD/_site" nix run ".#test-site"'
```

## Guidelines

### Temp Roots

Use the real repository workspace and normal persistent Nix store for local
pipeline tests. Do not create alternate test roots, copied workspaces, or
symlinked repository replicas. To simulate missing paths, pre-delete only the
specific test inputs or outputs needed for that scenario.
Do not use broad garbage collection or temporary Nix stores.
