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
silence, never on the check's colour. A round you cannot classify is failed.

Read [references/surfaces.md](references/surfaces.md) in pre-flight: finding
the active surfaces, reading each one's verdict, replying in-thread, rerunning
it. Read [references/traps.md](references/traps.md) whenever a round is not
clean: the failure modes that produce a green check while reviewing nothing.

## Discover the setup, do not assume it

Four inputs vary per repository: the active **surfaces**, the **deterministic
gate** (whatever branch protection actually requires — model reviewers gate
nothing), the repo's **local gate** command, and the **round cap** (default
5). Take each from an argument when given, otherwise resolve it and state what
you resolved. [references/surfaces.md](references/surfaces.md) covers how,
including the common case of a repo with no model reviewer at all.

## Workflow

### 1. Pre-flight

Resolve the PR number, base branch, and the **immutable head SHA**. Anchor
everything to that SHA: a local branch name can be stale, and a fork's branch
is absent from `origin` entirely. When given a branch with no PR, open one.

```bash
gh pr view <n> --json number,baseRefName,headRefOid,isCrossRepository,headRepositoryOwner
git fetch origin "pull/<n>/head"
```

Fixing findings later needs a **writable branch**, not just the head object:
`gh pr checkout <n>`, and record the remote and ref to push to. A fork's head
is not on `origin`, and a bare `git push` from whatever branch was checked out
can update something unrelated.

Confirm the branch is current with its base. A stale branch silently disables
some reviewers (trap 1) — check this before spending a round.

Record the **diff fingerprint** — the patch hash *and* the base revision it
was reviewed against, since the same patch over a moved base is a different
integration:

```bash
git diff "origin/<base>...<head-sha>" | git hash-object --stdin
git rev-parse "origin/<base>"
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

Recompute the fingerprint first. Carry a prior verdict forward only when
**both halves match** — same patch hash *and* same base revision — and only
when that prior verdict was explicit. A moved base is a different integration,
and carrying forward an unresolved or stalled round manufactures a clean
verdict nobody issued (trap 5).

### 3. Wait for the round

Wait in two phases, because they finish at different times. `gh pr checks
--watch` returns when the *checks* finish, but comment-only reviewers post
afterwards — reading the surfaces the moment it returns is what fakes a stall.

```bash
timeout 30m gh pr checks <n> --watch     # phase 1: the deterministic gate
```

Then wait on each active surface for a verdict against the current head SHA,
under an explicit per-surface timeout. A surface is stalled only once its
timeout expires with no verdict; say which timeout you used. Bound both
phases — an unbounded watcher on a wedged run hangs the loop with no ledger
entry and nothing for a human to take over from.

Retry a `gh` call that fails with a TLS or certificate error rather than
treating it as a hard failure (trap 7).

### 4. Classify the round

| Outcome | Signal | Next |
| --- | --- | --- |
| **clean** | The gate passed **and** every active surface reported against the current head with no findings | Step 6 |
| **findings** | The gate failed, or a surface reported actionable findings | Step 5 |
| **stalled** | A surface's timeout expired with no verdict for the current head SHA — tracking comment half-ticked or absent | Diagnose, correct, re-trigger |
| **skipped** | Run succeeded in seconds having read nothing | Diagnose, correct, re-trigger |
| **failed** | The reviewer's own run errored, or a wait timed out, or the round cannot be classified at all | Report it as unresolved and hand back |

A passing gate is necessary for **clean**, never sufficient. A failing gate is
a finding like any other: route it through step 5 rather than reporting clean
around a PR that cannot merge.

`stalled` and `skipped` both show a green check, so each needs its own
detection signal — see [references/traps.md](references/traps.md). Correct the
cause before re-triggering, capping retries at two per cause.

### 5. Act on findings

1. Present the findings to the user, grouped by surface, before changing code.
2. Apply the fixes on the checked-out PR branch.
3. Run the local gate — a round spent discovering a broken fix is wasted.
4. Push to the recorded remote and ref, then re-resolve the head SHA: the push
   moved it, and every later query must anchor to the new one.
5. Only now reply in-thread, citing the pushed SHA — replying earlier records
   a resolution the PR head does not yet contain. Then step 2.

Route findings; do not adjudicate them. When a finding looks wrong, say so to
the user and let them decide rather than silently declining it.

### 6. Report and stop

Report rounds run, findings addressed, the verdict per surface, and any round
carried forward. Leave the PR open and say a human must approve and merge it.
Stop at the round cap the same way — hitting it usually means the reviewer and
the fixer disagree, which is a human's call.

## Round ledger

Print this after every round, so a human can read the state and take over:

| Round | Head SHA | Fingerprint | Surface verdicts | Outcome | Action |
| --- | --- | --- | --- | --- | --- |
| 1 | `a06e93d` | `4f2c…` | codex: 1×P1 · gate: pass | findings | fixed, replied, pushed |
| 2 | `682396c` | `4f2c…` | — | unchanged | prior verdict carried |

This is the durable state the loop would otherwise rediscover every session.
