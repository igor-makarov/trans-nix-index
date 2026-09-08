{ pkgs, system }:
{
  revision-paths = pkgs.runCommand "check-revision-paths" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/revision-paths.py} ${../tools/prepare-revision-paths.py} | tee "$out"
  '';
  enrichment = pkgs.runCommand "check-enrichment" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/enrichment.py} ${../tools} | tee "$out"
  '';
  pure-pipeline = import ../tests/pure-pipeline.nix { inherit pkgs; };
  prepare-merge = pkgs.runCommand "check-prepare-merge" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/prepare-merge.py} ${../tools/prepare-merge.py} | tee "$out"
  '';
  revision-shards =
    pkgs.runCommand "check-revision-shards" { nativeBuildInputs = [ pkgs.python3 ]; }
      ''
        python3 ${../tests/revision-shards.py} ${../tools/revision-shards.py} | tee "$out"
      '';
  shard-build-lanes =
    pkgs.runCommand "check-shard-build-lanes" { nativeBuildInputs = [ pkgs.python3 ]; }
      ''
        python3 ${../tests/shard-build-lanes.py} ${../tools} | tee "$out"
      '';
  pure-inputs = pkgs.runCommand "check-pure-inputs" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/pure-inputs.py} ${../tools} | tee "$out"
  '';
  ci =
    pkgs.runCommand "check-ci"
      {
        nativeBuildInputs = [
          pkgs.actionlint
          pkgs.bash
        ];
      }
      ''
        cp -r ${../.github} .github
        actionlint -shellcheck="" .github/workflows/*.yml
        bash -n ${../scripts/nix}
        for script in ${../scripts/ci}/* ${../tools}/*.sh; do bash -n "$script"; done
        # Workflow policy: automation publishes OCI snapshots, never source commits.
        if grep -E 'git (add|commit|push)' .github/workflows/*.yml ${../scripts/ci}/*; then exit 1; fi
        # Automation defaults on; manual dispatch bypasses the opt-out gates.
        for workflow in census update-index; do
          grep -Fq "github.event_name == 'workflow_dispatch' || vars.DISABLE_SCHEDULES != 'true'" ".github/workflows/$workflow.yml"
        done
        grep -Fq "github.event_name == 'workflow_dispatch' || vars.DISABLE_PAGES != 'true'" .github/workflows/pages.yml
        touch "$out"
      '';
  extract = pkgs.runCommand "check-extract" {
    summary = builtins.toJSON (import ../tests/extract.nix { inherit system; });
  } ''echo "$summary" > $out'';
  incremental =
    pkgs.runCommand "check-incremental"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.bash
        ];
      }
      ''
        mkdir source
        cp -r ${../tools} source/tools
        cp -r ${../nix} source/nix
        python3 ${../tests/incremental.py} source | tee $out
      '';
  snapshot =
    pkgs.runCommand "check-snapshot"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.bash
        ];
      }
      ''
        mkdir source
        cp -r ${../tools} source/tools
        python3 ${../tests/snapshot.py} source | tee $out
      '';
  site-data = pkgs.runCommand "check-site-data" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/site-data.py} ${../tools}/build-site-data.py | tee $out
  '';
  shard-paths =
    pkgs.runCommand "check-shard-paths"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.nodejs
        ];
      }
      ''
        python3 ${../tests/shard-paths.py} ${../tools} ${../site/js/shard-path.js} | tee $out
      '';
  update-plan = pkgs.runCommand "check-update-plan" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/update-plan.py} ${../tools/update-plan.py} | tee $out
  '';
  oci = pkgs.runCommand "check-oci" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/oci.py} ${../tools} | tee $out
    python3 ${../tests/snapshot-tags.py} ${../tools} | tee -a $out
  '';
  docs-links = pkgs.runCommand "check-docs-links" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    mkdir -p repo/docs repo/nix repo/tools repo/scripts/ci
    cp ${../docs}/*.md repo/docs/
    cp ${../nix}/*.nix repo/nix/
    cp ${../tools}/*.sh ${../tools}/*.py repo/tools/
    cp ${../scripts/ci}/* repo/scripts/ci/
    cd repo
    python3 ${../tools/check-links.py} docs/*.md | tee $out
  '';
  topup-merge = pkgs.runCommand "check-topup-merge" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/topup-merge.py} ${../tools/merge-nested-eval.py} | tee $out
  '';
  store-liveness = pkgs.runCommand "check-store-liveness" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/store-liveness.py} ${../tools/consolidate-outpaths.py} | tee $out
  '';
  fetch-retry = pkgs.runCommand "check-fetch-retry" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/fetch-retry.py} ${../tools/fetch-store-paths.py} | tee $out
  '';
}
