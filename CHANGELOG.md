# Changelog

All notable changes to this repository are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A `review-loop` skill that drives a pull request through repeated automated
  review rounds until every active review surface reports no findings. The
  loop's whole job is telling a clean verdict apart from a review that stalled
  mid-run or was skipped in fifteen seconds — three states that show the same
  green check — so it classifies each round on a verdict the reviewer posted
  rather than on CI status, carries a prior verdict forward only when the
  patch hash, the base revision, and an explicit prior verdict all agree, and
  stops at a round cap without ever merging.
  Surfaces, the deterministic gate, and the local verification command are
  discovered per repository. `references/traps.md` records ten traps — eight
  that produce a green check while reviewing nothing, plus two that break the
  loop's own recovery and waiting machinery — and `scripts/round_status.py`
  applies the verdict-correlation rules so each round does not re-derive
  them: matching a review to both the current head and the surface that wrote
  it, and reading findings by review id rather than by head.

- The dashboard lists `matt-skills` as an external tool row. Selecting it
  unfolds the installed skills that ship `disable-model-invocation`, each
  toggleable between hidden and model-visible; choices are recorded in
  `.skills-model-invocation.json` and re-applied after an update, so a
  refresh cannot silently re-hide a skill the user enabled. External-tool
  presence is probed by a per-tool marker directory, because one install can
  drop a dozen directories under names that differ from the row's.
- A `GLOBAL INSTRUCTIONS` row in the dashboard, so the user-level
  `~/.agents/AGENTS.md` + `~/.claude/CLAUDE.md` files are installable from
  the TUI and not only via `--global-instructions`. The row is diffed and
  backed up like a skill: its pill compares both managed files against what
  the currently chosen copy/link mode would write — flipping the mode can
  honestly flip the pill, because installing in the other mode really would
  replace the files — replacement goes through the same confirm-and-backup
  flow, and the review step lists each target file with its
  `.skills-backups` destination. The write itself still runs through
  `install.install_global_instructions`.

- A cloud default that installs nothing. `install.sh --cloud-bootstrap`
  registers a user-scope `SessionStart` hook
  (`scripts/cloud-session-start.sh`) and stops, so a cloud environment's setup
  script is three lines that never need editing again. On a session where none
  of these skills are installed, the hook puts the catalog and the exact
  install commands into the agent's context and tells it to ask before
  installing anything. A setup script runs before anyone is present to consult,
  so every skill set it hard-codes is one chosen on the user's behalf and
  re-chosen by hand in a web UI field whenever it should change; moving the
  decision into the session puts it where somebody can actually answer.
  The offer stays silent once any bundled skill is installed, silent when
  `~/.claude/.skills-cloud-declined` exists — declining has to outlive the
  session that declined — and silent for a whole environment on
  `AGENT_SKILLS_CLOUD_OFFER=off`. It lists graphify and mattpocock/skills with
  their prerequisites, and names the `code-review` collision with Claude's
  built-in. Registering the hook merges into existing settings and never
  rewrites a `settings.json` it cannot parse.
- The offer's "everything suggested" command is generated from
  `global_default`, naming each skill explicitly rather than pointing at
  `--non-interactive`. That flag means *every* bundled skill, so suggesting it
  would machine-wide install exactly the narrow skills the flag marks as not
  wanting that — which is how the previous cloud setup script had come to
  install `wow-addon-dev` into every session. Generating the command from the
  flag keeps the two from drifting.

- `viz-driven-dev`, a skill carrying the hypothesis-first visualization
  workflow that previously lived inline in `global/AGENTS.md`. The global
  instructions keep a short pointer, so every session stops paying for
  guidance that only feature work needs.
- `validate_repo.py` warns when a `SKILL.md` passes 150 lines or its
  description lacks "Use when" trigger phrasing. Warnings do not fail the
  run; they encode the skill conventions instead of documenting them in
  prose.

- `global/AGENTS.md` holds user-level instructions that apply to every project,
  installable with `install.sh --global-instructions` or by setting
  `AGENT_GLOBAL_INSTRUCTIONS` for the sync script. Both are opt-in. The default
  `link` mode writes pointer files chaining `~/.claude/CLAUDE.md` ->
  `~/.agents/AGENTS.md` -> this checkout, so the repository stays the single
  source of truth; `copy` writes the text into `~/.agents/AGENTS.md` for agents
  that do not resolve `@path` imports. Existing files are backed up first.

