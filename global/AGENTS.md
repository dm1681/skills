# Global agent instructions

These apply to every project on this machine, in addition to any project-level
`AGENTS.md` or `CLAUDE.md`.

**Source of truth: `global/AGENTS.md` in the dm1681/skills checkout.** If you
are reading this text as `~/.agents/AGENTS.md` or `~/.claude/CLAUDE.md`, you
are reading an installed copy. Never edit it in place — change the checkout's
`global/AGENTS.md` and rerun `./install.sh --global-instructions`, because an
in-place edit is backed up and overwritten by the next install. This applies
to agents asked to "always remember" something globally: the durable place for
that instruction is the checkout, not the installed file.

Install with `./install.sh --global-instructions` (see the repo `AGENTS.md`).
`--global-instructions` (link, the default) writes pointer files that `@`-import
this one, so edits take effect without reinstalling; `--global-instructions
copy` writes the text into `~/.agents/AGENTS.md`, which then needs a reinstall
after every change.

Instruction-file discovery is agent-specific: installing a skill directory or
copying this text does not prove an agent loads it. When setting up a device,
check `docs/agent-support.md` in the skills checkout for loading gaps.

## Linear work tracking and handoffs

Apply this workflow when the repository's `AGENTS.md` identifies a Linear
project. Keep its project URL/ID, team, workflow exceptions and technical
policies there; use the onboarding example in `docs/linear-workflow.md` in the
skills checkout. These conventions grant no new execution, messaging or
publishing authorization. Use only actions authorized for the current task.

### Required status synchronization

This applies to every authorized session working a mapped issue, including
supervised setup work. Comments, workpads and checklists do not change the issue's
status field.

- Before substantive implementation, read the issue's current state and ownership.
  When authorized work begins from Backlog/Todo, set the mapped active state
  (In Progress here) and fetch the issue again to verify it. Symphony workers
  must follow their existing routing: never self-dispatch Backlog or reopen a
  Human Review/terminal issue; preserve the Merging and Rework flows.
- At meaningful checkpoints and before ending a substantive work turn, reconcile
  actual progress with the issue state. Keep In Progress while implementation or
  required validation remains. Move to the mapped review state only when its
  acceptance bar is met and the work is ready for human review. Follow explicit
  blocker exceptions instead of silently resetting started work to Backlog.
- After every state mutation, fetch the issue by its exact ID and verify the
  state field. A successful comment edit or mutation request alone is not proof.
  Respect a concurrent human change; do not blindly overwrite it.
- "Keep incomplete until reviewed" means do not mark Done; it does not mean keep
  Backlog. For supervised Symphony setup, use In Progress once work starts,
  Human Review when the setup deliverable is ready, and Done only after human
  acceptance. Worker Done still requires the upstream merge completion bar.
- If access or authorization prevents a transition, report the failed transition
  and last verified state in the existing progress record and final response.
  Continue only independently authorized work; never claim the state was updated.
  Otherwise include the verified issue state when reporting substantive completion.

### Legacy interactive tracking

These claim/label conventions apply to projects not using Symphony. Interactive
setup in a Symphony project uses the status rules above and the project setup
issue, without importing the worker dispatch protocol.

1. **Resume:** verify Linear access on this device/session. Read the mapped
   project's Current overview, the matching issue, its dependencies and latest
   handoff/comments. Reconcile them with the actual remote, branch, HEAD,
   worktree and uncommitted changes before choosing the next action. Reuse the
   existing issue; search before creating one within the authorized scope.
2. **Claim:** check the assignee, In Progress state and latest ownership record
   for another active session. Resolve an overlapping claim before editing.
   Record the agent/session or task, branch, worktree and starting HEAD on the
   issue, then set In Progress and remove `ready-for-agent`. Re-read ownership
   before starting; a comment alone is not an atomic lock. If an authorized
   claim cannot be recorded, report that limit and keep a local record.
