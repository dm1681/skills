#!/usr/bin/env bash
# Claude Code SessionStart hook (web / cloud) — make version-controlled agent
# skills available in the ephemeral container, which does not carry your local
# ~/.claude/skills.
#
# This is a thin, Claude-specific wrapper: it applies the remote guard, maps
# Claude's env onto the agent-neutral installer, and runs it. The actual install
# logic lives in scripts/sync-agent-skills.sh, which any agent (or a person) can
# invoke directly. See docs/cloud-skills-sync.md.
set -euo pipefail

# Only run in Claude Code on the web / remote sessions. Local machines manage
# their own skills via ./install.sh.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
INSTALLER="${PROJECT_DIR}/scripts/sync-agent-skills.sh"

if [ ! -x "$INSTALLER" ]; then
  echo "[skills-sync] installer not found at $INSTALLER; nothing to do" >&2
  exit 0
fi

# Install into every agent skill root (Claude + shared ~/.agents/skills) so the
# container is ready for whichever agent uses it.
AGENT_SKILLS_PROJECT_DIR="$PROJECT_DIR" exec "$INSTALLER"
