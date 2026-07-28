# Changelog

All notable changes to this repository are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `semantic-pr-review` marks every node the PR changed with a corner delta,
  so the change footprint reads at a glance in the full request path and not
  only in the PR delta view. The mark is a shape in the existing muted text
  color rather than a second color channel, and context nodes stay unmarked.
- Added `references/host-adaptation.md` to `orchestrate-olympus`, defining the
  required host capabilities, the stable-identifier rule for task and subagent
  IDs, and explicit fallbacks for missing host features such as pinning,
  follow-up turns, parallel child slots, bounded waits, and archiving.

### Changed

- `semantic-pr-review` no longer fails a whole explorer over unusable editor
  links. A `--cursor-root` that is a remote path, sits at a different `HEAD`,
  or holds drifted bytes now omits the affected links with a warning naming
  the reason, and the explorer still builds against its immutable GitHub
  links. A link is still never emitted for a file the scaffold cannot match
  byte for byte, so the guarantee is unchanged — only the failure mode is.
  Each notice travels in the model and renders on the page itself, because
  the person reading the explorer is rarely the operator who ran the
  scaffold and would otherwise never learn that links were dropped.
- `--agent` now defaults to `all`, so a plain `./install.sh` or a bare
  `--skill NAME` installs into every skill root instead of the shared
  `.agents/skills` directory alone. The previous default silently produced an
  install that Claude Code could not see, because Claude reads `.claude/skills`
  and never `.agents/skills`. Narrowing with an explicit `--agent` is unchanged,
  and the guided installer now pre-selects every root. Because the optional
  third-party steps follow the same selection, a bare `--matt-skills` now
  installs for both `codex` and `claude-code`, and a bare `--graphify`
  registers both the `agents` and `claude` platforms.
- `install.py` refuses a `--mode` change instead of reporting it current. An
  existing destination now has to match the requested mode, not merely hold
  equal contents, so converting a copy to a link no longer requires deleting
  the destination by hand. Refusals name the shape found.
- Made the `orchestrate-olympus` contract host-neutral. The normative
  documents now describe the parent agent session, host tasks, subagents, and
  hosted cloud reviews instead of Codex-specific features; Codex remains a
  named example only in the host-adaptation reference, the OpenAI interface
  file, and legacy checkpoint-schema history.
- `scripts/checkpoint.py` now accepts any stable whitespace-free host task
  identifier (4–128 characters) instead of requiring a Codex-style UUID, and
  renders the recovery prompt with a host-neutral skill invocation.

### Fixed

- The `semantic-pr-review` explorer now shows which node is selected.
  Selecting a node, or stepping with Previous and Next, set `aria-pressed`
  but matched no style rule, so the flowchart never moved: only the detail
  card and the step counter changed, and a viewer stepping through the path
  saw nothing happen. The selected node now takes the lane's color as an
  outline and a lifted background. The outline avoids widening the border,
  so selection cannot reflow the lane.
- `semantic-pr-review` editor deep links now form parseable URLs on Windows.
  `scaffold_pr_explorer.py` concatenated `cursor://file` with a native
  absolute path. A POSIX path opens with the separator the URL needs, but a
  Windows path opens at its drive letter, so the result was
  `cursor://fileC:\...`: Chromium parsed its protocol as `:` rather than
  `cursor:`, `new URL()` rejected it, clicking the link opened
  `about:blank#blocked`, and `verify_pr_explorer.py` failed every node with
  `invalid Cursor URL`. Links are now built from `Path.as_posix()` with an
  explicit leading separator (`cursor://file/C:/...`), and the verifier maps
  that form back to the on-disk drive path when it checks worktree bytes.
  Because the defect could not reproduce on a POSIX host, the regression
  coverage includes a host-independent unit test that drives the URL builder
  with a `PureWindowsPath`.
- Guided-installer tests no longer read the developer's real home directory.
  Three wizard tests parsed an empty argument list, so `--home` fell back to
  `Path.home()` and the wizard inspected whatever was already installed there.
  A pre-existing install that differed from the checkout added a backup
  confirmation the scripted input never answered, so
  `test_declining_matt_skills_warns_that_olympus_is_incomplete` failed on some
  machines and passed on others. Each test now supplies a temporary home.