3. **Track:** use the state/label rules below and record dependency links and
   blockers as they change. Use the repository's documented equivalents when
   names differ; report missing configuration instead of creating a workflow.
4. **Handoff:** at meaningful checkpoints and before stopping, record completed
   work, acceptance evidence and tests (including failures, skips and untested
   environments), blockers, branch/commit/worktree, uncommitted files and the
   exact next action. Identify who owns the next step and whether this session
   has released its claim. After substantive work, refresh the project's
   Current overview with the current milestone, verified result, active work,
   blockers and next action, retaining unrelated project context.

| State or label | Use |
| --- | --- |
| Backlog | Future or blocked work; state the blocker and remove `ready-for-agent`. |
| Todo + `ready-for-agent` | Clear acceptance criteria, dependencies satisfied, available for an agent to claim. |
| In Progress | Claimed work; remove `ready-for-agent`. |
| In Review | Implementation ready for pending review; link the evidence and remaining review action. |
| Done | Acceptance criteria verified with evidence; distinguish local completion from merge/deployment when those are required. |
| `needs-decision` | A concrete user question with options and a recommendation; remove after recording the resolution. If it blocks work, use Backlog and remove readiness. |

If the mapping, connection or write authorization is missing, preserve a pending
handoff in the repository's chosen location (default
`docs/handoffs/<issue-or-task>.md`) with the same fields and the missing input.
Continue independent authorized work; do not guess a project or report a claim
or sync as successful. When access returns, reconcile current Linear state
before publishing an authorized pending handoff. These instructions neither
install nor authenticate the connector: verify access separately on each device
and keep credentials out of synced files.

## Symphony worker sessions

A worker is explicitly identified by its launcher (`SKILLS_SESSION_KIND=symphony`)
and launch instructions. A workflow file or an absent human does not identify it.
For these workers, Symphony owns dispatch, retries, workspaces and the lifecycle:
Backlog -> Todo -> In Progress -> Human Review -> Merging -> Done. Use the single
persistent issue workpad for plans, acceptance, validation, progress and blockers.
The legacy Linear claim/readiness-label/Current-overview/separate-handoff protocol
above does not apply to Symphony workers. Interactive sessions retain their normal
skills; workers use the launcher's selected skills and project coding standards.

Humans run code-review during Human Review. Todo resumes incremental feedback on
an attached PR; Rework is a deliberate full reset. Approval moves work to Merging,
where the upstream land workflow runs; Done follows the merge. Visualization is
optional in interactive work; viz-driven-dev is disabled for Symphony workers.

## graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

## Workflows

When authoring a Workflow script, choose `model` and `effort` per `agent()`
call to match that agent's own task — never leave the tier to inherit by
default. Cheap mechanical stages (grep, list, transform, extract) get a small
model and `effort: 'low'`; hard reasoning stages (design judging, adversarial
verification, synthesis, root-cause analysis) get the strong model and
`effort: 'high'` or above. Record the pairing in `meta.phases` (add `model` to
the phase entry) and state the tiering in the summary so it can be overridden
before the run.

## Output shaping (ADHD reader)

Assume the reader has ADHD. Shape every response — code, debugging, planning, casual — to be immediately actionable:

- Lead with the next action (command/path/snippet first; context after, if at all).
- Number multi-step work; one bounded action per step.
- End with one concrete next action doable in under 2 minutes.
- Restate progress each turn ("Step 3 of 5 done: X. Next: Y").
- Give time estimates in concrete units (minutes/hours), never "some work."
- Make finished work visible: what now works + how to try it.
- Errors are matter-of-fact: state cause and fix, no "uh oh."
- One issue at a time; defer tangents as a separate offer.
- Cap lists at 5; if longer, split now/later or must/nice.
- No preamble, no recap, no closing pleasantries.

Override when: user says "explain / walk me through" (go long, use headers, still no preamble/closer); a destructive action is ahead (confirm first); stuck 3 turns (name the wrong assumption, ask one diagnostic question); real ambiguity (ask one clarifying question).

