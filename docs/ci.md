# CI and publication

No workflow commits, pushes, or creates Git tags or GitHub Releases. All Nix jobs
use `ubuntu-24.04-arm`, `actions/checkout@v7`, `jdx/mise-action@v4`, and the
repository's Docker Nix wrapper. The build toolchain is pinned in source.

- **ci:** formatting, extraction/merge/liveness/OCI tests, generated-data exclusion, site build, browser tests.
- **update-index:** hourly change detection against our latest snapshot. No changes means no evaluation, crawl, publication, or Pages build. Release-channel-only changes reuse existing index/store data; new revisions or stale store coverage trigger incremental work.
- **census:** weekly availability checks, publishing a complete snapshot with refreshed availability artifacts.
- **pages:** builds and tests one published snapshot, then deploys after a successful publication or site-source change.

## Snapshot layout

Snapshots are public OCI artifacts in `ghcr.io/igor-makarov/trans-nix-index-data`.
Each `YYYY-MM-DDTHH-MM-SSZ-run-<run-id>-<attempt>` registry tag holds one
self-contained `data.tar.gz`. For example, `2026-09-07T06-30-00Z-run-34088947935-1`
records the UTC publication time, GitHub Actions run ID, and attempt number.
`latest` points to the newest successful publication. Existing snapshots use their
OCI creation timestamp (the GHCR migration time). Legacy `data-*` aliases have
been removed; the timestamp tags retain the same immutable digests.

Archive contents:

- Index JSON: versions, history, stats, revisions, and releases.
- `artifacts/`: all store-data files consumed by the site.
- `state/`: crawl graph, census observations, and incremental miss tracking.
- `manifest.json`: schema version and SHA-256 checksums of every payload file.

All working data and archive members are plain JSON/JSONL. Compression happens
only when creating the outer archive. No older snapshots or upstream assets are referenced.
The latest complete snapshot alone is sufficient for an incremental update.
Older snapshot tags are rollback points; manifest digests identify immutable contents.

ORAS uploads the archive blob before publishing its OCI manifest. The publisher
verifies the manifest's archive digest before advancing the `latest` registry tag.
Consumers resolve a tag once and then read only by digest, verifying the layer's
checksum and the archive's internal manifest. Pages checks registry tags for the
triggering run ID and attempt before starting a data-triggered build; this does
not require knowing the publication timestamp. Tag listing is paginated.
Updater and census share a concurrency group to serialize publications.

## Permissions and automation

Publishers use `GITHUB_TOKEN` with `packages: write` and `contents: read`.
The OCI source annotation associates the package with this repository. The GHCR
package must remain public for anonymous downloads and pull-request site builds.
Registry credentials are temporary and never included in the snapshot.

Automation is enabled by default. Set repository variables `DISABLE_PAGES=true`
or `DISABLE_SCHEDULES=true` to pause automatic deployment or scheduled data jobs.
Unset or `false` values leave automation enabled. Manual dispatch bypasses those gates.
GitHub Pages deploys through Actions and additionally needs `pages: write` and
`id-token: write`. Public Nix binary-cache downloads require no account or key.
