# Symphony integration and curated skills: WSL handoff

Date: 2026-09-23 (US Pacific). Originating Codex task: `01a0cf62-0862-7c93-9b51-1d177723d8ec`.

## Resume here

The user has started another session in the skills repo on WSL and requested this handoff. Continue the project-level Symphony integration and curated skill work described below. The user prefers decisions one at a time, and extensive design has already been agreed; do not restart that interview or reopen accepted lifecycle choices. Implementation was intentionally deferred while those choices were resolved. The most recent discussion concerned WSL versus native Windows execution, not cancellation of the integration.

First verify this session's actual checkout, Git state, instruction loading and runtime. The original Windows checkout is `/mnt/c/Users/hbar6/projects/skills` (`C:\Users\hbar6\projects\skills`). A Linux-native clone under `/home/...` is a different checkout: these uncommitted files and this handoff will not arrive through `git pull`. Reconcile/transfer intended work explicitly if the new session uses a different clone.

Read the three research files listed below and current repository instructions. Consolidate the accepted design into a concrete implementation plan, preserving unrelated edits. The runtime choice is still provisional: the user is now exploring using Windows and WSL copies of projects, and has started this WSL session. They have not approved a universal two-environment launcher design, an all-project migration, or cancellation of the separate native port task.

## Verified state and current environment problems

- Branch: `main`; HEAD: `d8641f5c793a510addb44a06cb42c7db6bc0af69`.
- This conversation implemented no Symphony installer/runtime feature and made no curated-skill edits. It produced research documents and this handoff. No commits, pushes, installations, live Symphony workers or Linear writes were performed by this conversation.
- Many pre-existing edits exist. Windows Git previously reported modified `AGENTS.md`, `CHANGELOG.md`, `README.md`, `docs/agent-support.md`, `docs/cloud-skills-sync.md`, `docs/matt-pocock-skills.md`, `global/AGENTS.md`, `install.py`, and `tests/test_matt_skills.py`. Untracked items included `.claude/settings.local.json`, an image, `docs/handoffs/`, `docs/linear-workflow.md`, `docs/research/`, `mp/`, `skills/implement/`, and `tests/test_shadowed_skills.py`.
- During this handoff Linux Git reported modifications to most tracked files, including ones absent from the earlier Windows status. `git -c core.filemode=false status` did not eliminate that list; `git diff --summary` was empty. Cause has not been established (line-ending/config differences are a possibility). Do not reset, normalize, stage all, or assume all reported changes belong to this task.
- The app changed this task to Bash/WSL but supplied a malformed cwd beneath `/mnt/c/Program Files/WindowsApps/.../app/resources/C:\Users\hbar6\projects\skills`. Do not create files there or mistake it for the repository. Commands used the explicit correct directory above.
- Sandboxed commands currently fail before execution with `error building bubblewrap command: app-server socket directory has an unsupported host mount at /mnt/wslg/distro; remove the bind-mount alias or nested mount before starting the sandbox`. Approved host execution was used for limited reads and writing this requested handoff. No sandbox settings or mounts were changed. A correctly created WSL session may avoid the app-path problem, but must verify its own sandbox.
- Graphify query attempts failed with `Failed to canonicalize script path` in the Windows session; source reads were used instead. No code changed, so no graph update was needed.

## Accepted integration decisions

### Installation and execution

- Symphony is project-level only, not a global/user-level skill or orchestration installation.
- Provide a project setup path in this repo's installer/dashboard; a separate explicitly invoked start action begins issue dispatch.
- Setup configures and checks readiness without launching workers. The web dashboard is enabled by default when Symphony starts, bound to localhost, with configurable port and a disable option.
- Proposed command names such as `skills project setup`, `skills project check --platform both`, and `skills symphony start` were illustrative, not implemented or finalized. The user was hesitant about the broad two-environment management proposal. Avoid building that larger framework without resolving its scope.
- Preserve Symphony's engine and lifecycle rather than creating a competing scheduler. Native runtime porting, if pursued, belongs to the separate task below.

### Lifecycle: fully adopt Symphony

The user explicitly rejected keeping a hybrid of their old Linear lifecycle and Symphony's. Adopt the upstream sample's lifecycle and workpad behavior, not the old shared readiness-label/claim/handoff protocol.

