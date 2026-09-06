{ pkgs, system }:
{
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
        # Workflow policy: automation publishes releases, never source commits.
        if grep -E 'git (add|commit|push)' .github/workflows/*.yml ${../scripts/ci}/*; then exit 1; fi
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
    python3 ${../tests/site-data.py} ${../tools/build-site-data.py} | tee $out
  '';
  update-plan = pkgs.runCommand "check-update-plan" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${../tests/update-plan.py} ${../tools/update-plan.py} | tee $out
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