## About the user

A practicing **AI Research Scientist**, fluent in Python and deep learning
(PyTorch, training, supervised learning). Pitch ML/AI at research-practitioner
level — don't re-teach fundamentals. Visuals and intuition first, then build by
hand; the maths is solid but rusty, so walk real derivations through step by
step rather than watering them down. Prefers short, high-density material.
Python is the default for personal projects. Timezone: **US Pacific**.

## This machine

Windows 11, **NVIDIA RTX 5090 / 32 GB VRAM**. Never ask about GPU or VRAM —
assume 32 GB. That clears every consumer VRAM gate for local generative models,
so when recommending local AI tooling default to the highest-quality tier, not
the low-VRAM tier.

## GitHub identities and SSH remotes

`~/.ssh/config` has **no `Host github.com` entry** — only per-account aliases
(`github`/`github-dm1681`, `github-thrway1681`, `github-dmcdonald94`), each
pinned with `IdentitiesOnly yes`, and there are no default-named keys. A local
pre-push hook additionally blocks any repo outside `projects/thr` that does not
use `github-dm1681` (or `github`); HTTPS remotes are rejected outright.

**`thrway1681` is a pseudonymous account.** Before ANY `gh` write (issue, PR,
comment, label) against a repo it owns, run `gh api user --jq .login` and require
it to print `thrway1681`. A write attributed to the personal account would
deanonymize the repo.

**How to apply:**
- Never leave a `git@github.com:...` remote. Rewrite it to the owning account's
  alias: `git remote set-url origin git@github-thrway1681:thrway1681/<repo>.git`.
- `gh repo create --push` writes a plain `github.com` remote and fails with
  `Permission denied (publickey)` *after* creating the repo — fix the remote
  before the first push. `gh` still resolves an alias-based remote correctly.
- `gh` holds two accounts (`dm1681` active by default). Against a `thrway1681`
  repo, a wrong-account call fails with `Could not resolve to a Repository`,
  which looks like a missing repo but is an auth problem. `gh auth switch --user
  thrway1681`, then switch back so other projects aren't silently broken. Git
  push/pull is unaffected either way (it uses the SSH alias, not gh's token).

## ssh-keyscan is broken here

`C:\WINDOWS\System32\OpenSSH\` ships OpenSSH_for_Windows 9.5p2 (LibreSSL 3.8.2);
`ssh-keyscan` dies with `choose_kex: unsupported KEX method
sntrup761x25519-sha512@openssh.com`. `ssh.exe` itself works because
`C:\ProgramData\ssh\ssh_config` pins a working `KexAlgorithms` list.

To add a host key, use real ssh, not ssh-keyscan:
- Verify without writing: `ssh -v -o BatchMode=yes -o StrictHostKeyChecking=yes -T <host>`,
  grep `Server host key:` and compare against the published fingerprint.
- Write: `ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -T <host>`,
  confirm with `ssh-keygen -F <host> -l`, roll back with `ssh-keygen -R <host>`.
- GitHub's published Ed25519 fingerprint:
  `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`.

## Networking

The user uses **NordVPN**, not Tailscale. Do not suggest, configure, or document
Tailscale (`tailscale serve`, tailnet URLs, `*.ts.net`) unless asked for by name
— a 100.x address being visible on the machine is not consent to build on it.
For remote access to anything self-hosted, default to the LAN address and ask
what they want for off-LAN access. When they can't reach a LAN host from their
phone, check whether the VPN client's "allow LAN / local network" setting is off.

## Third-party packages

Vet before downloading or installing anything third-party: publisher, popularity,
maintenance status, known CVEs, license — and surface that to the user. Prefer
the standard library or already-installed tooling to keep the dependency surface
small. When a package is genuinely needed, present the vetting summary and
install it deliberately (on demand, into an isolated env) rather than
auto-installing.
