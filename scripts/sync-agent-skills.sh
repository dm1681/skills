#!/usr/bin/env bash
# Install version-controlled agent skills into every agent's user-scope skill
# directory. Agent-neutral and reusable: any coding agent that can run a startup
# script — or a person, by hand — can invoke this to make the skills
# discoverable. Dependency-free (git + coreutils), idempotent, non-interactive.
#
# Source, tried in order:
#   1. Local  — if $AGENT_SKILLS_PROJECT_DIR/$AGENT_SKILLS_SUBDIR contains
#               <skill>/SKILL.md entries, install from there (no network/auth).
#   2. Clone  — otherwise clone $AGENT_SKILLS_REPO@$AGENT_SKILLS_REF.
#
# Destinations: every path in $AGENT_SKILLS_DEST (colon-separated). The default
# covers both user-scope discovery roots used across agents:
#   ~/.claude/skills    Claude Code
#   ~/.agents/skills    shared Agent Skills dir (Codex, Cursor, Copilot)
#
# Config (all optional):
#   AGENT_SKILLS_REPO        owner/name of the source repo   (default dm1681/skills)
#   AGENT_SKILLS_REF         branch or tag                    (default main)
#   AGENT_SKILLS_SUBDIR      dir holding <skill>/SKILL.md      (default skills)
#   AGENT_SKILLS_DEST        colon-separated destination roots
#   AGENT_SKILLS_PROJECT_DIR repo to check for local skills   (default PWD)
set -euo pipefail

REPO="${AGENT_SKILLS_REPO:-dm1681/skills}"
REF="${AGENT_SKILLS_REF:-main}"
SUBDIR="${AGENT_SKILLS_SUBDIR:-skills}"
PROJECT_DIR="${AGENT_SKILLS_PROJECT_DIR:-$PWD}"
DEST_LIST="${AGENT_SKILLS_DEST:-${HOME}/.claude/skills:${HOME}/.agents/skills}"

log() { echo "[skills-sync] $*" >&2; }

# 0 if $1 contains <skill>/SKILL.md entries.
have_skills() {
  local m
  for m in "$1"/*/SKILL.md; do
    [ -e "$m" ] && return 0
  done
  return 1
}

# Copy one skill dir ($1) named ($2) into every destination root, replacing any
# existing copy of that skill name.
install_one() {
  local srcdir="$1" name="$2" dest
  printf '%s\n' "$DEST_LIST" | tr ':' '\n' | while IFS= read -r dest; do
    [ -n "$dest" ] || continue
    mkdir -p "$dest"
    rm -rf "${dest:?}/${name:?}"
    cp -R "$srcdir" "$dest/$name"
  done
}

# Install every <skill>/SKILL.md dir found under $1. Non-zero if none found.
install_from() {
  local src="$1" m dir name total=0
  for m in "$src"/*/SKILL.md; do
    [ -e "$m" ] || continue
    dir="$(dirname "$m")"
    name="$(basename "$dir")"
    install_one "$dir" "$name"
    total=$((total + 1))
    log "installed: $name"
  done
  log "installed $total skill(s) into: $DEST_LIST"
  [ "$total" -gt 0 ]
}

# 1) Local: skills already present in the current repo.
if have_skills "${PROJECT_DIR}/${SUBDIR}"; then
  log "source: local ${SUBDIR}/ in ${PROJECT_DIR}"
  install_from "${PROJECT_DIR}/${SUBDIR}" || log "no skills found locally"
  exit 0
fi

# 2) Clone: fetch the source repo and install from it.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
log "source: cloning ${REPO}@${REF}"
if git clone --depth 1 --branch "$REF" \
    "https://github.com/${REPO}.git" "$tmp/repo" \
    2>&1 | sed 's/^/[skills-sync] git: /' >&2; then
  install_from "$tmp/repo/${SUBDIR}" || log "no skills found in ${REPO}/${SUBDIR}"
else
  log "WARNING: could not clone ${REPO} (a private source repo must be reachable"
  log "         from this session, or vendor the skills locally). Skills not"
  log "         installed; session will continue."
fi

exit 0
