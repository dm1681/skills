#!/bin/bash
# SessionStart hook — make version-controlled agent skills available in
# Claude Code on the web (cloud) sessions.
#
# Cloud sessions run in a fresh, ephemeral container: your local
# ~/.claude/skills never travels with them. This hook installs skills from a
# source into the session's ~/.claude/skills so they are discovered on startup.
#
# Reusable across repos: copy this file into <repo>/.claude/hooks/ and register
# it in <repo>/.claude/settings.json (see docs/cloud-skills-sync.md). It has no
# dependencies beyond git + coreutils and is safe to run repeatedly.
#
# Two install modes, tried in order:
#   1. Local  — if the current repo already contains the skills (a "$SKILLS_SUBDIR"
#               directory with <skill>/SKILL.md entries), install from there. No
#               network or auth needed. This is what runs inside the skills repo
#               itself and for any repo that vendors the skills.
#   2. Clone  — otherwise clone "$SKILLS_REPO"@"$SKILLS_REF" and install from it.
#               Requires the source repo to be reachable from the session.
#
# Configure via env (e.g. in settings.json) to reuse for a different source:
#   CLAUDE_SKILLS_REPO    owner/name of the skills source repo (default dm1681/skills)
#   CLAUDE_SKILLS_REF     branch or tag to install from        (default main)
#   CLAUDE_SKILLS_SUBDIR  dir holding <skill>/SKILL.md entries (default skills)
set -euo pipefail

SKILLS_REPO="${CLAUDE_SKILLS_REPO:-dm1681/skills}"
SKILLS_REF="${CLAUDE_SKILLS_REF:-main}"
SKILLS_SUBDIR="${CLAUDE_SKILLS_SUBDIR:-skills}"
DEST="${HOME}/.claude/skills"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"

log() { echo "[cloud-skills-sync] $*" >&2; }

# Only run in Claude Code on the web / remote environments. Local machines
# already manage their own ~/.claude/skills (e.g. via ./install.sh).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Copy every <skill>/SKILL.md directory found under $1 into $DEST, replacing any
# existing copy of the same skill. Returns non-zero if it installed nothing.
install_from() {
  local src="$1" dir name count=0
  mkdir -p "$DEST"
  for skill_md in "$src"/*/SKILL.md; do
    [ -e "$skill_md" ] || continue
    dir="$(dirname "$skill_md")"
    name="$(basename "$dir")"
    rm -rf "${DEST:?}/${name}"
    cp -R "$dir" "$DEST/$name"
    count=$((count + 1))
    log "installed skill: $name"
  done
  log "installed $count skill(s) into $DEST"
  [ "$count" -gt 0 ]
}

# Mode 1: skills already present in the current repo.
if compgen -G "${PROJECT_DIR}/${SKILLS_SUBDIR}/*/SKILL.md" > /dev/null 2>&1; then
  log "installing from local repo: ${SKILLS_SUBDIR}/"
  install_from "${PROJECT_DIR}/${SKILLS_SUBDIR}" || log "no skills found locally"
  exit 0
fi

# Mode 2: clone the source repo and install from it.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
log "cloning ${SKILLS_REPO}@${SKILLS_REF} ..."
if git clone --depth 1 --branch "$SKILLS_REF" \
    "https://github.com/${SKILLS_REPO}.git" "$tmp/repo" \
    2>&1 | sed 's/^/[cloud-skills-sync] git: /' >&2; then
  install_from "$tmp/repo/${SKILLS_SUBDIR}" \
    || log "no skills found in ${SKILLS_REPO}/${SKILLS_SUBDIR}"
else
  log "WARNING: could not clone ${SKILLS_REPO} (a private source repo must be"
  log "         reachable from this session, or vendor the skills locally)."
  log "         Skills not installed; session will continue."
fi

exit 0