- `Backlog` -> `Todo` -> `In Progress` -> `Human Review` -> `Merging` -> `Done`.
- Prepared issues go to Symphony; interactive sessions handle interviews and preparation.
- Use the single persistent issue workpad for plans, acceptance, validation and progress.
- Drop automatic project Current overview updates, old `ready-for-agent` claim/removal rules, and the separate handoff-document workflow for Symphony execution.
- Human runs our Matt-derived `code-review` manually during Human Review and posts actionable findings on the PR.
- For incremental feedback on the existing PR, move the issue to Todo; the sample explicitly supports attached-PR Todo pickup, sweeping feedback, fixing or justified pushback, revalidating, and returning Human Review.
- `Rework` in the sample is a full approach reset, closing the prior PR, replacing the workpad and starting a fresh branch. Do not use that accidentally for every small comment fix.
- Once approved, human moves to Merging; follow the upstream land workflow, then Done after merge.
- Human Review is excluded from sample active states. PR comments alone do not reliably wake a worker; tracker transition is the dispatch trigger.
- The sample reviews its plan and performs validation/CI/feedback sweeps. It does not explicitly mandate an independent generated-code review. Manual Human Review is the agreed location for our code-review skill.
- Initial research recommendations to retain old claims/readiness labels/overview/rework semantics have been superseded. Do not implement those recommendations from the earlier assessment.

### Explicit session split

Workers must be explicitly identified by their launch context, not inferred from human absence or WORKFLOW.md existing. Interactive skills remain available in ordinary sessions; workers get a selected skill set. Project coding standards and technical validation still apply.

Separate CODEX_HOME alone does not hide home `.agents/skills`. Earlier source research found `skills.config` overrides processed in Codex User and SessionFlags layers, not project config alone, with entries using canonical SKILL.md paths. Reverify against the chosen Codex build before implementation. Do not assume a project disable list has worked without checking actual worker discovery.

## Curated repo-owned skills

Replace the broad Matt collection option with a supported subset owned by this repo. Retain upstream attribution and source revision, review upstream improvements deliberately, and prevent original upstream installs overwriting our forks. Initially unchanged content can remain byte-equivalent, but behavior changes belong in versioned source here, not installed home copies.

The user approved these choices:

| Skill | Agreed scope / changes |
| --- | --- |
| `codebase-design` | Keep for interactive and Symphony sessions. |
| `domain-modeling` | Interactive planning; workers consume resulting glossary/ADRs rather than running its interview. |
| `diagnosing-bugs` | Keep both; workers record blockers in workpad instead of requesting live input. Replace automatic `improve-codebase-architecture` handoff with recorded follow-up recommendation. |
| `tdd` | Keep. Interactive sessions confirm test seams; Symphony workers choose and document them themselves. |
| `research` | Keep both; delegate within current session if supported, otherwise investigate directly. Symphony retains issue ownership. |
| `writing-for-agents` | Keep both. |
| `grilling` | Interactive-only; preserve interview/wait behavior. |
| `code-review` | Manual interactive use during Human Review. Preserve parallel Standards and Spec reviews. Replace dependency on setup-matt-pocock-skills with existing project tracker mapping and linked issue/spec; ask for missing spec source rather than invoking whole setup. |
| `handoff` | Keep for interactive use. Symphony uses its workpad. |
| `claude-handoff` | Keep unchanged as explicitly user-invoked. User rejected blanket exclusion just because it launches an external agent. It does not transfer or stop Symphony ownership; no special rewrite required. |
| Local `implement` fork | Retain internal name; make description/display metadata clearly interactive-only and exclude from unattended execution. Suggested display name: Implement (interactive). |

Do not use `triage` or `to-tickets` in Symphony. Proposed supported subset also omits `loop-me`, `ask-matt` and `setup-matt-pocock-skills`; broad routers would point to unsupported workflows. Inspect retained skills' references and supporting files before finalizing installation, rather than silently retaining the whole upstream collection for dependencies.

The global mandatory visualization-first requirement is to be removed. `viz-driven-dev` remains usable interactively and must be explicitly disabled in Symphony workers; merely removing the AGENTS requirement does not prevent its trigger description from invoking it. Symphony supplies reproduction and validation requirements instead.

