#!/usr/bin/env bash
# Claude Code SessionStart hook, user scope — offer the collection's skills to
# whoever is actually in the session, instead of a setup script guessing for
# them before anyone arrives.
#
# Registered by `install.sh --cloud-bootstrap`, which a cloud environment setup
# script runs once. Everything this prints goes into the session's context, so
# it stays silent unless there is a decision to put in front of the user: the
# offer appears only when none of the collection's skills are installed and the
# decline sentinel is absent. See docs/cloud-skills-sync.md.
#
# This is the user-scope, whole-environment counterpart to
# .claude/hooks/session-start.sh, which installs everything unconditionally for
# one repository that opts in. Both are thin wrappers; the logic they share
# lives in Python and shell that any agent can call directly.
set -uo pipefail

# Only in Claude Code on the web / remote sessions. A local machine chose its
# skills with the dashboard and must not be asked again on every session.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

# Opt out for a whole environment without editing the setup script.
[ "${AGENT_SKILLS_CLOUD_OFFER:-on}" = "off" ] && exit 0

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# install.sh resolves an interpreter (system python, else uv) and needs no
# dependencies for this path. A hook that fails must not take the session with
# it, so swallow the status: no offer is a worse session, not a broken one.
"$REPO/install.sh" --cloud-offer 2>/dev/null || exit 0
