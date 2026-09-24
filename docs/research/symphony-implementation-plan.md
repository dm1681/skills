# Symphony integration implementation plan

Prepared 2026-09-23 after resuming the
[accepted WSL handoff](../handoffs/symphony-integration-wsl-2026-09-23.md).
The sequence below records the original plan; the current implementation and
validation boundary is recorded first.
The accepted handoff supersedes conflicting recommendations in the original
[upstream assessment](symphony-upstream-assessment.md).

## Current setup status — September 24, 2026 UTC

**The reviewed integration was published as `17b578f` on main. The user approved
landing by moving DIE-60 to Merging.** A CI portability repair follows that
commit: use the latest remote main, GitHub run and live DIE-60 state as the
completion evidence. Live dispatch still requires a separate explicit action.
Earlier checkpoint statements below are historical.

- WSL uv, gh and Graphify are installed. GitHub CLI is authenticated as dm1681;
  configured Codex login and repository SSH access are verified.
- The user saved the Linear key through hidden terminal input. It is stored at
  `~/.config/symphony/skills-linear-api-key`, mode 0600, outside the checkout.
  Its value was not printed, committed or copied from Windows.
- Machine-local credential-loading launcher:
  `python3 .symphony/linear-access.py check`. It loads the key into the service
  environment. `start --accept-preview` remains a separate explicit action.
- Authenticated readback verified exact DIE-60 UUID/project UUID/slug and all
  seven required lifecycle states. Created only the missing states:
  Human Review (`c68d6359-171c-4cd0-9349-38ff593b0f4c`),
  Merging (`d3b3a8af-03bd-481c-9517-342945dd9bac`),
  Rework (`ffe9d799-c704-4d9e-945c-d1eb97d61877`).
  Existing states, including In Review, and issue placements were preserved.
- Updated both existing native templates via the live public API. Exact payload
  readback verified the prepared descriptions and preserved unrelated metadata,
  assignees and Backlog defaults. Master playbook is now version 1.4.
  [Template evidence](../templates/README.md). Existing DIE-58/DIE-59 were not
  changed; their separate scopes and authorization remain authoritative.
- Before acceptance, no-dispatch readiness returned 3 solely because DIE-60 was
  not Done. Rerun it after the issue is completed; setup/check never dispatch.
- Initial remote CI for `17b578f` passed Linux and launcher jobs but failed
  macOS/Windows. macOS exposed a noncanonical test path; Windows exposed both
  path-separator assumptions and newline translation making generated-file
  hashes disagree with the written bytes. No prior Windows cleanup error recurred.
- The CI repair writes generated workflow bytes without host newline conversion
  and corrects path assertions. A regression reproduced the hash failure on Linux
  before the fix. Required local validation passed: 17 skills; 526 tests,
  525 passed and one Windows-only skip. Log:
  `/tmp/skills-symphony-ci-fix-tests.log`. Remote CI must verify the repaired head.
- Graphify AST update succeeded with the existing .toc partial-parse warning.
  Real sandbox enforcement, exact skill discovery and app-server command execution
  passed on the fixed project-local Codex. No live model-worker trial, native
  Windows Symphony support or other-device instruction loading is claimed.

### Precommit review — September 24, 2026 UTC

Reviewed the complete tracked/untracked integration against base
`d8641f5c793a510addb44a06cb42c7db6bc0af69`. The code-review skill's independent
Standards and Spec passes found two and three actionable findings respectively;
all were fixed and both reviewers confirmed no remaining blockers. Runtime
inspection found and fixed one additional configuration-validation gap.

- Curated migration now respects pre-manifest ownership and checks copy/link
  mode before writing any root. Regression tests cover both failure boundaries.
- Loading editable configuration validates field types, absolute runtime paths,
  the protected workspace-root boundary, the supported revision and symlinks.
- New workspaces create an issue branch from the configured base instead of
  staying on the remote default branch. The clone regression uses a non-default
  base and verifies both its content and the resulting issue branch.
- Delivery instructions handle unpublished branches, optional PR templates,
  noninteractive PR creation and the human review flow without requiring a bot.