- The dashboard groups its rows under `YOUR SKILLS` and `EXTERNAL TOOLS`, and
  graphify is now selectable and installable from that second group instead of
  only through the `--graphify` flag. The split is behavioural, not cosmetic:
  an external tool follows `--scope` but ignores copy/link because its own
  installer decides the shape, reports `PRESENT` rather than `UP TO DATE`
  because there is no source here to diff it against, and offers `update`
  rather than `skip` when present, since re-running an external installer
  upgrades. The review screen names what it cannot account for — an external
  tool's writes are neither counted nor backed up by this collection. Register
  a tool in `install.EXTERNAL_TOOLS` and wire it in
  `SkillsApp.external_installers`; a test pins the two together so a registry
  entry with nothing behind it fails in CI rather than at install time.

### Changed

- `--matt-skills` fetches `mattpocock/skills` with git instead of shelling out
  to `npx skills@latest`. The upstream CLI only copied files — a checkout and
  its staged output are byte-identical — so the transport swap changes nothing
  about what lands on disk, while `git` replaces Node.js 18+ as the one
  requirement for that path. The revision is pinned by `MATT_SKILLS_REF` rather
  than always taking `main`, so two installs a week apart match, an update is a
  reviewed commit, and `git diff` between two refs shows what an update would
  change. `MATT_SKILLS_COMMIT` records the commit behind that tag, so a
  force-moved tag upstream stops the install instead of silently changing what
  lands. The new `--matt-ref` takes a tag, a branch, or a commit SHA
  (`--matt-ref main` restores the old track-upstream behavior) and refuses an
  empty value rather than falling back to the pin; every install prints the ref
  and the commit it resolved to. The disposable checkout takes no line-ending
  conversion and none of the user's git hooks — `core.autocrlf` would install
  different bytes on Windows than everywhere else, and a `post-checkout` hook
  inherited through `init.templateDir` or `core.hooksPath` runs before the copy
  and can edit files the commit check would still call correct — and the
  install confirms the checkout still matches the commit before copying
  anything. That confirmation is asked twice: `git status`, and a raw-byte
  comparison against the blobs the commit records, because a `.gitattributes`
  in the fetched revision can set `eol`, outrank the config the checkout
  passes, and leave a rewritten tree that git still reports as clean. The
  fetch also runs with `GIT_TERMINAL_PROMPT=0` and `GIT_ASKPASS=echo`, so a
  `401` fails immediately instead of waiting on a password nobody is there to
  type. Discovery walks the checkout for `SKILL.md`
  instead of assuming upstream's directory depth, skips the top-level
  `skills/deprecated/` category, and stops on a name claimed by two categories.
  The per-agent staging mapping is gone: the skills carry no agent-specific
  content, so every selected root gets the same files.
- `semantic-pr-review`'s entrypoint dropped from 212 to about 120 lines. Build
  commands and the browser verification procedure moved to a new
  `references/build-and-verify.md`, and prose that duplicated the other
  references now points at them instead, so the entrypoint is a router rather
  than a second copy.
- The repo `AGENTS.md` and `global/AGENTS.md` are trimmed to purpose, gotchas,
  and pointers; structure an agent can discover by listing files is no longer
  restated.
- `semantic-pr-review` explorers are dark-only, using Catppuccin Mocha for
  every excerpt so a preview reads identically for every viewer instead of
  shifting with the reader's system theme.
- `scaffold_pr_explorer.py` gained `--check`, which reports every model
  violation at once and writes no artifact, and now rejects previews over 12
  lines or 110 characters wide rather than treating those limits as advice.
  `--source-ref` defaults to `pr.evidence_sha` when present, falling back to
  `pr.head_sha`, so a model analyzed against a snapshot other than the PR head
  still validates.

### Fixed

- A skill with no `agents/openai.yaml` describes itself in the dashboard and the
  cloud offer instead of reading "Bundled in this collection." `skill_summary`
  falls back to the SKILL.md frontmatter `description`, cut at its first clause:
  a description is written for matching, so it states the gist, then a dash, then
  everything the gist glossed over, and its first *sentence* runs to 250
  characters for one bundled skill. `viz-driven-dev` ships no interface file and
  was the skill with nothing to show.
