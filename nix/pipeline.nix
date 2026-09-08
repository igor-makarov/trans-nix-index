# Pure revision evaluation and aggregation. External discovery supplies manifest.
{
  pkgs,
  manifest,
  sourceFor ? (
    revision:
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
            value = perRevision.${r.name}.versions;
          }) revisions
        )
      )
    )
  );
  index = mergeOnly (
    pkgs.runCommand "revision-index"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.bash
        ];
      }
      ''
        python3 ${../tools/merge-revisions.py} ${manifestFile} ${files} "$out"
        mkdir work work/index
        cp "$out/revisions.json" work/
        cp "$out/history.json" work/index/
        MULTIVERSE_ROOT="$PWD/work" bash ${../tools/build-stats.sh}
        cp work/index/stats.json "$out/"
      ''
  );
  evaluations = mergeOnly (
    pkgs.linkFarm "revision-evaluations" (
      pkgs.lib.concatMap (
        r:
        map (system: {
          name = "${r.rev}.${system}.pure.json";
          path = "${perRevision.${r.name}.outputs.${system}}/outputs.json";
        }) systems
      ) revisions
    )
  );
in
assert manifest.schema == 1;
assert revisions != [ ];
assert systems != [ ];
assert builtins.length (pkgs.lib.unique (map (r: r.rev) revisions)) == builtins.length revisions;
assert builtins.length (pkgs.lib.unique (map (r: r.name) revisions)) == builtins.length revisions;
{
  inherit perRevision index evaluations;
  all = mergeOnly (
    pkgs.linkFarm "pure-index-pipeline" [
      {
        name = "index";
        path = index;
      }
      {
        name = "evaluations";
        path = evaluations;
      }
    ]
  );
}
