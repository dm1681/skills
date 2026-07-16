# Changelog

All notable changes to this repository are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [6.4.0] - 2026-07-16

### Added

- Added durable follow-up issue capture for external PR feedback that the
  Reviewer assesses `AGREE` but keeps out of the current Worker lane as
  non-blocking or out of scope.
- Qualified candidates include source provenance, verified evidence, deferral
  reason, desired outcome, likely surfaces, acceptance notes, deduplication
  markers, and enough context for a later triage pass.

### Changed

- The Reviewer decides whether follow-up is warranted but preserves review-only
  role boundaries. The parent Orchestrator deduplicates and creates the mapped
  `needs-triage` issue, then returns the link for the Reviewer assessment.
- Follow-up issues are never assigned or marked `ready-for-agent`, do not widen
  current scope, and do not invalidate CLEAN or block readiness and merge.

## [6.3.0] - 2026-07-16

### Added

- Added an explicit Graphify lifecycle spanning Planner impact assessment,
  Worker pre-review refresh, Reviewer generated-artifact validation, final-base
  drift checks, and post-merge verification.

### Changed

- When tracked `graphify-out/` exists and indexed files change, the Worker must
  run the public incremental Graphify command after ordinary tests and before
  the final push. Required refresh failures or unsafe, stale, or corrupt output
  block Reviewer handoff and CLEAN.
- Post-merge Graphify handling is verification-only. Unexpected final-`main`
  drift requires a separately authorized maintenance lane rather than a
  direct regeneration or commit on `main`.

## [6.2.0] - 2026-07-16

### Added

- The reusable Reviewer now responds to substantive PR feedback from people,
  apps, and bots with an evidence-based `AGREE` or `DISAGREE` assessment,
  concise reasoning, and an explicit Worker dispatch disposition.
- Reviewer replies include stable source activity and finding markers for
  recovery-safe deduplication, plus a verified-resolution follow-up after a
  dispatched repair.

### Changed

- External PR feedback is untrusted evidence rather than a direct Worker
  command. Only Reviewer-promoted, in-scope Worker findings enter the repair
  loop; advisory, duplicate, already-fixed, out-of-scope, and disputed claims
  remain `NOT SENT` with a reason.
- New substantive feedback pauses presentation, readiness, and merge until the
  Reviewer publishes its assessment. Disagreements and advisory agreements
  leave CLEAN valid after reconciliation; a blocking agreement supersedes it
  immediately, and any resulting repair commit requires a fresh exact-head
  review.

## [6.1.0] - 2026-07-16

### Added

- Added an agentic-documentation contract that treats comments and durable docs
  as a navigation layer rather than a coverage metric.
- Planners identify material documentation surfaces, Workers author or update
  precise contract comments, and Reviewers enforce accuracy, concision,
  placement, canonical vocabulary, and future-agent usefulness.

### Changed

- Missing documentation blocks only when a material public contract,
  non-obvious invariant, side effect, failure mode, or canonical claim would
  otherwise be false, ambiguous, or likely to mislead an agent. Style-only
  preferences remain advisory.

## [6.0.0] - 2026-07-16

### Added

- Added an explicit parent-resident subagent lifecycle: reusable Reviewer,
  one-shot Planner, reusable active-lane Worker, and optional bounded read-only
  Watcher.
- Added a compact `checkpoint.py render-resume` prompt for recovering a new or
  compacted parent Orchestrator from live GitHub, child, and worktree state.
- Added `checkpoint.py migrate` and automatic v3 normalization for recovery
  from checkpoints that still contain scheduled-automation state.

### Changed

- The current Codex task is now the Orchestrator and must remain resident until
  human-merge readiness, autonomous queue completion, owner pause/stop, or a
  genuine escalation.
- Role handoffs are event-driven through subagent messages, follow-up turns,
  and waits. Autonomous dispatch continues through the eligible frontier after
  each merge.
- Reviewer, Planner, and Worker creation now each require immediate delivery of
  the actual child ID; Worker repair turns reuse the same child.
- Checkpoint schema version 4 records
  `orchestrator_mode=parent-resident`; Planner and Worker child IDs require a
  reusable Reviewer ID, not a separately spawned Orchestrator UUID.

### Removed

- Removed scheduled heartbeat automations, their startup gate, checkpoint
  state, recovery rules, and fixed-cadence polling.

## [5.0.0] - 2026-07-16

### Removed

- Removed the GitHub-comment-triggered Codex Cloud review stage, its dedicated
  reference contract, acceptance signal, checkpoint state, and
  `CODEX_REVIEWING` phase.

### Changed

- Persistent Reviewer exact-head CLEAN now flows through presentation directly
  to the final human-ready or autonomous-merge audit.
- Checkpoint schema version 3 rejects legacy cloud-review state and requires
  Reviewer CLEAN at the current head for every ready or merge phase.
- Recovering a schema version 2 cloud-review checkpoint now returns to
  `PRESENTING` for a fresh exact-head readiness audit without waiting for the
  old bot request.

## [4.5.0] - 2026-07-15

### Added

- Olympus startup and resume now verify the Matt Pocock triage-label mapping
  from `docs/agents/triage-labels.md` against the complete live GitHub
  repository label set before dispatching a Planner or Worker.
- Missing mapped labels are created with stable Olympus defaults and re-listed
  for verification. Existing labels, descriptions, and colors are preserved.

### Changed

