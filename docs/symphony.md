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
are not copied by setup. Upstream removes the tracker secret before starting
Codex; the discovery helper also removes it.

## Project worker Git and GitHub identity

Configure these options through the CLI; the dashboard preserves them when it
updates other settings. Existing configurations without identity options retain
their inherited identity. For an explicit project account:

```sh
skills symphony setup --project-dir /path/to/project \
  --repo-url git@github-work:team/repository.git \
  --git-author-name 'Project Worker' --git-author-email worker@example.com \
  --ssh-host github-work --ssh-config /home/operator/.ssh/config \
  --github-repo team/repository --github-account project-account \
  --credential-provider /home/operator/bin/project-github-token
skills symphony check-git --project-dir /path/to/project
skills symphony check-pr --project-dir /path/to/project
```

`--ssh-host` selects the alias used in fresh clones' origin URLs. If omitted,
the configured URL is used unchanged. The existing SSH config should bind that
alias to github.com, the intended key and `IdentitiesOnly yes`. `--ssh-config`
selects an existing absolute config path; setup creates neither keys nor SSH
configuration. `--ssh-executable` selects one executable (default `ssh`), not a
shell command. Both Git author and committer are set in each worker environment.
GitHub repository selection is explicit `owner/repository` on github.com and must
match the clone URL's repository path; SSH aliases need no DNS resolution for
this comparison. Enterprise GitHub is not supported by these identity options.
Repository, account and provider must be configured together; repository-only
settings are rejected rather than falling back to the active gh account.

The credential provider is a trusted executable at an absolute path, invoked
without arguments in the project directory. It receives `GH_REPO`, `GH_HOST` and
`SYMPHONY_GITHUB_ACCOUNT`, but no inherited GitHub tokens or Linear key. It must
return exactly one token on stdout, exit zero, and finish within 30 seconds.
It may retrieve a token from an existing keychain, secret manager or external
runtime secret file. A provider using an already authenticated gh account can be:

```sh
#!/bin/sh
exec gh auth token --hostname github.com --user "$SYMPHONY_GITHUB_ACCOUNT"
```

Keep providers outside version control, make them executable, and never embed
tokens in their source, arguments, repository URLs or configuration. Provider
output and failure diagnostics are captured and suppressed. Setup stores only
the executable path and public identity settings; it does not invoke providers.
Credentials resolve afresh during clone, launch and online identity checks,
remain in child-process memory, and must stay valid for that worker invocation.
Providers must not write tokens to their own logs or files. The launcher verifies
`gh api user` matches `--github-account` and fails closed for missing credentials,
wrong accounts or provider errors. It never switches the user's gh account.

