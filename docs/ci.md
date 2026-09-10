# CI and pipeline publication

`ci.yml` retains automatic main/PR formatting, pipeline/tooling tests, workflow
linting, and generated-data exclusion checks. It no longer fetches the legacy
GHCR snapshot to build a site. Data-dependent site/browser verification belongs
to the manual pipeline.

All Nix jobs use `ubuntu-24.04-arm`, `actions/checkout@v7`, `jdx/mise-action@v4`,
and the repository's Docker Nix wrapper. No workflow commits or pushes source.

## Manual data pipeline

See [the pipeline reference](pure-pipeline.md) for inputs, handoffs, and local use.

- `pipeline`: manual orchestrator, discovery through optional deployment.
- `pipeline-manual`: manual restart from an existing named stage artifact.
- Reusable workflows: `pipeline-discover`, `pipeline-index`, `pipeline-enrich`,
  `pipeline-site`, and `pipeline-deploy`.

The superseded `update-index`, `census`, and `pages` workflows are deleted.
There are **no automatic pipeline triggers**. Production publishing is restricted
to main/full manifests; named trial repositories isolate branch/limited runs.

## GHCR artifacts

Each scope uses `ghcr.io/<owner>/<repo>-pipeline-<scope>`, with named tags:

| Tag                 | Contents                                            |
| ------------------- | --------------------------------------------------- |
| `revision-manifest` | Revisions, releases, and revision build plan        |
| `revision-index`    | Merged index and per-platform evaluations           |
| `enriched-snapshot` | Complete checksummed snapshot archive               |
| `site`              | Built site, published only after browser tests pass |
| `deployed-site`     | Alias to the site digest successfully deployed      |

These are OCI artifacts, not runnable images. Stable archive and manifest metadata
makes equal content retain its digest. Each stage records the upstream digest it
processed. Equal input means reuse; force explicitly requests work after code
changes. Uploads use candidate tags; named tags advance only after verification.
Consumers pin digests, verify archive hashes/sizes, and reject unsafe archive paths.
Registry errors are failures, not cache misses. Failure never advances acknowledgment.

Per-revision JSONs remain in Cachix; intermediate shard receipts and observations
are short-lived GitHub Actions artifacts. No historical aggregate is needed to
rebuild an index. Previous enriched snapshots optionally provide observation reuse.

## Permissions

Registry writers use `GITHUB_TOKEN` with `packages: write`. Set newly created GHCR
packages public if anonymous/local reads are desired. Credentials are temporary
and never included in artifacts. Cachix publishing uses `CACHIX_AUTH_TOKEN` only
in revision workers.

Only the deployment workflow uses the protected `github-pages` environment and
Pages deployment permissions. A branch build with deployment disabled never
enters that environment. Successful deployment updates `deployed-site`; failed
or skipped deployment leaves it untouched.

Legacy OCI snapshot tooling remains for historical recovery, but its `latest`
tag and old timestamp tags are not inputs to the new pipeline.