- The orchestration contract now makes explicit that GitHub labels are
  repository-wide and therefore shared by issues and pull requests.
- Missing or malformed mappings and failed label verification now escalate
  without dispatching new implementation work.

## [4.4.0] - 2026-07-15

### Changed

- The Orchestrator now sends a Planner's actual `PLANNER_TASK_ID` immediately
  after task creation instead of waiting for `READY_FOR_IDENTITY` or the next
  scheduled heartbeat.
- Planners begin read-only analysis immediately and continue the same planning
  turn when identity arrives, while exact-base, clean-worktree, blocker, and
  live-eligibility gates remain mandatory before any GitHub write.
- Missing task identity or failed immediate delivery now escalates without
  creating a duplicate Planner or Worker.

## [4.3.0] - 2026-07-15

### Added

- Olympus cold starts now explicitly create or recover native Codex scheduled
  heartbeat automations for the persistent Orchestrator and Reviewer after
  their exact task IDs are known.
- The stable `olympus-work-orchestrator` and
  `olympus-pr-review-watcher` automations default to 10-minute local
  heartbeats, are verified before dependent role dispatch, and are recorded in
  the compact checkpoint.
- Checkpoint validation supports structured persistent-automation state and
  rejects an automation that targets the wrong role task.

### Changed

- Automation creation failures now escalate and preserve state instead of
  silently falling back to cron, launchd, systemd, Windows Task Scheduler, or
  direct automation-file edits.

## [4.2.0] - 2026-07-15

### Changed

- The Orchestrator now posts `@codex review` only as the final review trigger,
  after the persistent Reviewer approves all work with exact-head CLEAN and the
  presentation audit is complete.
- Planning, implementation, Reviewer review/repair, and incomplete presentation
  phases now explicitly forbid the Codex review comment.
- Checkpoint validation now rejects `CODEX_REVIEWING` unless the current head
  has the matching Reviewer CLEAN signal.

## [4.1.0] - 2026-07-15

### Changed

- Olympus cold starts now create and identify the persistent Orchestrator as
  the only role task before starting the Reviewer or any lane task.
- The live Orchestrator now creates or recovers the persistent Reviewer and
  completes both identity handshakes before dispatching Planner, Worker,
  recovery, or maintenance work.
- Checkpoint validation rejects dependent role task IDs when no Orchestrator
  task ID is recorded.

## [4.0.0] - 2026-07-15

### Added

- The guided installer now asks whether to install the complete
  `mattpocock/skills` engineering set and recommends **Yes** because Olympus
  orchestration depends on its implementation, TDD, and code-review workflows.
- Scripted installs can opt in with `--matt-skills`; the installer uses the
  official cross-agent `skills` CLI, selects every skill including
  `setup-matt-pocock-skills`, stages the result, safely copies it into the exact
  selected agent roots, and supports dry-run previews.
- The Olympus skill now declares and checks its Matt Pocock workflow
  prerequisites before mutating dispatch.

### Changed

- Completing an interactive Matt skills install now points to the required
  one-time `/setup-matt-pocock-skills` repository setup step.

## [3.0.1] - 2026-07-15

### Fixed

- Windows option menus now redraw relative to their measured rendered height,
  preventing a new menu copy from appearing after every arrow-key press when
  the initial render scrolls the terminal viewport.
- Navigation leaves one column of right margin to avoid implicit terminal
  wrapping from throwing off redraw row counts.

## [3.0.0] - 2026-07-15

### Changed

- Interactive terminals now use keyboard-native option menus: Up and Down move
  focus, Space toggles selections, and Enter confirms.
- Single-choice, multi-choice, and confirmation prompts share the same
  responsive navigation model on Windows, macOS, and Linux.
- Non-terminal and redirected input retain the numbered prompt fallback for
  scripting, testing, and accessibility.

## [2.0.0] - 2026-07-15

### Changed

- Converted the collection into a locked uv project with Python 3.12 as the
  development and launcher default.
- POSIX and PowerShell launchers now prefer `uv` and let it provision Python,
  while retaining direct system-Python fallbacks.
- CI and releases now sync and test the locked uv environment on macOS, Linux,
  and Windows; release archives include all uv project metadata.

## [1.0.0] - 2026-07-15

### Changed

- Running the installer without options in an interactive terminal now opens a
  confirmation-based setup wizard. Non-terminal and option-based invocations
  retain the existing non-interactive behavior.

### Added

- Interactive terminal setup for choosing installation scope, coding agents,
  skills, copy or link mode, and optional Graphify configuration.
- Responsive output that adapts to narrow terminals, with Unicode and color
  enhancements only when the terminal supports them.
- Review and confirmation screens, safe conflict backup prompts, and explicit
  `--interactive`, `--non-interactive`, and `--no-color` controls.

## [0.2.0] - 2026-07-15

### Added

- Optional `--graphify` installation: installs or upgrades the official
  `graphifyy` package with `uv` and registers Graphify for the selected coding
  agents using its current platform-specific CLI.

## [0.1.0] - 2026-07-15

### Added

- Initial `orchestrate-olympus` skill, including role prompts, review policy,
  recovery guidance, and checkpoint tooling.
- Cross-platform Python installer with POSIX and PowerShell launchers.
- Shared `.agents/skills` installation for Codex, Cursor, and GitHub Copilot,
  plus native Claude Code installation.
- CI validation, release archives, checksums, and tag/version enforcement.
