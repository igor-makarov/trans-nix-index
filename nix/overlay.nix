{
  self ? { },
  snapshot ? null,
}:
final: _prev: {
  multiverse-index =
    if snapshot == null then
      throw "Supply a resolved data snapshot through nix/site-build.nix"
    else
      snapshot;
  multiverse-data = import ./data.nix { pkgs = final; };
  multiverse-docs = import ./docs.nix { pkgs = final; };
  multiverse-store-data = import ./store-data.nix { pkgs = final; };
  multiverse-site-data = import ./site-data.nix { pkgs = final; };
  multiverse-site = import ./site.nix {
    pkgs = final;
    inherit self;
  };
  multiverse-site-tests = import ./site-tests.nix { pkgs = final; };
  multiverse-formatter = import ./formatter.nix { pkgs = final; };
  multiverse-tools = import ./tools.nix { pkgs = final; };
}
