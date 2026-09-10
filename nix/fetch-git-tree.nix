# Build-time fetch, verified against the commit's Git root tree object ID.
{
  pkgs,
  rev,
  tree,
}:
assert builtins.match "[0-9a-f]{40}" rev != null;
assert builtins.match "[0-9a-f]{40}" tree != null;
pkgs.runCommand "source"
  {
    nativeBuildInputs = [
      pkgs.curl
      pkgs.gnutar
      pkgs.gzip
    ];
    outputHashMode = "git";
    outputHashAlgo = "sha1";
    outputHash = tree;
    impureEnvVars = pkgs.lib.fetchers.proxyImpureEnvVars;
    SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
    preferLocalBuild = true;
  }
  ''
    curl --fail --location --retry 3 --connect-timeout 30 \
      https://codeload.github.com/NixOS/nixpkgs/tar.gz/${rev} -o source.tar.gz
    mkdir "$out"
    tar --extract --gzip --file source.tar.gz --strip-components=1 --directory "$out"
  ''
