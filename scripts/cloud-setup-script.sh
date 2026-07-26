#!/bin/bash
# Cloud environment SETUP SCRIPT.
#
# This is NOT a repo hook and is not run from a checkout. Copy its contents into
# your claude.ai cloud environment's "Setup script" field:
#   claude.ai/code -> cloud icon (environment name) -> gear on the environment
#   -> Setup script. (New environment: "Add environment" dialog has the field.)
#
# It runs once before Claude Code launches in each cloud session (result cached),
# for every repo used in that environment, and installs skills into each agent's
# user-scope skill root (~/.claude/skills and the shared ~/.agents/skills). No
# files are committed to any repo.
#
# Installs:
#   1. dm1681/skills      — your own skills          (layout: skills/)
#   2. mattpocock/skills  — engineering skills (MIT) (layout: skills/engineering/)
#
# Requires the environment's network access to allow cloning GitHub (the default
# "Trusted" level does; "None" blocks it). Safe to re-run.
set -u

SKILLS_DIR=/opt/agent-skills

# 1) Your own skills — clones dm1681/skills, which also provides the installer.
rm -rf "$SKILLS_DIR"
git clone --depth 1 https://github.com/dm1681/skills "$SKILLS_DIR" || true
AGENT_SKILLS_PROJECT_DIR="$SKILLS_DIR" \
  "$SKILLS_DIR/scripts/sync-agent-skills.sh" || true

# 2) Matt Pocock engineering skills — reuses the same installer, pointed at their
#    repo's nested engineering category. Delete this block if you don't want them.
AGENT_SKILLS_REPO=mattpocock/skills \
AGENT_SKILLS_SUBDIR=skills/engineering \
AGENT_SKILLS_PROJECT_DIR="$SKILLS_DIR" \
  "$SKILLS_DIR/scripts/sync-agent-skills.sh" || true

# Matt's "code-review" shares a name with Claude's built-in /code-review and
# replaces it for the session. Uncomment to keep Claude's built-in instead:
# rm -rf "$HOME/.claude/skills/code-review" "$HOME/.agents/skills/code-review"

exit 0
