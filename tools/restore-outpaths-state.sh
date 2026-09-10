#!/usr/bin/env bash
# Restore plain local files from the single verified release archive.
set -euo pipefail
: "${MULTIVERSE_ROOT:?Set the work directory}"
snapshot="${1:?Pass the resolved snapshot directory}"
work="$MULTIVERSE_ROOT/index/.outpaths"
data="$work/data"
mkdir -p "$data/prev" "$data/prev-shards"
for file in "$snapshot"/artifacts/*.json; do
  name=$(basename "$file")
  case "$name" in
    info-indexed*.json|refs-indexed*.json|closures*.json|outs-indexed.json)
      cp "$file" "$data/prev-shards/" ;;
    *) cp "$file" "$data/prev/"; cp "$file" "$data/" ;;
  esac
done
cp "$snapshot/state/graph.jsonl" "$work/graph.jsonl"
shopt -s nullglob
for file in "$snapshot"/state/misses-*.json; do cp "$file" "$data/"; done