Worker environments override inherited Git routing/config injection when identity
is configured. The GitHub identity triple overrides inherited GitHub tokens,
repository and host; Git-author/SSH-only settings preserve existing GitHub auth.
For HTTPS github.com
clones, a process-only `gh auth git-credential` helper uses the same provider token.
Discovery servers and sandbox readiness probes also receive scoped environments;
offline probes clear ambient GitHub tokens without invoking the provider.
For SSH, Git authentication remains the key selected by the alias/config, while
PR APIs use the verified provider account. Global Git configuration, gh logins,
the interactive checkout and other projects are not written. This uses the
documented [Git environment overrides](https://git-scm.com/docs/git) and
[gh token/repository precedence](https://cli.github.com/manual/gh_help_environment).

`check-git` reads remote HEAD with `git ls-remote`; for SSH it does not require
the GitHub API provider. `check-pr` verifies the configured account, repository
push permission and PR list access using GET requests. Exit 0 means that check
passed, 3 means access is not ready, and 2 means invalid configuration. These
commands never push, create a PR, dispatch workers or require the Linear setup
gate. Read access and reported push permission cannot prove branch protection or
a token's PR **write** permissions; those need a separately authorized integration
trial. Ordinary installer tests use synthetic fixtures and local Git repositories.
The existing `check` still verifies runtime/discovery, authentication and Linear
readiness; run both access checks separately before an operational rollout.

### Reuse Windows keys from WSL

Key duplication is unnecessary. Where WSL Windows interoperability is enabled,
select `--ssh-executable /mnt/c/Windows/System32/OpenSSH/ssh.exe` and the alias
already defined in the Windows user's SSH config. Omit `--ssh-config` in this
case so Windows OpenSSH uses its native config and key locations. This combines
[WSL's supported Windows executable invocation](https://learn.microsoft.com/en-us/windows/wsl/filesystems#run-windows-tools-from-linux)
with Git's SSH executable override; verify it with `check-git` from the actual
service environment. Windows interop/agent availability can differ in services.
Alternatively, an existing Windows-agent bridge exposed through `SSH_AUTH_SOCK`
lets Linux SSH use the existing keys with a Linux SSH config. The installer does
not install a bridge, copy private keys, alter permissions or change either
machine's default account. Git key access and GitHub API token access are separate;
the provider must also work in the WSL service environment. Native Windows key
reuse is documented, not exercised by the Linux synthetic test suite.

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

## Fresh-worker bootstrap

Source-only projects need no extra configuration. For Python dependencies, keep
a small JSON declaration in the project and import it during setup:

```json
{
  "python": "/usr/bin/python3.12",
  "python_version": "3.12",
  "dependencies": "uv",
  "download_policy": "never",
  "cache_dir": ".symphony-cache",
  "required_tools": ["git"],
  "timeout_seconds": 300
}
```

```sh
skills symphony setup --project-dir /path/to/project \
  --bootstrap-file /path/to/project/worker-bootstrap.json \
  --validation-command 'uv run --no-sync python -m unittest discover -s tests'
```

Setup copies the declaration into local `.symphony/project.json`; it does not run
it, install dependencies or start a service. Reimport after changing the JSON.
Other setup calls (including dashboard saves) preserve it; importing `{}` removes
the bootstrap requirements. Old configurations remain valid. Machine-specific
interpreter paths belong in local configuration; portable declarations can use a
PATH executable name. Readiness checks probe local prerequisites and cache access,
but only a fresh issue clone proves dependency bootstrap succeeds.

The hook checks a **preinstalled** Python with an optional exact major.minor or
major.minor.patch match. It never downloads an interpreter. `dependencies` is
`none` by default; `uv` requires preinstalled uv and committed `pyproject.toml`
and `uv.lock`, then runs `uv sync --locked --python <selected> --no-python-downloads`.
`download_policy` defaults to `never`, adding `--offline`; choose `allow` explicitly
to permit uv dependency downloads. A missing/stale lock or missing offline package
fails bootstrap instead of silently regenerating the lock. uv offline mode controls
uv's network use, not arbitrary network activity in project build scripts.
The repository clone itself still uses the configured Git transport.

Caches must be workspace-relative (default `.symphony-cache`), resolve inside the
clone and pass an actual write probe. The same `UV_CACHE_DIR`, `PIP_CACHE_DIR`,
`XDG_CACHE_HOME`, `UV_PYTHON`, `UV_PYTHON_DOWNLOADS`, `UV_OFFLINE` and workspace-local
`UV_PROJECT_ENVIRONMENT` reach the bootstrap and worker. Offline dependency projects
must supply local dependency artifacts in the clone, or explicitly allow the initial
download; an empty fresh cache cannot satisfy uncached third-party dependencies.
The hook does not reuse or write the interactive checkout's cache. Interactive
`VIRTUAL_ENV`, `PYTHONHOME` and `PYTHONPATH` are removed. Use `uv run --no-sync` for
the prepared venv, or `"$SYMPHONY_PYTHON"` for the selected base interpreter in validation
commands; bare `python` still follows PATH. Worker cache and venv are Git-excluded.

Optional `required_tools` names/absolute paths are checked without invoking them.
Browser, media and model tooling stays project-owned: the shared hook does not
install browsers, download models or launch applications. Dependency installers can
execute project build steps, so bootstrap is for trusted dependency definitions.
Failures identify the interpreter/tool, cache or locked-sync blocker. Dependency
sync has a configurable 1–3600 second timeout; generated hook timeouts allow another
60 seconds for clone/provisioning. A failed bootstrap produces no ready worker marker.
Changing bootstrap settings requires reprovisioning existing issue workspaces;
the launcher rejects mismatched declarations instead of using stale dependencies.

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
