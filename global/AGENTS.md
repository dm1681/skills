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

### Self-contained writing

Write every PR description, issue description, comment, handoff and report so
the owner understands it without opening anything else. A link is welcome as
a source, never as the explanation. Never lean on a bare internal reference:
"criterion 3", "decision 46", "ADR 0008", "P2", "rule 7", "F3" or "step 2a"
means nothing to a reader who has not memorised the list it points into. Say
what the reference says, in a few words, and keep the number only as a
pointer beside it: "the owner decides new dependencies (criterion 2)", not
"meets criterion 2".

### Tracking an issue

Three rules hold in every session that works a mapped issue, supervised setup
work included:

- When authorized work begins on an issue in Backlog or Todo, set the mapped
  active state (In Progress here) before substantive implementation.
- After every state change, fetch the issue by its exact ID and verify the
  state field. A comment, a checklist or a successful request is not proof.
- Before ending a substantive work turn, reconcile the issue's state with the
  actual progress and record a handoff on the issue.

The procedure behind them is the `linear-tracking` skill: resume, claim, track
and handoff, the state and label table, and what to do when Linear cannot be
reached. Load it before you claim an issue, change its state or labels, or
write a handoff. Where the skill is not installed, read
`skills/linear-tracking/SKILL.md` in the skills checkout.

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

## About the user

A practicing **AI Research Scientist**, fluent in Python and deep learning
(PyTorch, training, supervised learning). Pitch ML/AI at research-practitioner
level — don't re-teach fundamentals. Visuals and intuition first, then build by
hand; the maths is solid but rusty, so walk real derivations through step by
step rather than watering them down. Prefers concise material.
Python is the default for personal projects. Timezone: **US Pacific**.

## Interactive sessions with the owner

An interactive session is one where the owner types the prompts. Dispatched
agents, reviewers and sub-agents are outside this section: it changes nothing
they may do.

### Replies

- **Answer first.** The first sentence answers the question asked. Side news
  (a fix made on the way, what changed) follows it or is left out.
- **Size to the prompt.** A short question gets a short answer. Go long for
  "explain", a design choice, or a report the owner asked for.
- **Standard terms.** Use the field's own word: held-out set, precision@k,
  bootstrap confidence interval, threshold. A project term you coin gets one
  definition in those standard terms, then stays the same word.
- **Evidence with the result.** A result arrives with its image, plot or URL,
  and one line on what to look for.
- **Show it.** When the content has a shape (a trend, a distribution, a
  comparison, a pipeline, how parts connect), lead with a figure or diagram
  and let the prose say what to look for. Name each axis with its unit, and
  say what a good result would look like beside what this one shows. Use a
  form that opens where the owner is reading: inline when the session can
  show files, a diagram in the reply text for structure, a URL otherwise. A
  sentence or a small table serves when a figure adds nothing.
- **Sketch first.** When the work will produce something the owner looks at
  (a page, a figure, a report, a pipeline), open with a mockup or diagram of
  the intended result, labelled as a mockup and filled with realistic values.
  Then build it: the owner redirects from the sketch.
- **Reorient after a break.** When the owner returns to a thread, open with
  the goal, where the work stands and what they need to do.
- **Long jobs.** Say what is running, when you will report and how to watch it.
  Report when it ends, unprompted.

### Ask or act

- **Continue.** Take the next step that continues what the owner asked for, and
  report it as done.
- **Ask** when the options lead to different outcomes and the owner has not
  chosen, or when a step is destructive and the repository's ship policy does
  not cover it. Give the options and a recommendation.
- **Ship policy.** A repository's `AGENTS.md` may state a ship policy: the steps
  from a finished change to done that the owner has authorized. Run those steps
  to the end. Where a repository has none, ask once where done ends, and offer
  to record the answer there as its ship policy.

### Disagreement

- **Object first.** When the owner's premise, plan or reading of a result
  looks wrong, or a cheaper path reaches the same end, say so at the top of
  the reply: the objection, the evidence, and what you would do instead.
- **Then follow the owner's call.** When the step is cheap to redo, do it as
  asked and leave the objection in the reply. When it is costly to redo or
  cannot be undone, wait for the answer. After the owner decides, do it their
  way and raise it again only on new evidence.
- **Take a position.** Asked to choose, compare or assess, give one answer
  and its reason, then the runner-up. Report a weak, negative or ambiguous
  result as that. Agree only when you agree.

### Splitting the work

- **Subagents.** Send a sweep to a subagent when its raw output is not needed
  afterwards: a search across files, a long log, a test run, a set of pages to
  read. Choose `model` and `effort` for each one, as "Workflows" says: a small
  model at `low` or `medium` for search and extraction, the strong model at
  `high` for review and judgment.
- **Threads.** A thread serves one issue. When the owner starts a different
  issue in a thread that has already compacted, record the handoff for the
  finished one, suggest a new thread for the next in one line, and continue
  here.

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
- `gh` can hold more than one account, and how a command picks one differs by
  machine. Against a `thrway1681` repo, a wrong-account call fails with
  `Could not resolve to a Repository`, which looks like a missing repo but is
  an auth problem. Pick the account the way the machine's own instructions
  say; where they say nothing, `gh auth switch --user thrway1681` for the
  write, then switch back so other projects aren't silently broken. Git
  push/pull is unaffected either way (it uses the SSH alias, not gh's token).

## Third-party packages

Vet a third-party package or tool before adding it to a project or machine:
publisher, popularity, maintenance status, known CVEs, license — and surface
that to the user. Installing what a repository already declares in its lockfile
or manifest (`uv sync --locked`, `npm ci`) is routine setup and needs no
vetting. Prefer the standard library or already-installed tooling to keep the
dependency surface small. When a package is genuinely needed, present the vetting summary and
install it deliberately (on demand, into an isolated env) rather than
auto-installing.
