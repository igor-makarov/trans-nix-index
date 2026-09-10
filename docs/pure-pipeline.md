# Pure revision pipeline (manual rollout)

The new `pure-index` GitHub workflow is deliberately **manual-only**. It does
not replace the scheduled `update-index` and `census` workflows yet. Those are
kept running during validation; the new workflow never reads or writes GHCR.
Do not enable an automatic backfill or cut over production until the small
trial and enriched site have been reviewed.

## Functional boundaries and sharded jobs

One `pure-index` workflow contains the entire graph:

1. **discover** fetches S3/GitHub channel metadata, without prefetching source
   trees except for historical release commit metadata fallback. The manifest
   and revision plan are a GitHub run artifact. Optional `limit` selects that
   many recent revisions; blank/omitted means unlimited. It accepts any positive
   integer, without a rollout cap. This selects a complete dataset, not only
   cache misses.
2. **revisions** is a matrix of up to 256 shards, not one job per revision.
   Discovery persists a shuffled revision plan, distributed round-robin for
   balanced random shard assignment. Shards shuffle their queues and extraction
   lane targets independently; Nix still controls dependency scheduling.
   Each shard submits all cache-missing
   revisions to separate extraction lanes: three output evaluations and one
   version extraction concurrently, then up to four cheap combiners. GitHub manages runner capacity.
   The `max_shards` workflow input defaults to 256 (valid range: 1–256).
   Actual shard count is capped at the revision count; `limit=8, max_shards=4`
   assigns two revisions to each of four zero-based shards. Both revision and
   enrichment jobs use GitHub's `strategy.job-index` and `strategy.job-total`;
   only discovery uses `max_shards` to construct the matrix.
   Every revision is still an independent Nix derivation. Instantiated recipes,
   downloaded inputs, and built outputs are GC-rooted through publication.
3. **merge revisions** depends on all shards succeeding. Each shard publishes a small
   GitHub artifact mapping revision SHAs to final JSON store paths. Merge
   validates exact receipt coverage and path names against the manifest, fetches
   all revision JSONs in one fetch-only Nix call, then runs the merge scripts
   directly in the workspace. It never reconstructs extraction recipes or fetches
   their nixpkgs source trees. Real `index/` and `evaluations/` directories travel
   as a compressed GitHub artifact, not a Nix derivation or Cachix output.
   Published revision JSONs remain reference-free, preserving package hashes
   without retaining build dependencies. Extraction recipes are unchanged.
   No live availability probes.
4. **enrichment shard N** optionally checks output presence and recursively
   crawls dependencies. It reuses the revision matrix count, but partitions
   package attributes using a deterministic shuffle seeded by the full index.
   Each shard publishes `enrichment-observations-shard-N` and
   `resource-usage-enrichment-shard-N` artifacts (retry suffixes only after
   attempt one). HTTP observations are not cached as Nix derivation results.
   Deduplication is per runner; shared dependencies may be fetched by multiple shards.
5. **merge enrichment** validates exact shard coverage and input identity,
   merges output mappings and graph records, rejects conflicting observations,
   then calculates closures globally and packages the snapshot. Optional census
   uses `scripts/ci/observe-census`, also shared by the legacy workflow.
6. **pages** runs only when deployment is explicitly requested; it builds and
   browser-tests the enriched snapshot before deploying.

Enrichment output probes and recursive dependency discovery share one bounded
async HTTP/2 queue across all platforms. The default is 2,048 async workers
(`ENRICH_THREADS` overrides it; this counts tasks, not OS threads). Crawl state,
checkpoint writes and transport counters are owned by one event loop. A small
synchronous adapter serves the existing join coordinator. In-flight and completed requests are deduplicated by digest,
including observed 404s. Output probes refresh observations each invocation;
dependency metadata can resume from the saved graph. Transport failures are
retryable but never checkpointed as absence. Requests allow HTTP cache responses
up to one hour old; the temporary benchmark timeout is 120 seconds. The queue
fetches no package payloads. Stage durations and exit codes are appended to
`index/.outpaths/timings.tsv` under the enrichment working directory.
These are local benchmark-based defaults, not guaranteed optimal on every runner.