- Locked environment sync, validator and full tests passed. Authenticated
  readiness still returns 3 only because DIE-60 awaits human acceptance/Done.
  No production worker was dispatched. No commit, push or release was made.
- DIE-60 was moved to Human Review and its actual state/evidence read back.
  82 reviewed files are staged; credentials, local runtime and generated graph
  remain excluded. Commit/push and remote-clone delivery remain outstanding;
  do not claim a fresh-session or live model-worker trial.
- Graphify AST refresh completed (2382 nodes, 4020 edges), retaining only the
  existing WoW .toc partial-parse warning. Local and remote main still resolve
  to the reviewed base. The prepared commit message is at
  `/tmp/skills-symphony-commit-message.txt`.

### Status-rule follow-up — prior checkpoint

DIE-60 is verified In Progress. Corrected the ambiguous setup instructions:
status updates now belong to pickup, meaningful checkpoints and substantive
completion, and every mutation requires a fresh issue readback. "Keep incomplete"
means no premature Done, not Backlog. Review-ready setup uses Human Review;
worker Backlog routing, Merging/Rework handling and completion bars remain intact.

Updated canonical `global/AGENTS.md`, the repository mapping, lifecycle docs,
worker prompt and both native templates. Master playbook is version 1.4 and
explicitly allows the mapped setup issue's status/evidence updates while keeping
unrelated Linear/workspace writes out of ordinary setup. Refreshed the managed
pilot workflow without dispatch. Native template API readbacks matched exactly.

Validation: 17-skill validator and 38 relevant existing tests passed (17 global
instruction tests plus 21 Symphony tests). These are instruction changes, not a
hard runtime guarantee. Shared guidance still needs commit/sync and verified
fresh-session loading before claiming delivery to other devices/remote clones;
root guidance covers future sessions in this checkout, and new template-based
issues receive the updated text immediately. Existing copied issues do not.

## Exact next action and gates

1. Verify the latest local/remote main match and all CI jobs pass for that exact
   commit. The CI portability repair follows the original `17b578f` integration.
2. Read DIE-60's live state/evidence. The user's Merging transition is recorded
   approval; after successful landing checks, mark Done if still Merging and
   reread the issue. Preserve any intervening human state change. Rerun the
   credential-loading readiness command above and record its result on DIE-60.
3. Obtain a separate explicit start instruction before a bounded supervised
   issue trial. Setup is complete, but no worker has been dispatched and no
   unattended execution outcome has been validated.
4. The running desktop's older bundled backend and Computer Use WSL initialization
   remain separate app issues. The Symphony pilot uses its verified fixed runtime
   and completed Linear changes through the API; do not replace the active app's
   binary or weaken its sandbox as part of pilot setup.

## Earlier implementation evidence — historical

**Implemented locally; not ready for a live pilot.** Work remains uncommitted on
`main` at `d8641f5c793a510addb44a06cb42c7db6bc0af69`. The Windows source
checkout and unrelated changes were preserved. No commit, push, release,
production tracker dispatch or remote CI run was performed.

