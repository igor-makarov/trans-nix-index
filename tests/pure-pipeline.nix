{ pkgs }:
let
  revision = {
    rev = "1111111111111111111111111111111111111111";
    date = "2026-01-01";
    name = "nixos-26.05pre1.111111111111";
  };
  manifest = {
    schema = 1;
    revisions = [ revision ];
    releases = { };
  };
  pipeline = import ../nix/pipeline.nix {
    inherit pkgs manifest;
    sourceFor = _: ./fixtures/pure-rev;
  };
  again = import ../nix/pipeline.nix {
    inherit pkgs;
    manifest = manifest // {
      revisions = [
        revision
        (
          revision
          // {
            rev = "2222222222222222222222222222222222222222";
            date = "2026-01-02";
            name = "nixos-26.05pre2.222222222222";
          }
        )
      ];
    };
    sourceFor = _: ./fixtures/pure-rev;
  };
  direct = import ../nix/revision.nix {
    inherit pkgs;
    revision = {
      inherit (revision) name rev;
    };
    source = ./fixtures/pure-rev;
  };
  realSource = pkgs.writeTextDir "default.nix" ''
    args: let packages = import ${pkgs.path} args; in { inherit (packages) hello; }
  '';
  real = import ../nix/revision.nix {
    inherit pkgs revision;
    source = realSource;
    systems = [ pkgs.stdenv.hostPlatform.system ];
    versionSystem = pkgs.stdenv.hostPlatform.system;
  };
  expected = builtins.unsafeDiscardStringContext pkgs.hello.outPath;
in
assert direct.all.drvPath == pipeline.perRevision.${revision.name}.all.drvPath;
assert
  builtins.attrNames direct.outputs
  == builtins.sort builtins.lessThan (import ../nix/revision-systems.nix);
assert
  pipeline.perRevision.${revision.name}.all.drvPath == again.perRevision.${revision.name}.all.drvPath;
pkgs.runCommand "check-pure-pipeline" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 - ${pipeline.all} ${again.all} ${
      real.outputs.${pkgs.stdenv.hostPlatform.system}
    }/outputs.json '${expected}' ${direct.all} <<'PY'
  import json, pathlib, sys
  first, second = map(pathlib.Path, sys.argv[1:3])
  load = lambda p: json.loads(p.read_text())
  a = load(first / 'index/versions.json')
  assert a == {'revisionCount': 1, 'attrs': {'hello': {'1': None}, 'jetbrains.idea': {'2': None}}}, a
  b = load(second / 'index/history.json')
  assert b['revisionCount'] == 2
  assert b['attrs']['hello']['1'] == [0, None]
  for system in ('x86_64-linux', 'aarch64-linux', 'aarch64-darwin'):
      data = load(first / f'evaluations/{"1" * 40}.{system}.pure.json')
      assert data['system'] == system
      assert data['errorCount'] == 1, data
      assert set(data['attrs']['hello']['outputs']) == {'out', 'dev'}, data
  x86 = load(first / f'evaluations/{"1" * 40}.x86_64-linux.pure.json')
  arm = load(first / f'evaluations/{"1" * 40}.aarch64-linux.pure.json')
  assert x86['attrs']['hello']['outputs']['out'] != arm['attrs']['hello']['outputs']['out']
  combined = load(pathlib.Path(sys.argv[5]))
  assert combined['schema'] == 1 and combined['rev'] == '1' * 40
  assert combined['attrs']['hello']['version'] == '1'
  assert set(combined['systems']) == {'x86_64-linux', 'aarch64-linux', 'aarch64-darwin'}
  assert all(sum('error' in a['systems'].get(s, {}) for a in combined['attrs'].values()) == 1 for s in combined['systems'])
  real = load(pathlib.Path(sys.argv[3]))
  assert real['attrs']['hello']['outputs']['out'] == sys.argv[4].split('/')[3][:32], real
  print('sandboxed versions, output paths, independent revision identities, full merge, real nixpkgs hello path: OK')
  PY
    touch "$out"
''
