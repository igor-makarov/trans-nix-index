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
   validates exact manifest coverage, downloads and roots those cached inputs
   with builds disabled, then folds them into the version index, history, and
   statistics. It never reconstructs extraction recipes or fetches their nixpkgs
   source trees. One merge derivation writes real `index/` and `evaluations/`
   directories, not a symlink wrapper. Published revision JSONs and the merged
   directory use structured `unsafeDiscardReferences.out = true` with an empty
   allowed-reference check: package hashes remain verbatim data, but downloads
   retain no build dependencies. Intermediate extraction recipes are unchanged.
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
HTTP queue across all platforms. The default is 128 workers (`ENRICH_THREADS`
overrides it). In-flight and completed requests are deduplicated by digest,
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

Cachix holds per-revision outputs, aggregates, observation snapshots, and site
closures. The discovery artifact contains metadata only, and its exact
artifact ID is passed to consumers (also when retrying failed jobs). Result
store paths travel as job outputs. Pages additionally uses its required upload
artifact for deployment. The legacy scheduled OCI workflows remain unchanged.

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

Merge always folds the full revision set. Its CI wrapper instantiates `all` once,
roots that `.drv`, and runs `nix-store --realise --dry-run` on it. The preflight
reads recipe metadata for the planned builds: only derivations marked
`transNixIndexMerge = "1"` may build. Revision outputs and toolchain dependencies
must already exist locally or be substitutable. Unknown plan formats fail closed.
No manifest-based duplicate input list is used for this check.

The preflight fetches and roots planned downloads and existing boundary inputs
with local and remote builders disabled. The wrapper then realises the exact
same `.drv`. Fetching remains outside the sandboxed pure computation. Direct
`nix build` remains useful for local development but does not enforce this CI
preflight policy.

Discovery also collects the latest published tip of each release channel since
13.10, excluding beta-only and architecture/small channels. These are metadata
pointers (full revision, commit date, channel build and name), not extra indexed
revisions or extraction jobs. For old archives without a git-revision object,
ambiguous short hashes are resolved by streaming the archive's .git-revision
metadata (no source extraction or hashing). The unstable revision limit does
not limit release metadata.

## Local use

The same derivations work locally; no CI credentials or Cachix uploads are
required. All commands use the existing Linux Docker wrapper:

```sh
# One revision, without any manifest:
mise run nix -- build --file nix/revision-build.nix \
  --argstr name nixos-26.11pre1068949.dc5d91f84032 \
  --argstr rev dc5d91f840324650bac8c379428c7037a416959a \
  all --out-link result-revision -L
# For a smaller local test, select outputs.x86_64-linux instead of all.

mise run nix -- build --file nix/pipeline-build.nix \
  --argstr inputs /workspace/_ci/my-inputs all --out-link result-pipeline -L

# Tiny offline fixtures plus one real nixpkgs package path, under the sandbox:
mise run nix -- build '.#checks.aarch64-linux.pure-pipeline' --no-link -L
```

For local external discovery without uploading anything:

```sh
mise run nix -- develop --command python3 tools/discover-pipeline.py \
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