The dedicated Linear project is
[Skills — Symphony WSL pilot](https://linear.app/diego-mcdonald/project/skills-symphony-wsl-pilot-f5364fea9e9c)
(project UUID `f1f4e47e-a464-4c93-a545-76ce39b28194`, slug `f5364fea9e9c`).
Its setup issue is
[DIE-60](https://linear.app/diego-mcdonald/issue/DIE-60/set-up-repository-for-harness-engineering)
(UUID `ea6a5458-4a39-41ff-aad4-c7ed65084283`), still incomplete. DIE-32 is
historical shared-instruction work, not the pilot setup gate.

### Remaining setup follow-up — September 23, 2026

Completed WSL user-tool installation on the existing `~/.local/bin` PATH:
uv 0.12.18 (previously verified official binary), GitHub CLI 2.101.0 (official
archive SHA256 `9bca2d1c16825f109907a23307628a2f0698fbf99662b73a5cf0b020293072b8`),
and Graphify 0.9.67 (`uv tool install --python 3.12 graphifyy==0.9.67`).
No global skill registration or hook was added.

Verified the configured Codex is logged in through ChatGPT and SSH repository
access succeeds (`git ls-remote --heads origin main` returned the expected HEAD).
Graphify AST update now succeeds: 2365 nodes, 3999 edges, 183 communities after
the authentication-check change. One existing WoW `.toc` skeleton produces a
partial-parse warning; no model/API labeling or source rewrite was requested.

Online readiness now checks bounded `gh auth status` and `codex login status`
commands and suppresses credential-bearing diagnostics. Tests isolate these
probes from the developer account. Validator: 17 skills with no warnings/errors.
Full suite: 521 tests, 520 passed and one Windows-only test skipped. Log:
`/tmp/skills-symphony-setup-tests.log`. `git diff --check` passes.

Remaining no-dispatch readiness blockers: GitHub CLI browser authorization and
a runtime Linear API key. A standard `gh auth login --web --git-protocol ssh
--skip-ssh-key` device flow was started; do not assume its temporary code remains
valid across sessions. Recheck `gh auth status`; restart login only if needed.
The user was asked for an existing Linear secret file/environment mechanism
(path only, never the key in chat), or whether a new key needs provisioning.
No credential file was copied from Windows or exposed.

Linear still lacks Human Review, Merging and Rework. Native templates still
contain their previous bodies. Computer Use initialization was retried and
failed with the same WSL `sandboxCwd` error. With authorized API credentials,
introspect the live Linear schema, verify permissions, and apply/read back the
prepared state/template changes directly. The old `linear/linear-node-sdk`
repository is archived (2019), so do not use its schema as current authority.
DIE-60 remains incomplete; no live dispatch, commit, push or release occurred.

### Sandbox repair follow-up — September 23, 2026

The **pilot worker sandbox is fixed**. The app-bundled Codex
`0.155.0-alpha.16.3` rejects WSLg's duplicate root mount even with the corrected
command. Official stable Linux Codex `0.156.1` masks that alias inside restricted
execution; no mount or security-policy changes were needed.

Installed only for the pilot at `.symphony/tools/codex-0.156.1/codex`; updated
its `project.json` and retained `project.before-sandbox-fix.json`. Provenance is
beside the executable. Official release archive SHA256:
`aff46539a83aff86e3c62c592bce2c50d95391f9df289afaf03a50c01d14533d`;
executable SHA256:
`0b2e9301d6100dddda3b9d5c80ebaeaa3a2f1962388f2f36f6b96a9f08b1f33f`.
Upstream source tag `rust-v0.156.1` resolves to
`81e8e29b2956dfe9b092c63953a9ed282781e77c`.

Corrected `probe_worker` to use `codex sandbox -- ...`; `sandbox linux` is no
longer the supported CLI form. Real synthetic-fixture checks passed: allowed
workspace write, denied `.git` and sibling writes, hidden WSLg duplicate root
and daemon socket directory, and blocked direct network with the probe policy.
Actual worker skill discovery also passed on the newly selected executable.
A direct app-server `command/exec` probe using Symphony's workspaceWrite policy
also returned `appserver-sandbox-ok` with exit 0. No model turn or live dispatch
occurred. Post-fix validation passed: 17 skills; 519 tests run, 518 passed and the
Windows-only check skipped. Log: `/tmp/skills-symphony-sandbox-fix-tests.log`.

The refreshed pilot readiness check returns 3 only for missing `gh` and absent
`LINEAR_API_KEY`. Team states and the incomplete DIE-60 gate still need completion
once authenticated. Earlier sandbox failures below are historical. This running
desktop app still uses its old bundled backend; changing the pilot executable
has not repaired its tool sandbox or the separate Computer Use initialization.

### Delivered changes

- Ten owned Matt forks plus the existing interactive implement fork, with pinned
  provenance/licenses, upstream shadow protection and ownership-aware migration.
  The curated installer alias installs locally; the broad upstream option is
  retired. Unrelated installed skills and records are preserved.
- One project service shared by CLI, installer and dashboard: setup/check,
  digest-pinned official runtime installation or pinned source build, and a
  separate explicit start. Setup/check do not dispatch or change templates.
- Upstream-derived workflow and delivery skills, explicit worker identity, actual
  Codex discovery enforcement, a normal sandbox probe, exact project/setup-issue
  Done gate, expected lifecycle states, configurable localhost dashboard.
- Repository documentation and release packaging. No version bump/release;
  breaking broad-Matt-option changes are noted under Unreleased.
- Master Linear playbook updated/read back as version 1.2. Native project/issue
  template replacement bodies are in [../templates/README.md](../templates/README.md).
  Application to the native templates remains pending.

### Validation evidence

- Official uv 0.12.18 downloaded/verified in a temporary tool directory;
  `uv sync --locked` created a Linux Python 3.12.14 environment. This supersedes
  the initial inventory below; uv has not been installed permanently on PATH.
- `uv run python scripts/validate_repo.py`: 17 skills, version 10.0.1,
  no warnings/errors.
- `uv run python -m unittest discover -s tests -v`: 519 tests run,
  518 passed and one Windows user-environment check skipped.
- Isolated source copy containing the changes but no original Git metadata,
  .venv or .symphony configuration: locked sync twice, validator and full suite
  passed. Of 519 tests, 517 passed; the Windows check and Git-index executable
  mode check skipped. The latter passed in the real checkout.
- Release file-list staging: scripted installer listing and Symphony setup
  worked with system Python and no Textual dependency; repeated setup was
  identical and created no worker workspaces. Temporary rehearsal tree removed.
- Actual Linux Codex 0.155.0-alpha.16.3 discovery enabled exactly the selected
  eleven skills and disabled the eight other discovered skills. No model turn.
- Official digest-verified Symphony runtime at the accepted source pin executed
  its help command. A disposable local fake-tracker smoke test returned dashboard
  HTTP 200, verified a loopback-only listener, no running agents, two local tracker
  requests and zero production tracker requests. SIGTERM exited 0; temporary
  resources were removed. This is not an end-to-end worker/model trial.
- Pilot `python3 skills_cli.py symphony setup --project-dir .` refreshed the
  managed workflow without dispatch. `python3 skills_cli.py symphony check
  --project-dir .` returned 3 for missing gh, the sandbox mount failure and absent
  LINEAR_API_KEY. Connector access does not provide the runtime API key.
- Graphify update was attempted but the executable is unavailable; no graph is
  present here. Remote CI, native Windows validation, full model-worker
  cancellation/retry behavior and independent-agent onboarding were not run.
  The Cloudflare artifact client was unchanged.

Session-local diagnostic logs (not durable artifacts):
`/tmp/skills-symphony-tests-final.log`,
`/tmp/skills-symphony-isolated-rehearsal.log`,
`/tmp/skills-symphony-runtime-smoke.log`.
The reusable commands and behavior are documented in [../symphony.md](../symphony.md).

### Previous setup gates (superseded by current status)

1. Pilot sandbox and actual worker discovery now pass on the pinned local Codex
   0.156.1. Keep that configured executable. The desktop's separate bundled
   backend needs its own supported update/restart; do not replace its binary
   underneath the active task or change mounts/security policy.
2. Complete the pending GitHub browser authorization and provision the runtime
   LINEAR_API_KEY from an approved secret source. Permanent WSL uv/gh/Graphify,
   Codex login and repository SSH access are now verified. Never paste secrets
   into handoffs. Recheck CLI authentication before continuing.
3. In a working Linear UI session, add/verify the missing Human Review, Merging
   and Rework states without repurposing shared existing states. Last inspected
   team states had In Review, not Human Review. Apply/read back both prepared
   native templates. Computer Use currently fails initialization with
   `sandboxCwd is not a local file URI: file:///home/hbar6/projects/skills`;
   no native-template edit or default-selection change has been performed.
4. Graphify update is now complete. Review the full local change set, retain
   existing user changes, and agree the commit/sync boundary.
   Worker clones use the repository remote: uncommitted local implementation
   is not automatically present in those clones.
5. Rerun no-dispatch readiness, have the human review DIE-60 evidence and finish
   the exact setup issue only when acceptance is satisfied. An incomplete setup
   issue intentionally prevents a successful live startup gate.
6. Only after readiness passes and a separate explicit start instruction:
   perform a bounded supervised single-issue trial. Neither template changes
   nor project setup authorize that start. Record real worker/PR/cleanup evidence
   before claiming unattended readiness.

## Initial resume verification and preserved work

- Active checkout: `/home/hbar6/projects/skills`, branch `main`, HEAD
  `d8641f5c793a510addb44a06cb42c7db6bc0af69`; initially clean.
- Windows source: `/mnt/c/Users/hbar6/projects/skills`, same HEAD.
  Of 72 changed tracked files, 63 are byte-equivalent to HEAD after replacing
  CRLF with LF. Nine have substantive edits. No source files were changed.
- Transferred the nine substantive files: `AGENTS.md`, `CHANGELOG.md`,
  `README.md`, `docs/agent-support.md`, `docs/cloud-skills-sync.md`,
  `docs/matt-pocock-skills.md`, `global/AGENTS.md`, `install.py`, and
  `tests/test_matt_skills.py`.
- Also transferred `docs/linear-workflow.md`, `tests/test_shadowed_skills.py`,
  both files under `skills/implement/`, the two existing handoffs, and all three
  Symphony research documents. Total: 18 files, written with Linux line endings
  only in the destination. Destination content and unchanged source bytes were
  checked with SHA256. Temporary transfer manifest:
  `/tmp/skills-symphony-resume-2026-09-23-transfer.json`.
- Unrelated Windows files, local settings, image and `mp/` remain there.
  No reset, staging, commit, installed-skill edit, or configuration migration.
- This checkout's `AGENTS.md` was read. No `graphify-out/` exists here.
  `/home/hbar6/.agents/AGENTS.md` and `/home/hbar6/.codex/AGENTS.md` are absent;
  there is no verified Linux global instruction chain to assume inherited.
- Sandboxed commands fail before execution with the existing bubblewrap
  `/mnt/wslg/distro` mount error. Approved host execution supports these
  inspections and transfers; it does not validate worker sandboxing.
- PATH provides Python and Codex `0.155.0-alpha.16.3`; `uv`, Node, Graphify,
  Elixir, Mix and Erlang were not found. No dependencies were installed.
- Reconciled baseline checks passed with system Python:
  `python3 scripts/validate_repo.py` (7 skills, version 10.0.1),
  `python3 -m unittest discover -s tests -p test_shadowed_skills.py` (14 tests),
  `python3 -m unittest discover -s tests -p test_matt_skills.py` (41 tests),
  and `git diff --check`. These are targeted checks, not the full suite or
  the required uv-based pre-commit checks.

## One remaining design choice

User selected Linux Symphony and Linux Codex in WSL, with this Linux-native
skills checkout as the integration pilot on 2026-09-23. No universal Windows/WSL launcher or broad migration is approved.
No action has been taken on the separate native Windows port task.

## Implementation sequence after that choice

1. **Curated repository-owned skills.** Import the ten agreed Matt skills from
   revision `6acc160e4e0cd062dbbbd7a1b26ae92855edf07e`, preserving attribution,
   license and source revision; the retained source directories are present
   under the Windows shared root. Check all supporting files and references
   against the pin before copying, rather than treating an installed copy as
   pristine upstream. Keep the existing `implement` fork and shadow machinery.
   Version these as owned forks, not immutable `VENDORED_SKILLS`. Extend
   flattened-name shadow protection to the retained forks, including protection
   against external collection name collisions through `ownership()` and
   `claimed_names()`. Replace the broad Matt offering with the supported subset
   across installer/dashboard/docs; define an explicit legacy-flag migration
   message and preserve already installed unrelated skills and ownership records.
2. **Apply the agreed session behavior.** Keep `codebase-design`,
   `diagnosing-bugs`, `tdd`, `research`, and `writing-for-agents` available to
   workers. Workers document test seams and blockers in their workpad, retain
   Symphony issue ownership during any in-session delegation, and record
   architecture follow-ups rather than launching the omitted architecture skill.
   Keep `domain-modeling`, `grilling`, `code-review`, `handoff`, and `implement`
   for interactive use. Preserve `code-review`'s parallel Standards/Spec reviews;
   replace its setup dependency with existing project mapping and linked spec.
   Keep explicitly invoked `claude-handoff` unchanged, without transferring
   Symphony ownership. Clarify `implement`'s interactive description and display
   name. Omit broad routers, triage and ticket generation from worker discovery.
3. **Explicit worker configuration.** Add a launch-context marker and a selected
   worker skill set. Keep the ordinary interactive environment separate. Remove
   the mandatory global visualization-first requirement in `global/AGENTS.md`;
   keep the skill usable interactively and disable `viz-driven-dev` in workers.
   Ensure Symphony sessions use the upstream workpad lifecycle instead of the
   legacy claim/readiness-label/Current-overview/handoff rules. Preserve unrelated
   global instructions and project coding/validation rules.
   Official [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills)
   currently documents user `.agents/skills` discovery and disabling canonical
   `SKILL.md` paths through `[[skills.config]]` in user configuration. Reverify
   actual discovery and configuration precedence with the chosen executable;
   separate `CODEX_HOME` or project configuration alone is not acceptance evidence.
4. **Small project setup surface.** Implement one project service module called
   by `install.py`, `skills_cli.py` and `skills_tui.py`; keep actual skill writes
   going through `install_one` and the existing ownership/receipt machinery.
   A focused `skills symphony setup|check|start --project-dir ...` is a proposed
   command shape, not an existing or finalized interface. The dashboard exposes
   project setup and readiness using the same implementation. Scripted paths
   work without Textual. Setup records project identity, exact setup issue ID,
   pinned runtime, isolated workspace root, selected worker skills, and dashboard
   settings. It consumes existing project information, reports missing inputs,
   and does not edit templates or dispatch workers. Avoid credential persistence
   in generated project files, overwriting existing workflows, or copying a
   Windows virtual environment into Linux.
5. **Preserve upstream execution.** Generate `WORKFLOW.md` from the verified
   upstream sample at the handoff pin, adapting repository hooks and skill paths.
   Keep Backlog -> Todo -> In Progress -> Human Review -> Merging -> Done;
   one persistent workpad; manual Human Review; Todo for feedback on an attached
   PR; Rework only for a full reset; upstream land flow after approval. Human
   Review stays outside active states. Keep polling, retries, issue workspace
   management and cleanup in Symphony. Do not create a second scheduler.
6. **Explicit start and readiness gate.** Before starting the upstream executable,
   verify the recorded setup issue belongs to the configured project and its
   state is specifically Done. Missing/incomplete/unverifiable or cancelled setup
   issues block startup; the completed issue must carry reviewed setup evidence.
   Do not use ordinary terminal-blocker semantics as a substitute. Bind the
   dashboard to localhost by default, support configurable port and disabling it,
   and verify the actual bind behavior of the selected runtime. Setup/check
   commands never dispatch, and this implementation session must not start live
   dispatch merely to validate configuration.
7. **Verification and delivery.** Add focused tests for the gate's failure cases,
   setup idempotence and existing-file preservation, no-dispatch setup/check,
   worker skill discovery, fork drift/ownership, dashboard defaults, and CLI/TUI
   delegation. Use isolated homes for installs and the existing plugin-off test
   helpers. Run a disposable no-production-dispatch integration probe for the
   selected runtime: app-server loading, normal sandbox command execution,
   deliberate failure propagation, timeout/cancellation and workspace cleanup.
   Treat the current app sandbox failure and absent runtime prerequisites as
   unresolved evidence gaps, not reasons to weaken worker isolation. Run the
   required uv validator/full suite and Graphify update after code changes;
   run Node artifact tests if that client changes. Record release implications
   under Unreleased without cutting a release.
8. **Templates last.** After implementation and validation, reconcile repository
   onboarding documentation, native project template's embedded setup issue,
   master playbook, and Agent task template to the delivered behavior. Discover
   actual template-edit capability before claiming writes. Reconcile existing
   copied issues explicitly; DIE-59 currently forbids Symphony activation during
   harness preparation. Do not substitute DIE-32 for the project's setup issue.
   Required records and IDs are in the accepted handoff.

## Original next action (superseded by the gates above)

Begin the curated-fork import and the small WSL/Linux project setup
implementation above; the runtime/pilot choice is now resolved. Keep template edits until the
final integration step and require separate explicit live-start authorization.
