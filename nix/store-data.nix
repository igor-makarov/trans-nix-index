# The store-data products: meta/revdeps/identify shards, census.json,
# universe.bin. Built from the pinned artifacts, so the site's store views and
# the fast evaluation path always describe the same data cut.
#
# Give tools/build-site-data.py an assembled root with the generated index.
{ pkgs }:
pkgs.runCommand "nixpkgs-multiverse-store-data"
  {
    nativeBuildInputs = [ pkgs.python3 ];
  }
  ''
    mkdir -p $out
    root=$(mktemp -d)
    mkdir -p "$root/index"
    cp ${pkgs.multiverse-index}/revisions.json "$root/revisions.json"
    cp ${pkgs.multiverse-index}/versions.json "$root/index/versions.json"
    cp ${pkgs.multiverse-index}/history.json "$root/index/history.json"
    python3 ${../tools/build-site-data.py} "$root" ${pkgs.multiverse-data} $out
  ''
