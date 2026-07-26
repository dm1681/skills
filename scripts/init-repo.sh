#!/usr/bin/env bash
# Scaffold another repository to use this collection's agent-agnostic cloud
# skills sync (Option A: vendor by copy). Run it from a checkout of the skills
# repo:
#
#   scripts/init-repo.sh <target-repo-dir> [options]
#
# It performs, non-destructively and idempotently:
#   1. Copies scripts/sync-agent-skills.sh and .claude/hooks/session-start.sh
#      into the target, and registers the hook in .claude/settings.json
#      (merging if that file already exists).
#   2. Vendors every skill from this repo's skills/ into the target (so the
#      installer uses local mode — no auth needed), unless --no-vendor.
#   3. Creates AGENTS.md (shared agent guidance) and CLAUDE.md (a one-line
#      @AGENTS.md import), unless --no-agents-md.
#
# Options:
#   --subdir DIR      vendor skills into DIR instead of skills/ (the hook is
#                     configured to read from there)
#   --no-vendor       do not copy skills in (use submodule/clone mode instead)
#   --no-agents-md    do not create AGENTS.md / CLAUDE.md
#   --force           replace an already-vendored skill of the same name
#   -h, --help        show this help
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() { sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; }

SUBDIR="skills"
VENDOR=1
AGENTS_MD=1
FORCE=0
TARGET=""

while [ $# -gt 0 ]; do
  case "$1" in
    --subdir) SUBDIR="${2:?--subdir needs a value}"; shift 2;;
    --subdir=*) SUBDIR="${1#*=}"; shift;;
    --no-vendor) VENDOR=0; shift;;
    --no-agents-md) AGENTS_MD=0; shift;;
    --force) FORCE=1; shift;;
    -h|--help) usage; exit 0;;
    --) shift; break;;
    -*) echo "error: unknown option: $1" >&2; usage; exit 2;;
    *) if [ -z "$TARGET" ]; then TARGET="$1"; shift; else echo "error: unexpected argument: $1" >&2; exit 2; fi;;
  esac
done

log() { echo "[init-repo] $*"; }

[ -n "$TARGET" ] || { echo "error: target repo directory required" >&2; usage; exit 2; }
[ -d "$TARGET" ] || { echo "error: target not found: $TARGET" >&2; exit 2; }
TARGET="$(cd "$TARGET" && pwd)"

# Sanity: are we really inside the skills repo?
[ -f "$SRC_ROOT/scripts/sync-agent-skills.sh" ] && [ -d "$SRC_ROOT/skills" ] || {
  echo "error: $SRC_ROOT does not look like the skills repo" >&2; exit 1; }
[ "$TARGET" != "$SRC_ROOT" ] || { echo "error: target is the skills repo itself" >&2; exit 1; }

log "source: $SRC_ROOT"
log "target: $TARGET"

# --- 1. Machinery -----------------------------------------------------------
mkdir -p "$TARGET/scripts" "$TARGET/.claude/hooks"
cp "$SRC_ROOT/scripts/sync-agent-skills.sh" "$TARGET/scripts/sync-agent-skills.sh"
HOOK_DEST="$TARGET/.claude/hooks/session-start.sh"
cp "$SRC_ROOT/.claude/hooks/session-start.sh" "$HOOK_DEST"
chmod +x "$TARGET/scripts/sync-agent-skills.sh" "$HOOK_DEST"
log "installed installer + Claude hook"

# Configure the hook for a non-default vendor dir.
if [ "$SUBDIR" != "skills" ]; then
  subdir_esc="$(printf '%s' "$SUBDIR" | sed 's/[#&\\]/\\&/g')"
  sed 's#exec "\$INSTALLER"#AGENT_SKILLS_SUBDIR="'"$subdir_esc"'" exec "$INSTALLER"#' \
    "$HOOK_DEST" > "$HOOK_DEST.tmp" && mv "$HOOK_DEST.tmp" "$HOOK_DEST"
  chmod +x "$HOOK_DEST"
  log "configured hook to read skills from: $SUBDIR/"
fi

# Register the hook in settings.json.
SETTINGS="$TARGET/.claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
  cp "$SRC_ROOT/.claude/settings.json" "$SETTINGS"
  log "created .claude/settings.json"
elif grep -q "session-start.sh" "$SETTINGS"; then
  log ".claude/settings.json already registers the hook; left as-is"
elif command -v python3 >/dev/null 2>&1; then
  python3 - "$SETTINGS" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as fh:
    data = json.load(fh)
