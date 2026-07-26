#!/usr/bin/env bash
# Package each skill under skills/ into an upload-ready .zip for claude.ai
# (Settings -> Capabilities -> Skills -> "Upload skill" -> drag & drop).
#
# Each archive contains the skill's SKILL.md at its ROOT alongside any supporting
# files (references/, scripts/, agents/, ...). claude.ai reads the skill name and
# description from the SKILL.md YAML frontmatter, so no wrapping folder is needed.
#
# Usage: scripts/package-skills.sh [skills-dir] [output-dir]
#   defaults: skills-dir = <repo>/skills, output-dir = <repo>/dist
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/skills}"
OUT="${2:-$ROOT/dist}"

command -v zip >/dev/null 2>&1 || { echo "error: 'zip' is required (apt install zip)" >&2; exit 1; }
[ -d "$SRC" ] || { echo "error: skills dir not found: $SRC" >&2; exit 1; }
mkdir -p "$OUT"

count=0
for d in "$SRC"/*/; do
  d="${d%/}"
  [ -f "$d/SKILL.md" ] || continue
  name="$(basename "$d")"
  archive="$OUT/$name.zip"
  rm -f "$archive"
  # Zip the skill's CONTENTS (SKILL.md at archive root), excluding junk.
  ( cd "$d" && zip -rq "$archive" . -x '*.DS_Store' -x '*/__pycache__/*' -x '*.pyc' )
  echo "packaged: ${archive#"$ROOT"/}"
  count=$((count + 1))
done

echo "packaged $count skill(s) into ${OUT#"$ROOT"/}/"