Matt source inspected: v1.2.3, commit `6acc160e4e0cd062dbbbd7a1b26ae92855edf07e`, recorded in the Windows shared root `.skills-external.json`. Original files are under `/mnt/c/Users/hbar6/.agents/skills`. The WSL session may not discover those automatically. Reading a skill for migration is not invoking its workflow.

## Project onboarding, templates and setup gate

No separate setup skill is needed. The project installer setup path should consume existing project information and configure Symphony. It must NOT edit Linear templates as part of ordinary setup. The user corrected this explicitly: update templates ourselves at the END of the implementation to match the finished integration.

Live Linear reads found:

- Workspace project template `Agent-Ready Software Project`, ID `d8000a8e-a285-4dbe-9a1b-c1caaa2fc96c`, including issue `Set up repository for harness engineering`.
- Workspace issue template `Agent task`, ID `82789dda-2d26-4808-a957-a43e3dfba272`; still carries old ready-for-agent/needs-decision/pickup/handoff conventions.
- Master document `Harness Engineering — Repository Setup Playbook`, ID `2ca3ee6d-a0da-4f1d-9eba-eef89cf2770e`, version 1.1:
  https://linear.app/diego-mcdonald/document/harness-engineering-repository-setup-playbook-b2e35753abae
- Existing copied setup issues include DIE-58 (funscript-gen) and DIE-59 (Puppy Instagram Autopilot). DIE-59 was read: it explicitly forbids installing or activating Symphony during current harness preparation.
- The playbook's template activation section says not configured, but a live template now exists under the name above. Reconcile that stale section; do not assume team default selection was verified.

Agreed new-project flow:

1. Create project using its template, which supplies the setup issue.
2. Run setup issue supervised to prepare actual repository harness/instructions/validation.
3. Run project-level Symphony setup to configure the runtime and skills without dispatch.
4. Review evidence and complete the setup issue.
5. Explicitly start Symphony.

The user approved a startup readiness gate: configuration records the exact setup issue ID; start verifies it belongs to the intended project and is Done, with completion based on reviewed setup evidence. If missing, incomplete or unverifiable, do not launch workers. This is a small local startup addition, not an existing standard Symphony project-wide gate. Ordinary Linear blocker handling only gates Todo and accepts terminal blockers, including cancellation, so it is not a substitute for this Done check.

Use native Linear relationships: issue membership in project; blocks/blocked-by for actual implementation dependencies; related links for nonblocking follow-ups; attached PR; persistent workpad. No need to link every issue to the setup issue since the project start gate handles that prerequisite. Do not assume Symphony invents missing dependency links.

At implementation closeout update the project template's embedded setup issue, master playbook, Agent task template and repository onboarding docs consistently. Existing copied issues need explicit reconciliation; template edits do not retroactively edit them. Current connector supported reading/applying templates but no template-edit tool was established; discover capabilities then rather than claiming updates succeeded. No Linear writes have occurred here.

Earlier answers incorrectly assumed 'template and issue' meant only docs/linear-workflow.md and DIE-32. The native project template and harness setup issue above are the relevant new-project mechanism. DIE-32 and docs/handoffs/DIE-32.md remain background on old global instruction work, not the Symphony setup ticket.

## Windows / WSL research and outstanding choice

Read:

- `docs/research/symphony-upstream-assessment.md` (original conflict inventory; lifecycle recommendations superseded as noted).
- `docs/research/symphony-native-windows.md`.
- `docs/research/symphony-wsl-powershell.md`.

Upstream inspected and HEAD verified during research: `be10a1b79df723d6d7612b5651c8522704dafb2e` (commit dated 2026-09-15).
https://github.com/openai/symphony

Findings: Elixir and Codex support native Windows, but Symphony hardcodes Bash/sh internally and publishes/tests Linux/macOS builds. Git Bash is a plausible bridge, not proven support. WSL2 is closer to upstream assumptions. Path translation alone does not make Windows-only code or dependencies Linux-compatible. Launching Windows codex.exe from Linux Symphony also raises JSON cwd/sandbox-root translation problems, not just shell arguments.

Read-only interoperability probes actually passed on this host before the session runtime switched:

