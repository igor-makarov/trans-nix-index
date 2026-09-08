{
  system,
  config,
  overlays ? [ ],
}:
let
  package =
    version:
    builtins.derivation {
      inherit system version;
      name = "hello-${version}";
      builder = "/bin/sh";
      args = [
        "-c"
        "exit 99"
      ]; # Must never be built by the indexing pipeline.
      outputs = [
        "out"
        "dev"
      ];
      src = ./source.txt;
    };
in
{
  hello = package "1";
  jetbrains.idea = package "2";
  broken = throw "expected unsupported package";
}
