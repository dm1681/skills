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
surfaces, reading each verdict, replying in-thread, rerunning. Read
[references/traps.md](references/traps.md) whenever a round is not clean.

## Discover the setup, do not assume it

Four inputs vary per repository: the active **surfaces**, the **deterministic
gate** (whatever branch protection requires, whichever app produces it), the
repo's **local gate** command, and the **round cap** (default
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
`gh pr checkout <n>`, and record the remote and ref to push to. A bare `git
push` from whatever branch was checked out can update something unrelated.

Confirm the branch is current with its base. A stale branch silently disables
some reviewers (trap 1) — check this before spending a round.

Record the **diff fingerprint** — patch hash *and* base revision, since the
same patch over a moved base is a different integration:

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
retry. See [references/surfaces.md](references/surfaces.md) for each rerun.

Recompute the fingerprint first. Carry forward only **model-review** verdicts,
and only when patch hash and base revision both match and that prior verdict
was explicit. The gate always re-runs for the current head: a rewritten commit
can keep the patch identical while changing the metadata a DCO or signed-commit
check reads. A moved base is a different integration, and carrying an
unresolved round forward manufactures a verdict nobody issued (trap 5).

### 3. Wait for the round

Wait in two phases, because they finish at different times. `gh pr checks
--watch` returns when the *checks* finish, but comment-only reviewers post
afterwards — reading the surfaces the moment it returns is what fakes a stall.

```bash
until [ "$(gh pr view <n> --json statusCheckRollup --jq length)" -gt 0 ]
do sleep 10; done                 # wait for the suite to exist
gh pr checks <n> --watch          # phase 1: the gate
```

Poll for **existence, not success**: after a push `--watch` can exit `no
checks reported` instead of waiting, and `gh pr checks` also exits non-zero
when a check *fails*, so polling its exit status spins forever on a red gate.

Then wait on each active surface for a verdict against the current head, under
an explicit per-surface timeout; say which timeout you used. Bound both phases
with the runner's process timeout or a deadline loop — `timeout(1)` is absent
on a stock macOS — since an unbounded watcher on a wedged run hangs the loop
with no ledger entry for a human to take over from.

Retry a `gh` call that fails with a TLS or certificate error rather than
treating it as a hard failure (trap 7).

### 4. Classify the round

| Outcome | Signal | Next |
| --- | --- | --- |
| **clean** | The gate passed **and** every active surface reported against the current head with no findings | Step 6 |
| **findings** | The gate failed, or a surface reported actionable findings | Step 5 |
| **stalled** | A surface's timeout expired with no verdict, and it did start — tracking comment half-ticked, or a run that began and never finished | Diagnose, correct, re-trigger |
| **skipped** | Run succeeded in seconds having read nothing | Diagnose, correct, re-trigger |
| **failed** | The reviewer's run errored outright, or a surface never started before its timeout, or the round cannot be classified | Report it as unresolved and hand back |

A passing gate is necessary for **clean**, never sufficient; a failing gate is
a finding like any other, routed through step 5.

`stalled` and `skipped` both show a green check, so each needs its own
detection signal — see [references/traps.md](references/traps.md). Correct the
cause before re-triggering, capping retries at two per cause.

### 5. Act on findings

1. Present the findings to the user, grouped by surface, before changing code.
2. Apply the fixes on the checked-out PR branch.
3. Run the local gate — a round spent discovering a broken fix is wasted. On
   a PR from an untrusted fork this executes that fork's code (test scripts,
   build hooks): ask the user before running it, or gate only in CI.
4. Commit, then push to the recorded remote and ref, then re-resolve the head
   SHA. `git push` publishes commits, not working-tree edits: skip the commit
   and the PR head never moves while the loop believes it did.
5. Only now reply in-thread, citing the pushed SHA — replying earlier records
   a resolution the PR head does not yet contain. Then step 2.

Route findings; do not adjudicate them. When a finding looks wrong, say so to
the user and let them decide rather than silently declining it.

### 6. Report and stop

Report rounds run, findings addressed, the verdict per surface, and any round
carried forward. Leave the PR open; a human approves and merges. Stop at the
round cap the same way — hitting it means reviewer and fixer disagree.

## Round ledger

Print a table after every round so a human can read the state and take over —
round, head SHA, fingerprint, per-surface verdict, outcome, action taken. This
is the durable state the loop would otherwise rediscover every session: which
round is in flight, what was reviewed, which surface still owes a verdict.