- Default Ubuntu distribution running WSL2.
- Repository path conversion `/mnt/c/Users/hbar6/projects/skills` <-> `C:\Users\hbar6\projects\skills`.
- Ubuntu invoked Windows `/mnt/c/Program Files (x86)/PowerShell/7/pwsh.exe`, which reported version 7.6.4, Win32NT, and correct Windows cwd.
- Deliberate Windows PowerShell exit 7 propagated through WSL correctly.
- Probed non-login Ubuntu PATH found git and bwrap plus Windows pwsh.exe, but did not find codex, Linux pwsh, elixir, mix or erl. This is a PATH observation, not a claim those exist nowhere; recheck current session.
- Those probes used approved host execution, not a future worker sandbox. Full Symphony/Codex sandboxed Windows interop, cancellation, timeout and cleanup remain UNTESTED. Nothing was installed.

Latest recommendation under discussion: independent Windows and Linux-native clones sharing Git source/lockfiles, each with native dependencies and caches; pilot one representative project before broad migration. Keep the existing Windows checkout intact. The user has not selected a pilot or approved migration of all projects. They disliked the friction of an elaborate two-environment management proposal. Prefer a small implementation using existing tools over a new orchestration framework.

## Separate native Windows port task

At the user's explicit request, created `Port Symphony to native Windows`:

- Task ID `01a0d0d7-f71e-7581-903f-31404013be60`, host `local`.
- Original dedicated directory: `C:\Users\hbar6\Documents\Codex\2026-09-23\symphony-windows`; output directory under `outputs`.
- Prompt requests a full native Windows/PowerShell port of upstream Elixir Symphony, preserving capabilities, tested process/hook/path/sandbox handling, native build/run tooling and Windows CI. Dashboard localhost default. No WSL/Git Bash runtime requirement. No changes to the skills repo, no production dispatch or real tracker mutation merely to test.
- Immediately after creation it reported active/inProgress. At this handoff, wait_threads and read_thread report `notLoaded`, no turns, and a similarly malformed translated cwd under app/resources. This does NOT establish successful ongoing implementation or completion. Inspect/recover the task if needed.
- User was asked whether to pause it while evaluating WSL, but did NOT explicitly answer yes. This conversation has not paused, cancelled or sent new instructions to that task. Do not claim it was stopped.

## Implementation pointers and checks

- `install.py` owns installer behavior and `install_one`, external collection fetch/verification, receipts and ownership. `skills_tui.py` must delegate installation rather than duplicating it; external registry and TUI installer mapping are test-pinned. `skills_cli.py` owns command exposure.
- Existing local implement fork uses `SHADOWED_SKILLS`; preserve the same-name shadow behavior. Upstream category skipping cannot replace flattened-name filtering.
- Use shared `install_upstream` and ownership/forget_records machinery rather than copying installer logic. Curated imports/forks need provenance and dependency/reference checks.
- Tests performing installs must redirect home; status tests must avoid probing actual Claude plugins (`SKILLS_PLUGIN_STATUS=off` in test helpers). Do not uninstall unrelated user skills as an implicit migration side effect.
- Canonical shared guidance is this checkout's `global/AGENTS.md`; installed copies must not be edited in place. AGENTS.md is canonical and CLAUDE.md imports it.
- Keep CLI paths functional without Textual.
- Required checks before committing: `uv run python scripts/validate_repo.py`, `uv run python -m unittest discover -s tests`; Node 22 tests if artifact client touched. Appropriate targeted tests during development. No current-turn implementation test pass is claimed.
- Earlier work recorded a Windows WinError 32 cleanup error in test_semantic_pr_review; historical result was 499 tests / 490 pass / 8 skip / 1 error. Re-run when changes require it; do not treat this as a current WSL outcome.
- Version at last observation: 10.0.1. Follow RELEASING.md for feature notes/version policy; do not perform a release merely to land implementation.

## Exact next action

Continuation implemented in the Linux checkout on September 23, 2026. Resume
from the current evidence and ordered gates in
[the implementation plan](../research/symphony-implementation-plan.md#exact-next-action-and-gates).
The original resume instruction below is retained as history; the runtime/pilot
choice and implementation work have since progressed. Native templates and authentication are now configured; human setup review,
commit/sync and the separately authorized live trial remain.

Verify the new WSL session is in its intended real checkout and can execute sandboxed commands. Reconcile the unusually broad Git diff before editing. Then resume the accepted project-level integration and curated forks with a concrete plan, first settling only the remaining runtime/pilot choice. Carry forward all accepted lifecycle and skill decisions. Keep template updates as the final integration step and do not start live dispatch as a side effect of setup.