- `./install.sh --setup-path` writes the `skills` launcher, so the command can
  be bootstrapped on a machine that does not have it. The documented route was
  `skills setup-path`, which is circular — `setup-path` is what creates
  `skills` — and nothing else wrote the shim, so on a fresh clone the command
  was unreachable and every attempt ended in `command not found`. The installer
  is always present in a checkout, so it is the one thing that can break the
  loop; it delegates to the same code, and `skills setup-path` remains correct
  once the command exists. A successful install now also names the command when
  the shim is missing, rather than leaving the gap to be discovered later.
- `--setup-path` honours `--home`, deriving the shim directory the same way
  `DEFAULT_BIN` does instead of reading the real home at import time. Every
  other path already isolated on that flag, so a test of this one could only
  describe the machine it ran on: it passed on a fresh checkout and failed on
  any machine that had actually run `--setup-path`, which is the inverse of a
  useful signal.
- The Windows leg of CI is green again. Two test harnesses, not the installer,
  were platform-bound: a `#!/bin/sh` stand-in for `uv` cannot be executed by
  `CreateProcess`, which has no shebang support, so it is written as a `.cmd`
  there; and a hand-written launcher shim omitted `skills.cmd`, the only name a
  `shutil.which` matching on `PATHEXT` can find, so it now calls `write_shims`
  rather than keeping a copy that has to remember.
- The `sync-agent-skills.sh` tests are skipped on Windows, with the reason
  stated. `AGENT_SKILLS_DEST` is colon-separated, so an absolute Windows path
  cannot survive it — `C:\Users\x` splits into a root of `C` plus a remainder,
  and the run deposits a stray `./C` tree in the working directory, which is the
  repository when the suite runs from a checkout. That is a real limit of the
  POSIX script rather than something a test can pass its way around; the script
  is the POSIX and cloud entry point, and Windows installs through `install.ps1`,
  which CI covers in its own job.

- Installing or updating graphify no longer leaves its instruction block
  appended to pointer files this repository manages. `install_graphify` strips
  a trailing `# graphify` section from `~/.claude/CLAUDE.md` and
  `~/.agents/AGENTS.md` when the managed chain to `global/AGENTS.md` already
  carries the registration, so the same instructions stop loading twice into
  every session. Only a trailing block is touched, and only while the
  instructions stay reachable; the section `copy` mode inlines mid-file is
  left alone.

## [9.0.0] - 2026-08-05

### Added

- A `skills` command that works from any directory. `skills setup-path` writes
  launcher shims into a directory on `PATH` — a POSIX shim for Git Bash, WSL,
  and Unix shells, plus a `.cmd` shim for PowerShell and cmd.exe — each
  remembering where this checkout lives. `skills install NAME` then installs
  into the current project's `./.agents/skills` and `./.claude/skills` without
  naming a path. `--add-path` adds the directory to `PATH` for you: on Windows
  by editing the current user's registry environment, never `setx`, which
  silently truncates a `PATH` longer than 1024 characters.
- A Textual interface replaces the prompt-driven wizard, in one shell with two
  modes. The dashboard lists every skill with its live state — not installed,
  up to date, or differing from this checkout — beside a sidebar carrying the
  view filter, destination, and copy/link mode. A first install into a
  destination with no receipt instead opens a four-step guided flow (where,
  which, how, review) that explains what a repo-level install means and spells
  out every write and backup before touching disk. `G` switches modes;
  `skills install --guided` / `--no-guided` forces either.
- Colour now carries meaning rather than decoration, and the contract holds
  across both modes: mauve is your selection, blue an additive install, peach a
  replacement whose old copy is backed up, green means already identical, teal
  is a location, yellow an advisory, and red is reserved for failure — so a
  healthy run is provably red-free. A skill's state is painted in the colour of
  the consequence of selecting it, so the hue carries from the state pill to
  the action verb to the review screen.

### Changed

- **Breaking.** `textual` is now a dependency. `uv` provisions it from the
  lockfile automatically; a bare-Python run without it can still install
  anything by naming it (`--skill NAME`), and says so rather than failing with
  a traceback.
- **Breaking.** `--no-color` is gone. It configured the hand-rolled terminal UI,
  which no longer exists; the dashboard follows Textual's own theming.