- The backup confirmation is now covered deliberately, for both the accept and
  decline paths and for one and several differing paths, instead of being
  reached by accident through ambient state.
- The backup warning agrees in number: one differing path reads `1 installed
  skill path differs`, not `1 installed skill path differ`.

### Removed

- Removed the Graphify lifecycle from `orchestrate-olympus`, including its
  role gates, checkpoint state, and dedicated reference. The repository's
  separate opt-in Graphify installer remains available.

## [7.1.0] - 2026-07-26

### Added

- Added the `semantic-pr-review` skill. It pins a pull request's immutable head
  SHA, derives semantic layers from responsibilities rather than directories,
  records DTO-labeled runtime handoffs, and builds a self-contained interactive
  explorer through bundled scaffold, render, and strict verification scripts.
- Added packaging and pipeline tests for the new skill covering entrypoint
  routing, install-location portability, standard-library-only scripts, a full
  scaffold/render/verify pass against a Git snapshot, and the fail-closed paths
  for hand-edited previews, mismatched models, and drifting editor worktrees.
- Added installer coverage for multi-skill collections: every bundled skill is
  installed by default, `--skill` still installs exactly one, and `--list`
  reports the full bundled set.

### Changed

- The guided installer now shows the skill selection screen whenever more than
  one skill is bundled and labels each option with that skill's own
  `agents/openai.yaml` short description instead of a generic line.
- The Olympus prerequisite screen is offered only when `orchestrate-olympus` is
  part of the selection, so installing `semantic-pr-review` alone no longer
  proposes an unrelated third-party download.
- `README.md` documents both skills, the new per-skill install example, and the
  snapshot-verification boundary for PR explorers.

## [7.0.0] - 2026-07-16

### Added

- Added source, evidence, artifact, and final Reviewer phases so independent
  Standards and Spec review completes before screenshots and Graphify work.
- Added source-tree and runtime fingerprints, separate Standards and Spec
  certificates, required aggregate-test evidence, exact-head artifact review,
  Graphify refresh markers and dispositions, and exact-head Actions evidence.
- Added one-shot read-only source-review agents, per-worktree runtime bootstrap,
  repository-supported test-output isolation, and mandatory-agent slot priority
  over optional CI Watchers.
- Added a bounded GitHub Actions `5xx` degradation path for one initial WIP
  push and PR publication. Successful exact-head Actions evidence remains
  mandatory before Reviewer CLEAN, readiness, or merge.

### Changed

- Deterministic artifact-only commits may reuse product tests and source-review
  certificates only when source-tree hash, runtime fingerprint, scope, and
  required aggregate evidence still match. Every commit still invalidates the
  final exact-head Reviewer CLEAN.
- Graphify now refreshes once per reviewed source-tree hash and records a
  version, command, and output marker. Generated-output commits do not trigger
  a duplicate refresh when the marker still matches.
- Mechanical evidence metadata receives a narrow provenance-only classification
  only when it cannot alter acceptance meaning and is outside Graphify's
  semantic corpus. Section-level Markdown preservation is explicitly left to
  upstream Graphify public tooling.
- Checkpoint schema v5 replaces the combined source-review state with separate
  Standards and Spec evidence. Migrating a legacy CLEAN/ready checkpoint
  conservatively returns it to `REVIEWING` until the new gates are rebuilt.

## [6.5.0] - 2026-07-16

### Added

- Added separate Graphify structural and presentation freshness dispositions.
  Eligible code-only PRs use `graphify update . --no-cluster`; semantic and
  material architecture changes continue to require the full public refresh.
- Added safe worktree cache seeding rules keyed to the same repository, exact
  starting SHA, and Graphify version. Mutable graph and presentation outputs
  are never shared across branches.

### Changed

- The Worker suppresses Graphify's post-commit hook for intermediate and
  generated-artifact commits, then runs exactly one synchronous final refresh
  per proposed head instead of duplicating background and explicit rebuilds.
- Deferred report, label, and HTML regeneration is truthful and non-blocking
  only when no acceptance or PR evidence depends on it. Autonomous queues
  close accumulated presentation work in one reviewed maintenance PR.
- `GRAPHIFY_MAX_WORKERS` remains an optional per-command optimization that
  requires repository-local timing and stability evidence; no global override
  is forced, including on Windows.

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
