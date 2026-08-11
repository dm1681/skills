---
name: review-loop
description: Drive a pull request through repeated automated review rounds until every active review surface reports no findings, distinguishing a clean verdict from a review that stalled or was silently skipped. Use when driving a PR to a clean review verdict, re-triggering a review that died mid-run or reported success without reviewing anything, or routing reviewer findings into fixes and in-thread replies.
---

# Review loop

`/review-loop <pr-number | branch>` drives one pull request through review
**rounds** until every active **surface** reports no findings, then stops. It
never merges: the loop reports and leaves the PR open for a human.

## A green check is not a verdict

Three things look identical in a PR's check list: a clean review, a review
that died halfway through, and one the runner skipped in fifteen seconds.
Classify every round on a signal the reviewer explicitly posted — never on
silence, never on the check's colour. A round you cannot classify is
unresolved, not clean; say so.

Read [references/surfaces.md](references/surfaces.md) in pre-flight: finding
the active surfaces, reading each one's verdict, replying in-thread, rerunning
it. Read [references/traps.md](references/traps.md) whenever a round is not
clean: the failure modes that produce a green check while reviewing nothing.

## Discover the setup, do not assume it

Every input below varies per repository. Take it from an argument when given,
otherwise resolve it and state what you resolved.

- **Surfaces** — which reviewers comment on this repo's PRs. Read
  `.github/workflows/` and the comments and reviews on the last few merged
  PRs.
- **Deterministic gate** — the required check that actually gates the merge
  (`gh pr checks <n>`). Model reviewers are comment-only and gate nothing.
- **Local gate** — the verification command the repo tells contributors to run
  before pushing (`AGENTS.md`, `CLAUDE.md`, `package.json` scripts, `Makefile`).
- **Round cap** — how many rounds before stopping and handing back. Default 5.

Many repositories have no model reviewer at all. When discovery finds none,
say so and offer the choice: run against the deterministic gate alone, or stop
and provision a reviewer first — this skill drives an existing pipeline.

## Workflow

### 1. Pre-flight

Resolve the PR number, base branch, and the **immutable head SHA**. Anchor
everything to that SHA: a local branch name can be stale, and a fork's branch
is absent from `origin` entirely. When given a branch with no PR, open one.

```bash
gh pr view <n> --json number,baseRefName,headRefOid,isCrossRepository
git fetch origin "pull/<n>/head"
```

Confirm the branch is current with its base. A stale branch silently disables
some reviewers (trap 1) — check this before spending a round.

Record the **diff fingerprint** against that SHA, so later rounds can tell a
substantive change from a base merge:

```bash
git diff "origin/<base>...<head-sha>" | git hash-object --stdin
```

### 2. Trigger a round

A push triggers a round on any surface listening to `synchronize`. When there
is nothing to push — after a re-trigger, or when correcting a trap — the
`reopened` event is the fallback:

```bash
gh pr close <n> && gh pr reopen <n>
```

Check each surface's configured events first: one listening only to
`synchronize` ignores `reopened`, so close/reopen starts nothing and burns a
retry. See [references/surfaces.md](references/surfaces.md) for the per-surface
rerun.

Recompute the diff fingerprint first. When it matches the previously reviewed
head, the substantive diff is unchanged: carry the prior verdict forward and
do not spend a round (trap 5).

### 3. Wait for the round

Wait in two phases, because they finish at different times. `gh pr checks
--watch` returns when the *checks* finish, and model reviewers are
comment-only — they gate nothing and post afterwards, so reading the surfaces
the moment the watcher returns is what makes a live review look stalled.

```bash
gh pr checks <n> --watch          # phase 1: the deterministic gate
```

Then wait on each active surface for a verdict against the current head SHA,
under an explicit per-surface timeout. A surface is stalled only once its
timeout expires with no verdict; say which timeout you used.

Retry a `gh` call that fails with a TLS or certificate error rather than
treating it as a hard failure (trap 7).

### 4. Classify the round

| Outcome | Signal | Next |
| --- | --- | --- |
| **clean** | The gate passed **and** every active surface reported against the current head with no findings | Step 6 |
| **findings** | The gate failed, or a surface reported actionable findings | Step 5 |
| **stalled** | A surface's timeout expired with no verdict for the current head SHA — tracking comment half-ticked or absent | Diagnose, correct, re-trigger |
| **skipped** | Run succeeded in seconds having read nothing | Diagnose, correct, re-trigger |

A passing gate is necessary for **clean**, never sufficient. A failing gate is
a finding like any other: route it through step 5 rather than reporting clean
around a PR that cannot merge.

`stalled` and `skipped` both show a green check, so each needs its own
detection signal — see [references/traps.md](references/traps.md). Correct the
cause before re-triggering, capping retries at two per cause.

### 5. Act on findings

1. Present the findings to the user, grouped by surface, before changing code.
2. Apply the fixes.
3. Reply in-thread on the surface that raised each finding, so the reviewer
   and the next human reader can see how it was addressed.
4. Run the local gate — a round spent discovering a broken fix is wasted.
5. Push, then re-resolve the head SHA: the push moved it, and every later
   fingerprint and verdict query must anchor to the new one. Then step 2.

Route findings; do not adjudicate them. When a finding looks wrong, say so to
the user and let them decide rather than silently declining it.

### 6. Report and stop

Report rounds run, findings addressed, the final verdict per surface, and the
rounds carried forward as unchanged. Leave the PR open and say explicitly that
a human still has to approve and merge it. Stop at the round cap the same way —
hitting it usually means the reviewer and the fixer disagree, a human's call.

## Round ledger

Print this after every round, so a human can read the state and take over:

| Round | Head SHA | Fingerprint | Surface verdicts | Outcome | Action |
| --- | --- | --- | --- | --- | --- |
| 1 | `a06e93d` | `4f2c…` | codex: 1×P1 · gate: pass | findings | fixed, replied, pushed |
| 2 | `682396c` | `4f2c…` | — | unchanged | prior verdict carried |

This is the durable state the loop otherwise rediscovers every session: which
round is in flight, what was reviewed, which surface still owes a verdict.