Workflow-level concurrency permits only one **whole pipeline** at a time.
There is no polling coordinator, custom check state, or external state database.
GitHub's `needs` supplies fan-in. Revision jobs use `fail-fast: false`, allowing
other shards to finish and publish useful work even when one fails. Merge does
not run after a failed shard. The workflow files must be on the default branch
before the first manual trial. One- and three-revision trials have passed on GitHub.

A shard computes each revision's expected output path, checks only remote
narinfo metadata (including referenced dependencies), and skips cached outputs
without downloading their payloads. Cache misses are collected, realised together, and then pushed.
Only HTTP 404 is treated as missing; network/server errors fail the job. This
probe is an availability hint, not signature/payload verification: Nix verifies
actual downloads when outputs are consumed. Sources may still need downloading
to compute the expected path. Retrying shards reuses successful cached revisions.
Shards must fit the hosted-runner job time limit; large backfills need bounded
workflow runs even though the partitioner handles more than 256 revisions.

Observation, census, and deployment default off. No scheduled backfill is
enabled. `observation_previous` optionally supplies an enriched snapshot for
external observation reuse only. Discovery and pure merge never read a previous
index: every manifest revision supplies an independent cached input.

Each revision publishes one attribute-grouped JSON containing versions, all three
platforms' outputs, and errors, with shared names stored once where possible.
Output and version extraction use separate Nix requests with `--max-jobs 3`
and `--max-jobs 1`. Both must succeed before the combiners run. Lane assignments
come from the actual revision derivation dependencies, without changing recipes.
The Docker wrapper is used both locally and in CI; the final
combiner copies data rather than linking intermediate outputs. Diagnostic text
may still reference nixpkgs sources. Merge reconstructs the per-platform JSON
interface for observation from the combined artifacts.

Shard jobs record host CPU, available memory, swap use, and I/O wait every five
seconds in separate seven-day `runner-*` GitHub artifacts. These are host-wide
samples, not per-process measurements. Build/upload boundaries are timestamped.

New Cachix uploads are limited to per-revision outputs. Aggregated revisions
and enriched snapshots travel as compressed GitHub artifacts, selected by exact
artifact ID. Enriched snapshots include checksums verified before the Pages build.
Pages uses its required deployment artifact; neither snapshots nor sites are
uploaded to Cachix. Existing Cachix entries are not deleted. The discovery
artifact contains metadata only. The legacy scheduled OCI workflows remain unchanged.

## Inputs and outputs

`nix/pipeline-build.nix` takes `inputs`, an absolute path to a directory with:

- `manifest.json`: `{schema: 1, revisions: [...], releases: {...}}`.
- Each revision: full `rev`, `date`, and channel `name`.
- Indexed platforms are fixed in `nix/revision-systems.nix`, not supplied by discovery.

Revision jobs use `nix/revision-build.nix` directly with only `name` and `rev`.
They do not download or read the manifest. `builtins.fetchTree` resolves the
GitHub source from the full commit; discovery does not calculate source hashes.
The `system` argument on the Nix entry point describes the build host/toolchain,
not which platforms to index. The manifest is still used for the aggregate.

No previous aggregate is accepted. Every manifest revision must have an input;
no revision may have a
missing or empty extraction. Individual unsupported packages are omitted by the
existing extractors (output evaluation records error counts); an entirely empty
revision/system fails. Unsupported historical revisions are not silently skipped.

The entry point exposes:

- `perRevision."<channel-name>".versions`: attribute → version JSON.
- `perRevision."<channel-name>".outputs.<system>`: evaluated outputs and package errors.
- `perRevision."<channel-name>".all`: both products for one revision.
- `index`: revisions, releases, versions, history, statistics.
- `evaluations`: explicit files for every manifest revision and supported platform.
- `all`: `index` and `evaluations`, consumed by external observation.

