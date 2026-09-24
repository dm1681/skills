# DIE-32 pending handoff

Issue: [DIE-32](https://linear.app/diego-mcdonald/issue/DIE-32/skills-add-linear-work-tracking-and-handoffs-to-synced-global-agent)

## Local ownership — 2026-09-22

Codex task `01a0cbad-1050-7181-ba27-9f45141eb68a` implemented the shared
Linear guidance in `C:/Users/hbar6/projects/skills`, on `main` at starting HEAD
`d8641f5c793a510addb44a06cb42c7db6bc0af69`. No separate worktree was created.
The issue is Todo with `ready-for-agent`, no assignee, no dependencies and no
comments as read this session; no competing claim was visible.

No Linear project mapping exists for this repository in the retrieved issue
or project list. This is a local ownership record, not a published Linear
claim. No project overview was guessed, and no Linear messages were sent.

## Implementation checkpoint

Added the shared resume/claim/state/decision/handoff workflow to canonical
`global/AGENTS.md`, a repository mapping example in `docs/linear-workflow.md`,
and loading/sync guidance in the root guide, README and support docs. The
installer and installed copies were not edited. Existing local changes are
preserved, including the implement/shadowing work and user-specific global
instructions.

## Verification — 2026-09-22

- `uv run python scripts/validate_repo.py`: passed, 7 skills, version 10.0.1.
- `git diff --check`: passed; 37 local documentation link targets resolved.
- Windows PowerShell `install.ps1`, link and copy modes, isolated temporary
  `--home` values: complete canonical source or resolved source pointer verified,
  Claude import pointer verified, second install reported both files unchanged.
- Git Bash `scripts/sync-agent-skills.sh`, local-source link and copy modes:
  shared source content/pointer and Claude pointer verified. HOME, skill roots
  and both instruction destinations were redirected into temporary homes.
- `uv run python -m unittest discover -s tests`: 499 tests, 490 passed,
  8 skipped, 1 error. The error is Windows `WinError 32` during cleanup of
  `test_a_drifted_worktree_warns_and_omits_editor_links` in
  `tests/test_semantic_pr_review.py`, after its assertions. The suite is not
  clean. Final log: `%TEMP%/skills-die32-tests-final.log`. An earlier run also
  failed the default plugin-status test because the caller forced its status
  environment off; the normal-environment rerun removed that failure.

Read-only inspection found this device's shared/Claude pointer chain points
to this checkout; `C:/Users/hbar6/.codex/AGENTS.md` is empty. The installer
does not populate Codex's native instruction entry point. The supported-agent
loading gaps and official sources are recorded in `docs/agent-support.md`.
Linear issue/workspace reads succeeded in this Codex session.

Not checked: fresh Claude/Codex/Cursor/Copilot instruction loading, cloud or
remote-clone sync execution, or other devices. No credentials, installed
instruction files, connector configuration or bulk rollout were changed.
No code changed, so no AST graph update was required.

## State and next action

Implementation is local and uncommitted; HEAD remains the starting commit.
This task changed `global/AGENTS.md`, root `AGENTS.md`, `CHANGELOG.md`,
`README.md`, `docs/agent-support.md`, `docs/cloud-skills-sync.md`, and added
`docs/linear-workflow.md` and this handoff. Pre-existing edits to root/global
guidance and the changelog remain alongside these additions. Pre-existing
changes in `install.py`, `tests/test_matt_skills.py`,
`docs/matt-pocock-skills.md`, `skills/implement/`, `tests/test_shadowed_skills.py`
and the other untracked files were not part of this implementation.

The local session's ownership is released. Linear remains unchanged; no
published claim or project overview sync is asserted. Missing input for project
sync: a verified repository-to-Linear-project mapping. No such mapping was
needed to complete this documentation change.

Exact next action for the next maintainer: inspect this task's documentation
additions in the working tree, keeping the listed pre-existing edits separate
when staging. Before closing DIE-32, record the acceptance evidence in Linear
when authorized; resolve or explicitly disposition the unrelated Windows test
cleanup error. Commit/release and device rollout remain separate steps.
