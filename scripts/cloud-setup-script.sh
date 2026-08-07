#!/bin/bash
# Cloud environment SETUP SCRIPT.
#
# This is NOT a repo hook and is not run from a checkout. Copy its contents into
# your claude.ai cloud environment's "Setup script" field:
#   claude.ai/code -> cloud icon (environment name) -> gear on the environment
#   -> Setup script. (New environment: "Add environment" dialog has the field.)
#
# It runs once before Claude Code launches in each cloud session (result cached),
# for every repo used in that environment. No files are committed to any repo.
#
# It installs NO skills. It clones the collection and registers a SessionStart
# hook, and the hook asks you what to install once the session is running. That
# is the point: a setup script runs before anyone is present to consult, so
# anything it decides is decided for you and has to be re-decided here every
# time it should change. Choosing in the session instead means this field holds
# three lines that never need editing again, and what you are offered is
# whatever the checkout says today.
#
# Requires the environment's network access to allow cloning GitHub (the default
# "Trusted" level does; "None" blocks it). Safe to re-run.
set -u

SKILLS_DIR=/opt/agent-skills

rm -rf "$SKILLS_DIR"
git clone --depth 1 https://github.com/dm1681/skills "$SKILLS_DIR" || true
"$SKILLS_DIR/install.sh" --cloud-bootstrap || true

exit 0
