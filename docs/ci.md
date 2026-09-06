# CI and publication

No workflow commits or pushes source changes. All jobs use `ubuntu-24.04-arm`,
`actions/checkout@v7`, `jdx/mise-action@v4`, and the repository's Docker Nix wrapper.
The build-toolchain revision is deliberately pinned in source configuration.

- **ci:** formatting, extraction/merge/liveness tests, generated-data exclusion, site build, browser tests.
- **update-index:** hourly change detection against our latest snapshot. No changes means no evaluation, crawl, publication, or Pages build. Release-channel-only changes reuse existing index/store data; new revisions or stale store coverage trigger incremental work.
- **census:** weekly availability checks, publishing a complete snapshot with refreshed availability artifacts.
- **pages:** builds and tests one published snapshot, then deploys; runs after successful updates or site-source changes.

## Release layout

Each `data-<run-id>-<attempt>` release has one self-contained `data.tar.gz` asset.
Pages checks for that run's published release before starting a data-triggered build:

- Index JSON: versions, history, stats, revisions, and releases.
- `artifacts/`: all store-data files consumed by the site.
- `state/`: crawl graph, census observations, and incremental miss tracking.
- `manifest.json`: schema version and SHA-256 checksums of every payload file.

All working data and archive members are plain JSON/JSONL. Compression happens
only when creating the outer `data.tar.gz`; there are no nested compressed files.

No upstream assets or older releases are referenced. The latest successful release alone
is sufficient for an incremental update. Older complete releases are rollback points.
The initial archive is approximately 1 GB; GitHub's per-asset limit is 2 GiB.

Each release stays draft until every required upload succeeds. Only then is it published and marked latest.
Failed generation leaves the previous complete snapshot available. The next run starts from that snapshot, not the initial seed.
Updater and census share a concurrency group because they both modify crawl state.

## Enabling automation

First publish a coherent snapshot and successfully deploy Pages. Then set repository variables
`ENABLE_PAGES=true` and `ENABLE_SCHEDULES=true`. Manual dispatch works before those gates are enabled.
Configure GitHub Pages to deploy through GitHub Actions. Only release publishers need `contents: write`;
Pages additionally needs `pages: write` and `id-token: write`.