Appending to a manifest does not change existing per-revision derivation
identities. Evaluation runs with `dummy://`, IFD disabled, and no writable host
store or daemon. It computes paths without building the indexed packages.
Evaluation uses nix-eval-jobs' default worker memory threshold (4 GiB), with
no custom memory sizing or override. Give the local VM enough RAM (6 GiB for
one worker). Nix and nix-eval-jobs default to one build job and one evaluator
worker; the pipeline leaves those defaults unchanged. Output evaluation reports progress every 30 seconds.

CI merge always folds the full revision set in the workspace. Receipt checks
reject missing, extra or duplicate revisions and mismatched store-path names.
One `nix-store --realise` call downloads and roots all revision JSONs with
`--max-jobs 0 --builders ''`; Nix schedules concurrent substitutions, and missing
cached files fail rather than triggering extraction. The merge checks schema
and revision identity while reading each JSON, with no duplicate parsing pass.
The compressed merged artifact is consumed by enrichment shards and enrichment
merge. The optional Nix aggregation expression remains available for local use,
but CI does not instantiate, build or publish a merge derivation.

Discovery also collects the latest published tip of each release channel since
13.10, excluding beta-only and architecture/small channels. These are metadata
pointers (full revision, commit date, channel build and name), not extra indexed
revisions or extraction jobs. For old releases without a git-revision object,
the full SHA is read by streaming the archive's .git-revision metadata (no
source extraction or hashing). The unstable revision limit does not limit
release metadata. Missing unstable git-revision files fail discovery; this
fallback is release-only.

Discovery uses one async HTTPX client with HTTP/2 enabled and default connection
pool limits, without an application concurrency cap. Build files come from
releases.nixos.org; paginated listings still use the S3 API with HTTP/1.1 fallback.
Commit metadata requests are deduplicated by SHA within the run. GitHub tokens
are sent only to the GitHub commit API. Failed discovery writes no input bundle.
The workflow runs discovery through the Docker/Nix wrapper on mise's PATH, including
HTTPX and h2 dependencies. No GHCR metadata cache is used.

## Local site verification

Use `scripts/ci/pages-pure`, matching this workflow's `pages` job. The legacy
`scripts/ci/pages` fetches GHCR data and is not the local verification path.
Download the `enriched-snapshot` artifact from a successful enrichment run
(retries add an attempt suffix), placing its `enriched-snapshot.tar.gz` in
`_ci/pure/`, or use the archive produced by local pure enrichment.

```sh
nix develop --command bash scripts/ci/pages-pure
```

This verifies the archive, builds `_site`, and runs browser tests without deploying.
It requires the enriched snapshot, not the merged-revisions archive.

## Local use

The same derivations work locally; no CI credentials or Cachix uploads are
required. Run from the repository root with mise activated so `nix` resolves to
`scripts/nix`, the existing Linux Docker wrapper:

```sh
# One revision, without any manifest:
nix build --file nix/revision-build.nix \
  --argstr name nixos-26.11pre1068949.dc5d91f84032 \
  --argstr rev dc5d91f840324650bac8c379428c7037a416959a \
  all --out-link result-revision -L
# For a smaller local test, select outputs.x86_64-linux instead of all.

nix build --file nix/pipeline-build.nix \
  --argstr inputs /workspace/_ci/my-inputs all --out-link result-pipeline -L

# Tiny offline fixtures plus one real nixpkgs package path, under the sandbox:
nix build '.#checks.aarch64-linux.pure-pipeline' --no-link -L
```

For local external discovery without uploading anything:

```sh
nix develop --command python3 tools/discover-pipeline.py \
  _ci/my-inputs --limit 1
```

The destination must not exist. Discovery fetches channel and commit metadata,
not nixpkgs source trees. GitHub credentials are optional but
increase API rate limits. Merge the resulting manifest directly; no previous
index is needed.

`scripts/nix` configures the public `trans-nix-index` Cachix substituter and its
signing public key for **every local and CI invocation**. Reads need no token.
Publishing scripts require `CACHIX_AUTH_TOKEN`; CI obtains it from the repository
secret of that name. No credential belongs in a manifest, Nix expression, or
tracked config. Cachix is a cache, so keep the result paths and arrange retention
for durable historical artifacts before a production cutover.
