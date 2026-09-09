# One immutable revision. No channel discovery, cache probes, or package builds.
{
  pkgs,
  revision,
  source,
  systems ? import ./revision-systems.nix,
  versionSystem ? "x86_64-linux",
}:
let
  # Import only evaluation code: unrelated site/tool edits must not invalidate it.
  evaluators = builtins.path {
    path = ./.;
    name = "revision-evaluators";
    filter =
      path: type:
      type == "directory"
      || builtins.elem (baseNameOf path) [
        "extract-versions.nix"
        "eval-outpaths.nix"
        "nested-sets.nix"
      ];
  };
  label = pkgs.lib.strings.sanitizeDerivationName revision.name;
  sourcePath = "${source}";
  environment = ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    # Compute store paths without a daemon, writable host store, or IFD.
    export NIX_REMOTE=dummy://
    export NIX_CONFIG='experimental-features = nix-command flakes
    build-users-group =
    allow-import-from-derivation = false'
  '';
  versions =
    pkgs.runCommand "versions-${label}-${versionSystem}"
      {
        nativeBuildInputs = [
          pkgs.nix
          pkgs.python3
        ];
      }
      ''
        ${environment}
        python3 ${../tools/extract-index.py} ${evaluators}/extract-versions.nix \
          ${evaluators}/nested-sets.nix ${source} ${pkgs.lib.escapeShellArg versionSystem} "$out"
        python3 -c 'import json,sys; assert json.load(open(sys.argv[1])), "empty revision extraction"' "$out"
      '';
  outputs = builtins.listToAttrs (
    map (system: {
      name = system;
      value =
        pkgs.runCommand "outputs-${label}-${system}"
          {
            nativeBuildInputs = [
              pkgs.nix-eval-jobs
              pkgs.python3
            ];
          }
          ''
            ${environment}
            mkdir "$out"
            python3 ${../tools/eval-progress.py} nix-eval-jobs \
              --no-instantiate \
              --option max-call-depth 100000 \
              --argstr revPath ${pkgs.lib.escapeShellArg sourcePath} \
              --argstr system ${pkgs.lib.escapeShellArg system} \
              ${evaluators}/eval-outpaths.nix
            python3 ${../tools/reduce-eval-jobs.py} --jobs jobs.jsonl \
              --rev ${pkgs.lib.escapeShellArg revision.rev} --system ${pkgs.lib.escapeShellArg system} \
              --out "$out/outputs.json" --errors "$out/errors.json"
            python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["attrCount"], "empty output evaluation"' "$out/outputs.json"
          '';
    }) systems
  );
in
{
  inherit versions outputs;
  all =
    pkgs.runCommand "revision-${label}.json"
      {
        nativeBuildInputs = [ pkgs.python3 ];
        # A revision JSON must never retain source trees or extraction dependencies.
        allowedReferences = [ ];
      }
      ''
        python3 ${../tools/combine-revision.py} ${versions} \
          ${pkgs.lib.escapeShellArg (builtins.toJSON outputs)} \
          ${pkgs.lib.escapeShellArg revision.rev} "$out"
      '';
}
