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

**This file is public.** `dm1681/skills` is a public repository, cloned on a
work machine as well, so write here only what is safe to publish. Facts about
particular machines, networks or addresses go in the private layer that the
personal machines load from `~/.claude/rules/`.

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

### Naming issues

Name a Linear issue by its slug, never a bare identifier, in everything a person
reads: replies, comments, PR bodies, handoffs. The slug is the identifier plus 2
to 5 kebab-case words saying what the issue does, e.g.
`DIE-207-anchor-candidate-vs-baseline`. It is the first line of the issue
description, `**Slug:** `<slug>``; use it exactly as written. An issue you create
gets that line from you; in a project the Dispatcher maps, a tick adds one within
minutes if you leave it out. An issue with no slug line yet is named by its
identifier and a few words of its title. Lines that link a PR to its issue
(`Linear issue: DIE-207`, `Closes DIE-207`) stay bare.

Every mention counts: a list, a "next" line, a range of issues, a repeat of one
named a line earlier. A pull request is named the same way, with its issue's
slug (`PR 212 (DIE-485-session-limit-band-policy)`); one with no issue gets a
few words of its title (`PR 216 (pause automatic releases)`). A bare number
tells the reader nothing about what the work does.

### Required status synchronization

This applies to every authorized session working a mapped issue, including
supervised setup work. Comments and checklists do not change the issue's status
field.

- Before substantive implementation, read the issue's current state and ownership.
  When authorized work begins from Backlog/Todo, set the mapped active state
  (In Progress here) and fetch the issue again to verify it.
- At meaningful checkpoints and before ending a substantive work turn, reconcile
  actual progress with the issue state. Keep In Progress while implementation or
  required validation remains. Move to the mapped review state only when its
  acceptance bar is met and the work is ready for human review. Follow explicit
  blocker exceptions instead of silently resetting started work to Backlog.
- After every state mutation, fetch the issue by its exact ID and verify the
  state field. A successful comment edit or mutation request alone is not proof.
  Respect a concurrent human change; do not blindly overwrite it.
- "Keep incomplete until reviewed" means do not mark Done; it does not mean keep
  Backlog.
- If access or authorization prevents a transition, report the failed transition
  and last verified state in the existing progress record and final response.
  Continue only independently authorized work; never claim the state was updated.
  Otherwise include the verified issue state when reporting substantive completion.

### Interactive tracking

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

## Third-party packages

Vet before downloading or installing anything third-party: publisher, popularity,
maintenance status, known CVEs, license — and surface that to the user. Prefer
the standard library or already-installed tooling to keep the dependency surface
small. When a package is genuinely needed, present the vetting summary and
install it deliberately (on demand, into an isolated env) rather than
auto-installing.
