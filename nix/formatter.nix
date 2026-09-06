# `nix fmt`. The tree wrapper rather than bare `nixfmt`, which now deprecates
# being handed a directory and formats stdin when `nix fmt` is called with no
# paths at all. Extended so that every language in the tree has a formatter
# rather than only the Nix code: prettier for the site's html/css/js and for
# markdown, black for the tools.
{ pkgs }:
pkgs.nixfmt-tree.override {
  runtimeInputs = [
    pkgs.prettier
    pkgs.black
  ];
  settings = {
    formatter.prettier = {
      command = "prettier";
      options = [ "--write" ];
      includes = [
        "*.css"
        "*.js"
      ];
    };
    # The scripts in tools/. black rather than a linter:
    # the point is that nobody argues about where a call wraps, and CI's one
    # formatting step is what settles it.
    formatter.black = {
      command = "black";
      options = [ "--quiet" ];
      includes = [ "*.py" ];
    };
    # Markdown, at the width the docs are already written to. proseWrap is
    # left at its default of preserving the author's line breaks: these files
    # are hand-wrapped prose, and reflowing them would rewrite every paragraph
    # and make every future diff a whole-file diff.
    formatter.prettier-markdown = {
      command = "prettier";
      options = [
        "--write"
        "--print-width"
        "80"
      ];
      includes = [ "*.md" ];
    };
    # HTML separately: the default whitespace-sensitive mode emits `></a\n>`
    # gymnastics to keep inline spacing byte-identical. This page keeps its
    # inline spacing in text nodes, so the insensitive mode is safe and far more
    # readable.
    formatter.prettier-html = {
      command = "prettier";
      options = [
        "--write"
        "--html-whitespace-sensitivity"
        "ignore"
        "--print-width"
        "100"
      ];
      includes = [ "*.html" ];
    };
  };
}
