# Project-level Symphony (Linux / WSL)

Symphony is an opt-in project runtime. Setup and readiness checks do not dispatch
issues. `start` is the separate action that begins upstream Symphony's dispatch.
This integration targets Linux Symphony plus Linux Codex. Keep Windows checkouts
and dependency environments separate; this does not implement the native Windows
port or a universal two-environment launcher.

## Onboard and configure

1. Create the Linear project using **Agent-Ready Software Project**, which
   supplies a harness setup issue. Prepare the repository in a supervised session
   using the master Harness Engineering playbook.
2. Record the exact project UUID, project slug ID (the final ID in its URL), and
   setup issue UUID or identifier. Configure Symphony without starting it:

   ```sh
   python3 skills_cli.py symphony setup --project-dir /path/to/project \
     --project-id PROJECT_UUID --project-slug PROJECT_SLUG_ID \
     --setup-issue ISSUE_UUID --validation-command 'your existing validation command'
   python3 skills_cli.py symphony install-runtime --project-dir /path/to/project
   python3 skills_cli.py symphony check --project-dir /path/to/project
   ```

   `skills symphony ...` works after PATH setup. The equivalent installer entry is
   `./install.sh --symphony setup ...`. In the dashboard (`./install.sh --interactive`),
   press **Y** for the project setup form. Its Save and Check controls never start
   workers. No Textual dependency is needed for scripted commands.
3. Review the setup issue's acceptance evidence and complete it. Missing,
   inaccessible, incomplete or canceled setup issues block startup. The issue
   must belong to the configured project and be specifically **Done** (completed
   type). The code checks state and identity; human review of evidence is the
   completion rule, not something inferred automatically from prose.
4. Start only when explicitly ready to dispatch:

   ```sh
   skills symphony start --project-dir /path/to/project --accept-preview
   ```

   `--accept-preview` acknowledges upstream's engineering-preview requirement.
   The launcher rechecks readiness and replaces itself with upstream Symphony;
   polling, retries, continuation, cancellation and workspace cleanup stay in
   the upstream engine. Stop with the normal process interrupt (Ctrl-C).

`LINEAR_API_KEY` must be available to the service environment; interactive app
connectors do not provision it. Codex and `gh` must be installed and authenticated
for the chosen Linux environment. Online readiness checks verify both CLI login
statuses with bounded timeouts and suppress credential-bearing diagnostics.
Offline checks leave authentication unverified. Credentials stay out of generated files and
are not copied from Windows. Upstream removes the tracker secret before starting
Codex; the discovery helper also removes it.

## What setup writes

Only the selected project receives `.symphony/project.json` and
`.symphony/WORKFLOW.md`. Configuration is machine-local; ignore `.symphony/` in
version control. Keep the durable project mapping in `AGENTS.md`. Setup merges
explicit options into existing configuration and preserves an edited generated
workflow rather than overwriting it. Review and reconcile edits before rerunning.
It never edits Linear templates or installs into a global skill root.

The default workspace root is `.symphony/workspaces` inside the project;
each issue gets its own cloned repository. `--workspace-root` overrides this.
The root cannot equal the interactive project or an ancestor. Configuration
loading rechecks this boundary, field types and the runtime pin, including after
manual edits. Existing files inside a new issue workspace are preserved by
refusing the clone. A new workspace starts on `codex/<issue-identifier>` from the
configured base branch, or restores that published issue branch. Workers recover
an attached open PR's branch before handling incremental feedback and never push
implementation commits directly to the base branch.

`--repo-url`, `--base-branch` (default `main`), `--runtime-source`, `--codex`,
and `--validation-command` record explicit project/runtime choices. The origin
remote is used when no repository URL is supplied. Existing coding standards,
ADRs, glossary and repository validation continue to apply.

The web dashboard defaults to `127.0.0.1:8788`. Set `--port PORT` during setup
or disable it with `--no-dashboard`; rerunning setup with `--port` enables it.
The first pilot uses one concurrent worker and upstream's 20-turn invocation
limit; that limit is not a task-wide cost or lifetime bound.

Generated workflows poll every 30 seconds and allow 30 seconds for Codex protocol
responses, including thread startup. Linear API-key quotas are shared per user
across projects and keys, so account for every running service when tuning polling.
Rerun setup to apply these defaults to an existing unedited managed workflow.

## Runtime provenance

The upstream engine is pinned to
`be10a1b79df723d6d7612b5651c8522704dafb2e`. `install-runtime` downloads the official
Linux binary with a fixed SHA256 and checks it before installation and startup.
The `nightly` tag was verified at that source revision on 2026-09-23. Because
nightly is rolling, a later changed asset is rejected, never silently accepted.
The binary embeds Erlang and Elixir; installation does not execute it.

If the historical asset is no longer available, use the pinned source build:
install upstream's Erlang 28 / Elixir 1.19.5-otp-28 tooling, then run
`skills symphony build-runtime`. Fetching uses the existing hardened Git helper;
revision, worktree and source bytes are checked. Build dependencies are fetched
by Mix. Use a fresh `--runtime-source` directory when switching from a package to
a source build; existing runtime directories are preserved.

