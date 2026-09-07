// Mirrors tools/shard_paths.py; cross-language fixtures enforce agreement.
export function shardKey(attr) {
  const parts = attr.split(".");
  const leaf = parts.pop();
  const parents = parts.map(
    (part) => part.replace(/[^A-Za-z0-9_-]/gu, "_") || "_",
  );
  const prefix =
    [...leaf]
      .slice(0, 2)
      .join("")
      .toLowerCase()
      .replace(/[^a-z0-9]/gu, "_") || "_";
  return ["pkgs", ...parents, prefix].join("/");
}