- The two-phase global/project selection is gone with the wizard. The dashboard
  installs one scope at a time and switches between them with a keypress, which
  is the same reach in fewer concepts.
- `--interactive` and `--non-interactive` now open and suppress the dashboard.
  `--graphify`, `--matt-skills`, and `--target` stay scripted-only and say so
  instead of being silently ignored.

### Removed

- The numbered-prompt and arrow-key interface, its Windows virtual-terminal and
  raw-key plumbing, and the two-phase wizard: 666 lines out of `install.py`.

## [8.1.0] - 2026-08-05

### Added

- The guided installer now runs two skill-selection phases instead of asking
  for one scope. Phase one picks machine-wide skills; phase two is an opt-in
  project install that marks anything already chosen globally as `already
  global` and leaves it unchecked, since a project copy of an already-global
  skill is redundant. Either phase accepts `none`, so global-only and
  project-only installs are both normal, and one run can populate both scopes.
- Skills can declare `global_default: false` in `agents/openai.yaml` to be
  listed without being pre-selected for a machine-wide install. `wow-addon-dev`
  uses it: a narrow, domain-specific skill should not reach every unrelated
  session just because the wizard's defaults were accepted.
- `wow-addon-dev` ships `agents/openai.yaml`, so the wizard shows a real
  one-line summary instead of the generic `Bundled in this collection.`

### Changed

- `--scope` is now a scripted-install control only. The wizard no longer asks
  it, because a single run can install into both scopes.

### Fixed

- A bare `./install.sh` with no usable terminal no longer installs everything
  silently. It skipped the wizard and fell through to "every skill into every
  root", which made exactly the choices the wizard exists to collect --
  including a machine-wide install of a skill marked `global_default: false`.
  It now exits with an actionable error. This is reachable in practice: a pty
  shell such as Git Bash on Windows hides the terminal from Python, so the
  wizard cannot start there. Explicit runs are unchanged, and
  `--non-interactive` still accepts every default.
- The wizard says when a terminal cannot provide arrow-key selection instead of
  silently serving numbered prompts. Selection is checkbox-based -- Space
  toggles, Enter confirms -- but a pty shell falls back to numbers, and nothing
  distinguished "your terminal is limited" from "this is the interface".
- Continuation rows in the review summary keep their alignment. A row with an
  empty label padded the value with leading spaces, which `textwrap` strips, so
  extra destination paths rendered flush against the left margin instead of
  under the value column.

## [8.0.0] - 2026-08-05

### Added

- New `wow-addon-dev` skill covering retail World of Warcraft addon
  development: TOC manifests and load order, the event and widget model,
  SavedVariables, taint and secure templates, the Midnight-era secret-value
  restrictions on combat data, the library ecosystem, performance discipline,
  and BigWigs-packager publishing. Ships a copyable addon skeleton under
  `assets/skeleton/` and a `scripts/check_toc.py` manifest validator.
- `semantic-pr-review` marks every node the PR changed with a corner delta,
  so the change footprint reads at a glance in the full request path and not
  only in the PR delta view. The mark is a shape in the existing muted text
  color rather than a second color channel, and context nodes stay unmarked.

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
- The guided installer no longer offers to download third-party skills. The
  `mattpocock/skills` prompt existed because Olympus orchestration required
  those workflows; with that skill removed, nothing bundled here depends on
  them, so they are installed only via an explicit `--matt-skills`.

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
  confirmation the scripted input never answered, so those tests failed on some
  machines and passed on others. Each test now supplies a temporary home.
- The backup confirmation is now covered deliberately, for both the accept and
  decline paths and for one and several differing paths, instead of being
  reached by accident through ambient state.
- The backup warning agrees in number: one differing path reads `1 installed
  skill path differs`, not `1 installed skill path differ`.

### Removed

- Removed the `orchestrate-olympus` skill and everything that existed to serve
  it: the skill directory (`SKILL.md`, 16 references, `agents/openai.yaml`, and
  `scripts/checkpoint.py`), its nine dedicated test modules, the installer's
  Olympus prerequisite step, and the Olympus framing in the README and
  `docs/matt-pocock-skills.md`. The full contract and its history remain
  recoverable from Git. This supersedes the earlier removal of the Graphify
  lifecycle from that skill; the repository's separate opt-in Graphify
  installer is unaffected.

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