Attribution and original file hashes for adapted workflow/delivery resources are
in `templates/symphony/upstream.json`, with the upstream Apache-2.0 license.
Repository-specific upstream validation and hook commands are replaced with the
project's documented checks. The land/check/feedback loop remains upstream's.

## Worker skill selection

Workers are explicitly marked by `SKILLS_SESSION_KIND=symphony`, the workflow
prompt, and `.symphony-worker.json` inside their issue clone. Ordinary sessions
are not workers just because a workflow file exists or the user is absent.

Selected worker skills are `codebase-design`, `diagnosing-bugs`, `tdd`, `research`,
`writing-for-agents`, and explicitly invoked `claude-handoff`, plus upstream-derived
`linear`, `commit`, `pull`, `push` and `land`. `claude-handoff` retains its explicit
invocation policy and does not transfer Symphony ownership.

The launcher asks the actual Codex app-server for `skills/list`, disables every
unselected discovered path through session configuration, then asks again. It
refuses launch unless the enabled paths are exactly the selected set. This also
excludes home/admin/system skills, including `viz-driven-dev`, rather than merely
changing a trigger description. It does not assume a separate `CODEX_HOME`
hides `$HOME/.agents/skills`. Discovery probes create no model turn.

The skills pilot is verified with Linux Codex **0.156.1**. The desktop-bundled
0.155.0-alpha.16.3 rejected WSLg's duplicate filesystem mount at
`/mnt/wslg/distro` while protecting its daemon socket. The verified stable
release masks that alias inside restricted execution and passes workspace-write
isolation checks without changing host mounts. If you encounter that exact
failure, install an official verified Linux release and select its absolute path
with `skills symphony setup --codex /path/to/codex`. The current command form is
`codex -c 'sandbox_mode="workspace-write"' sandbox -- /bin/sh -c 'printf sandbox-ok'`.
Changing a project's executable does not update a running desktop app's bundled
backend; diagnose that backend separately. Do not disable sandboxing or unmount
WSLg as a workaround.

The shared worker launcher grants Git access through `symphony_worker.py`. Before
each `turn/start`, it validates the canonical workspace, project marker and real
`.git` directory, then adds only the clone and its `.git` to the turn's writable
roots. Linked worktrees, redirected or shared Git metadata, and unexpected roots
are rejected. Approval, network and temporary-directory policies are preserved.
The configured Codex executable stays native for login, help and discovery;
projects do not need to replace it with their own Git adapter. The launcher
relays JSON lines and cleans up its child process group on shutdown.
SIGINT, SIGTERM and SIGHUP all use that cleanup. Both the real worker and readiness
probe clear inherited Git metadata-routing variables (such as `GIT_DIR`,
`GIT_WORK_TREE`, and `GIT_INDEX_FILE`). Transport authentication settings such as
`GIT_SSH_COMMAND`, `GIT_ASKPASS`, and `GIT_CONFIG_*` remain available so private
repository fetches and pushes use the same credentials as provisioning.

Readiness now creates a disposable repository under the configured workspace root
and uses the same validated roots to run a real native sandbox commit. It also
proves parent and sibling writes fail. Git or isolation failure blocks start;
host execution used by an interactive developer is not a substitute. A workspace
root under a directory already writable by the sandbox (such as default `/tmp`)
cannot pass that isolation proof. Use a dedicated workspace root instead.
This check creates no model turn and does not fetch, push or change service state.
Run the optional native regression explicitly with
`SYMPHONY_TEST_CODEX=/absolute/path/to/codex uv run python -m unittest discover -s tests -p test_symphony_worker.py`.
`check --offline` still checks local prerequisites and reports the unverified
Linear gate, returning 3. Exit 0 means checks passed; 3 means not ready; 2 reports
invalid configuration or a refused operation.

## Issue lifecycle and review

Use Backlog → Todo → In Progress → Human Review → Merging → Done. The team must
also have Rework for deliberate full resets. Startup verifies these state names;
`In Review` is not an automatic substitute for Human Review.

Status changes are an explicit agent responsibility. Read the current issue
at pickup; update and read back its state before implementation, at transitions,
and before reporting completion. Comments do not substitute for state updates.
Supervised setup moves to In Progress when work begins, Human Review when ready
for acceptance, and Done only after human acceptance. Keeping it incomplete does
not mean keeping it in Backlog. Follow the shared status synchronization rules
in `global/AGENTS.md`; workers also retain the upstream routing below.

Prepared issues enter Todo. Workers use one persistent `## Codex Workpad` comment
for plan, acceptance, validation, progress and blockers. They do not remove
readiness labels, claim through the old protocol, update project Current overview,
or write a separate handoff file as their execution trail.

A human runs the curated `code-review` during Human Review and posts actionable
findings on the PR. Move incremental feedback on the existing PR to Todo. Rework
closes the previous PR and replaces the workpad/branch, so reserve it for a full
approach reset. After approval the human moves to Merging; workers follow land
and mark Done after the merge. PR comments alone do not wake a worker; a tracker
transition is the dispatch trigger. Human Review is not an active state.

Use project membership, actual blocks/blocked-by dependencies, nonblocking related
links, the attached PR and persistent workpad. There is no need to link every task
to the setup issue; the project startup gate checks that prerequisite.
