# Manual pipeline and reusable workflows

`pipeline.yml` is a **manual-only orchestrator**. There are no schedules,
`workflow_run` chains, or registry event triggers. It calls reusable workflows
with `workflow_call` and passes immutable OCI digests between them.
`pipeline-manual.yml` is a second manual entry point for starting at an existing
stage input. The old `update-index`, `census`, and `pages` workflows are removed.
Census sweeps are removed; enrichment retains historical observations without
claiming current cache availability.

## Components and outputs

```text
pipeline (manual; validates options and serializes the namespace)
  discovery   -> GHCR :revision-manifest
  index       -> GHCR :revision-index
  enrichment  -> GHCR :enriched-snapshot
  site/tests  -> GHCR :site
  deployment  -> GitHub Pages; GHCR :deployed-site acknowledgment
```

- **pipeline-discover.yml** fetches revision and release metadata, then obtains
  commit tree hashes without fetching trees/blobs. The artifact contains
  `manifest.json` and `matrix.json`. Release pointers are ordinary manifest data;
  they have no special update path. Discovery runs on every orchestrator invocation.
- **pipeline-index.yml** checks its input digest, partitions a shuffled manifest
  into bounded revision shards, builds only missing per-revision Cachix outputs,
  validates exact receipt coverage, fetches the JSONs in one fetch-only Nix call,
  and merges locally. The artifact contains `index/` and `evaluations/`.
- **pipeline-enrich.yml** checks its input digest and partitions attributes across
  shards. Whenever it runs, it starts with empty observation state, probes cache
  membership and crawls runtime references anew. Prior successes and 404s are
  not restored, including on local reruns. Merge validates
  shard coverage and calculates closures globally. Its OCI artifact contains
  `enriched-snapshot.tar.gz`, with index JSON, store artifacts, crawl state and
  an internal checksum manifest. HTTP observations are not Nix derivations.
- **pipeline-site.yml** checks its input digest, unpacks the enriched snapshot,
  builds `_site` and runs browser tests. Only a passing site is published as `:site`.
  This workflow has no Pages environment or deployment permission.
- **pipeline-deploy.yml** checks whether `:deployed-site` already points to the
  requested tested site digest. Only a changed site enters the protected
  `github-pages` environment, uploads the Pages artifact, and deploys. The
  acknowledgment moves only after successful deployment.

Shard handoffs within a workflow use short-lived Actions artifacts with attempt
suffixes. Partial job reruns select the latest successful receipt for each shard
from that run, retaining completed shards from earlier attempts; coverage and
input identities are still validated before merging. Durable stage outputs use GHCR. Per-revision immutable outputs stay in
Cachix, and their Nix store roots remain retained during local work/publication.
No aggregate is uploaded to Cachix. No workflow commits or pushes source changes.

## Named tags and avoiding repeated work

Repositories are `ghcr.io/<owner>/<repo>-pipeline-<scope>`. Within each repository,
use the simple tags above. No input-hash tags are needed. Temporary candidate tags
allow upload verification before advancing a stage's named tag.

Each artifact records `io.trans-nix-index.input`, the digest it consumed, and
`io.trans-nix-index.stage`. A stage compares the current input digest with the
input recorded in its last successful output. If equal, it returns that output's
digest and skips expensive jobs. Missing outputs or differing inputs require work.
Registry/authentication/network errors fail closed rather than triggering work.
Failed stages never acknowledge the input, so subsequent runs retry them even
when discovery is unchanged. Reused outputs still pass their digests downstream.

Archives have sorted members and fixed gzip/tar timestamps and ownership. OCI
creation metadata is fixed too, so rediscovering identical data yields the same
digest. Tags are resolved once; all subsequent downloads use digests and verify
archive SHA-256 and size. No package payloads are fetched during ordinary enrichment.

Code/configuration changes do not implicitly change this simple input comparison.
Use **force** when changing extraction, enrichment, site code or tests. Force reruns
stages while immutable revision outputs can still hit Cachix. Enrichment either
skips entirely for an already-consumed input, or performs a full observation
refresh. Force bypasses that skip; it does not change the refresh behavior.
Within an execution, requests are deduplicated. Failed-job reruns may retain
successful shard receipts from the same workflow run. Skipped snapshots retain
historical observations; even refreshed narinfos do not verify NAR payloads.

## Manual controls and isolation

`pipeline` accepts:

- `scope`: defaults to `trial`; use distinct trial names for different datasets.
- `limit`: positive number of latest revisions, or blank for all revisions.
- `max_shards`: 1–256, default 20. Actual matrices are capped by revision count.
- `force`: rerun stages even when inputs are unchanged (default false).
- `enrich`: enrichment plus site build/tests (default true).
- `deploy`: explicitly deploy a tested site (default false).

`production` scope requires main and an unlimited manifest. Deployment additionally
requires production scope and enrichment. Branch/limited trials cannot overwrite
production tags. Both manual entry points share a namespace-level concurrency
lock across the whole pipeline; child workflows must not acquire the same lock.
Do not reuse a trial scope concurrently for unrelated datasets.

`pipeline-manual` takes `scope`, `start` (index/enrich/site/deploy), `force`,
`max_shards`, and `deploy`. It resolves the appropriate named input tag and calls
that stage plus subsequent stages, without discovery. For example, a site-only
retry consumes `:enriched-snapshot`, without reevaluation or enrichment. Deployment
is still opt-in and restricted to main/production. Standalone deployment requires
`start=deploy` and `deploy=true`.

The package must be readable by consumers; publishers need `packages: write`.
`CACHIX_AUTH_TOKEN` is forwarded only to revision builds. Credentials stay in
short-lived registry configuration files, never in archives. Public packages
should be made public through GHCR package settings after initial publication.

## Local creation and verification

Run from the repository root using `scripts/nix` on PATH. This uses the existing
persistent Docker Nix store; do not copy the checkout or create alternate stores.
The following creates a three-revision snapshot locally using cached revision
outputs where available. Discovery and merge destinations must not already exist.
Enrichment can still involve many thousands of live cache requests.

```sh
nix develop --command env PIPELINE_LIMIT=3 bash scripts/ci/discover-pure
nix develop --command env PIPELINE_SHARD=0 PIPELINE_PUBLISH=false \
  python3 tools/revision-shards.py build _ci/pure/inputs/matrix.json --shards 1
nix develop --command bash scripts/ci/merge-pure
nix develop --command env PIPELINE_RESULT=/workspace/_ci/pure/merged-revisions \
  bash scripts/ci/enrich-pure
nix develop --command bash scripts/ci/pages-pure
```

`pages-pure` replaces its unpacked input on reruns, builds and browser-tests the
snapshot without deploying. To reuse a GHCR snapshot locally, pass the repository
and a resolved immutable digest:

```sh
nix develop --command python3 tools/pipeline-artifact.py pull enriched-snapshot \
  --repository ghcr.io/OWNER/REPO-pipeline-trial \
  --digest sha256:DIGEST --path _ci/pure/snapshot-input
cp _ci/pure/snapshot-input/enriched-snapshot.tar.gz _ci/pure/
nix develop --command bash scripts/ci/pages-pure
```

The download destination must not exist. Browser tests derive row/chart expectations
from the snapshot; the pagination-state test skips snapshots with no second page.
A failing browser suite is never published as a tested site.

## Future automation

No automation is enabled by this change. Later an hourly orchestrator schedule
can run discovery; named artifact input comparisons will gate downstream work.
There is no need for registry-triggered workflow loops or special release handling.
