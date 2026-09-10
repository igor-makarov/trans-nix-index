# Pure revision evaluation and aggregation. External discovery supplies manifest.
{
  pkgs,
  manifest,
  revisionFiles ? null,
  sourceFor ? (
    revision:
    if revision ? tree then
      import ./fetch-git-tree.nix {
        inherit pkgs;
        inherit (revision) rev tree;
      }
    else
      (builtins.fetchTree {
        type = "github";
        owner = "NixOS";
        repo = "nixpkgs";
        inherit (revision) rev;
      }).outPath
  ),
}:
let
  # Mark only aggregation recipes; preflight reads this from the actual .drv.
  mergeOnly =
    drv:
    drv.overrideAttrs (_: {
      transNixIndexMerge = "1";
    });
  revisions = manifest.revisions;
  systems = import ./revision-systems.nix;
  perRevision = builtins.listToAttrs (
    map (revision: {
      name = revision.name;
      value = import ./revision.nix {
        inherit pkgs revision systems;
        source = sourceFor revision;
      };
    }) revisions
  );
  manifestFile = mergeOnly (pkgs.writeText "pipeline-inputs.json" (builtins.toJSON manifest));
  files = mergeOnly (
    pkgs.writeText "revision-files.json" (
      builtins.toJSON (
        builtins.listToAttrs (
          map (r: {
            name = r.rev;
            value =
              if revisionFiles == null then
                perRevision.${r.name}.all
              else
                builtins.storePath revisionFiles.${r.rev};
          }) revisions
        )
      )
    )
  );
  all = mergeOnly (
    pkgs.runCommand "pure-index-pipeline"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.bash
        ];
        __structuredAttrs = true;
        unsafeDiscardReferences.out = true;
        outputChecks.out.allowedReferences = [ ];
      }
      ''
        mkdir "$out"
        python3 ${../tools/merge-revisions.py} ${manifestFile} ${files} "$out/index"
        mkdir work work/index
        cp "$out/index/revisions.json" work/
        cp "$out/index/history.json" work/index/
        MULTIVERSE_ROOT="$PWD/work" bash ${../tools/build-stats.sh}
        cp work/index/stats.json "$out/index/"
        python3 ${../tools/split-revision-evaluations.py} ${files} "$out/evaluations"
      ''
  );
in
assert manifest.schema == 1;
assert revisions != [ ];
assert
  revisionFiles == null
  || builtins.attrNames revisionFiles == builtins.sort builtins.lessThan (map (r: r.rev) revisions);
assert systems != [ ];
assert builtins.length (pkgs.lib.unique (map (r: r.rev) revisions)) == builtins.length revisions;
assert builtins.length (pkgs.lib.unique (map (r: r.name) revisions)) == builtins.length revisions;
{
  inherit perRevision all;
  index = "${all}/index";
  evaluations = "${all}/evaluations";
}