entry = {"hooks": [{"type": "command",
                    "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"}]}
data.setdefault("hooks", {}).setdefault("SessionStart", []).append(entry)
with open(path, "w") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  log "merged SessionStart hook into existing .claude/settings.json"
else
  log "WARNING: python3 not found; add this SessionStart hook to $SETTINGS manually:"
  cat "$SRC_ROOT/.claude/settings.json"
fi

# --- 2. Vendor skills -------------------------------------------------------
if [ "$VENDOR" -eq 1 ]; then
  mkdir -p "$TARGET/$SUBDIR"
  copied=0
  for d in "$SRC_ROOT/skills"/*/; do
    d="${d%/}"
    [ -f "$d/SKILL.md" ] || continue
    name="$(basename "$d")"
    if [ -e "$TARGET/$SUBDIR/$name" ] && [ "$FORCE" -ne 1 ]; then
      log "skip existing skill (use --force to replace): $SUBDIR/$name"
      continue
    fi
    rm -rf "$TARGET/$SUBDIR/$name"
    cp -R "$d" "$TARGET/$SUBDIR/$name"
    copied=$((copied + 1))
    log "vendored: $SUBDIR/$name"
  done
  log "vendored $copied skill(s)"
else
  log "skipped vendoring (--no-vendor); the installer will clone at session start"
fi

# --- 3. AGENTS.md / CLAUDE.md ----------------------------------------------
if [ "$AGENTS_MD" -eq 1 ]; then
  AGENTS="$TARGET/AGENTS.md"
  if [ ! -f "$AGENTS" ]; then
    cat > "$AGENTS" <<'MD'
# Agent guide

<!-- Shared guidance for all coding agents (Claude Code, Codex, Cursor,
Copilot, ...). Claude Code reads it through the CLAUDE.md import. Replace the
project section below with real context. -->

## Project

TODO: one paragraph on what this repo is, plus how to build, run, and test it.

## Agent skills (cloud sync)

This repo vendors version-controlled agent skills so cloud/web sessions have
them. They are installed into each agent's user-scope skill directory at
session start.

- Installer: `scripts/sync-agent-skills.sh` (agent-neutral; installs into
  `~/.claude/skills` and the shared `~/.agents/skills`).
- Claude Code trigger: `.claude/hooks/session-start.sh`, registered in
  `.claude/settings.json`, runs the installer in web sessions.
- Other agents: run `scripts/sync-agent-skills.sh` from that agent's own
  startup hook.

Refresh the vendored skills by re-running the source repo's
`scripts/init-repo.sh` against this repo.
MD
    log "created AGENTS.md"
  elif grep -qi "agent skills" "$AGENTS"; then
    log "AGENTS.md already documents agent skills; left as-is"
  else
    cat >> "$AGENTS" <<'MD'

## Agent skills (cloud sync)

This repo vendors version-controlled agent skills so cloud/web sessions have
them, installed at session start via `scripts/sync-agent-skills.sh` (Claude Code
runs it from `.claude/hooks/session-start.sh`; other agents call it from their
own startup hook).
MD
    log "appended agent-skills section to existing AGENTS.md"
  fi

  CLAUDE="$TARGET/CLAUDE.md"
  if [ ! -f "$CLAUDE" ]; then
    cat > "$CLAUDE" <<'MD'
# CLAUDE.md

Agent guidance for this repository is maintained in AGENTS.md so every coding
agent shares one source of truth. The import below pulls it into Claude Code's
context — edit AGENTS.md, not this file.

@AGENTS.md
MD
    log "created CLAUDE.md (imports AGENTS.md)"
  elif grep -q "@AGENTS.md" "$CLAUDE"; then
    log "CLAUDE.md already imports AGENTS.md; left as-is"
  else
    printf '\n@AGENTS.md\n' >> "$CLAUDE"
    log "added @AGENTS.md import to existing CLAUDE.md"
  fi
fi

# --- Done -------------------------------------------------------------------
ADD_PATHS="scripts/sync-agent-skills.sh .claude/"
[ "$VENDOR" -eq 1 ] && ADD_PATHS="$ADD_PATHS $SUBDIR/"
[ "$AGENTS_MD" -eq 1 ] && ADD_PATHS="$ADD_PATHS AGENTS.md CLAUDE.md"
cat >&2 <<EOF

[init-repo] done. Next:
  cd "$TARGET"
  git add $ADD_PATHS
  git commit -m "Add agent-agnostic cloud skills sync"
  git push        # must land on the repo's default branch to take effect
EOF
