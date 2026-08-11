---
name: review-loop
description: Drive a pull request through repeated automated review rounds until every active review surface reports no findings, distinguishing a clean verdict from a review that stalled or was silently skipped. Use when driving a PR to a clean review verdict, re-triggering a review that died mid-run or reported success without reviewing anything, or routing reviewer findings into fixes and in-thread replies.
---

# Review loop

`/review-loop <pr-number | branch>` drives one pull request through review
**rounds** until every active review **surface** reports no findings, then
stops. It never merges: the loop ends by reporting and leaving the PR open for
a human to approve and merge.

## A green check is not a verdict

Three different things look identical in a PR's check list: a clean review, a
review that died halfway through, and a review the runner skipped in fifteen
seconds. Classify every round on a signal the reviewer explicitly posted —
never on silence, never on the check's colour. A round you cannot classify is
unresolved, not clean; say so.

Read [references/surfaces.md](references/surfaces.md) in pre-flight: how to
discover the active surfaces, read a verdict from each, and reply in-thread.
Read [references/traps.md](references/traps.md) whenever a round is not clean:
the failure modes that produce a green check while reviewing nothing, each
with its detection signal and recovery.

## Discover the setup, do not assume it

Every input below varies per repository. Take it from an argument when the
user supplied one, otherwise resolve it and state what you resolved.

- **Surfaces** — which reviewers comment on this repo's PRs. Read
  `.github/workflows/` and the comments and reviews on the last few merged
  PRs.
- **Deterministic gate** — the required check that actually gates the merge
  (`gh pr checks <n>`). Model reviewers are comment-only and gate nothing.
- **Local gate** — the verification command the repo tells contributors to run
  before pushing (`AGENTS.md`, `CLAUDE.md`, `package.json` scripts, `Makefile`).
- **Round cap** — how many rounds before stopping and handing back. Default 5.

## Workflow

### 1. Pre-flight

Resolve the PR number, base branch, head branch, and head SHA. When given a
branch with no PR, open one.

Confirm the branch is current with its base. A stale branch silently disables
some reviewers (trap 1) — check this before spending a round.

Record the **diff fingerprint** so later rounds can tell a substantive change
from a base merge:

```bash
git fetch origin && git diff origin/<base>...<head> | git hash-object --stdin
```

### 2. Trigger a round

A push triggers a round. When there is nothing to push — after a re-trigger,
or when correcting a trap — use the `reopened` event instead:

```bash
gh pr close <n> && gh pr reopen <n>
```

Recompute the diff fingerprint first. When it matches the previously reviewed
head, the substantive diff is unchanged: carry the prior verdict forward and
do not spend a round (trap 5).

### 3. Wait for the round

Block on one long-lived watcher rather than polling in a loop:

```bash
gh pr checks <n> --watch
```

When it returns, read every surface once. Retry a `gh` call that fails with a
TLS or certificate error rather than treating it as a hard failure (trap 7).

### 4. Classify the round

| Outcome | Signal | Next |
| --- | --- | --- |
| **clean** | Every surface reported, none has findings | Step 6 |
| **findings** | At least one surface reported actionable findings | Step 5 |
| **stalled** | Run succeeded, no verdict posted for this head SHA — tracking comment half-ticked or absent | Diagnose, correct, re-trigger |
| **skipped** | Run succeeded in seconds having read nothing | Diagnose, correct, re-trigger |

`stalled` and `skipped` both show a green check, which is why they need their
own detection signals — see [references/traps.md](references/traps.md) for the
cause behind each and how to correct it. Correct the cause before
re-triggering, and cap retries at two per cause so the loop cannot spin on one
broken reviewer.

### 5. Act on findings

1. Present the findings to the user, grouped by surface, before changing code.
2. Apply the fixes.
3. Reply in-thread on the surface that raised each finding, so the reviewer
   and the next human reader can see how it was addressed.
4. Run the local gate. A round spent discovering a broken fix is a round
   wasted.
5. Push — which starts the next round at step 2.

Route findings; do not adjudicate them. When a finding looks wrong, say so to
the user and let them decide rather than silently declining it.

### 6. Report and stop

Report rounds run, findings addressed, the final verdict per surface, and the
rounds skipped as unchanged. Leave the PR open and say explicitly that a human
still has to approve and merge it.

Stop at the round cap the same way: report where the loop got to and what is
still outstanding. Hitting the cap usually means the reviewer and the fixer
disagree, which is a human's call.

## Round ledger

Print this table after every round, so a human reading the session can see the
state and take over at any point:

| Round | Head SHA | Fingerprint | Surface verdicts | Outcome | Action |
| --- | --- | --- | --- | --- | --- |
| 1 | `a06e93d` | `4f2c…` | claude: FINDINGS (3) · codex: 1×P2 | findings | fixed, replied, pushed |
| 2 | `682396c` | `4f2c…` | — | unchanged | prior verdict carried |

The ledger is the durable state the loop otherwise rediscovers every session:
which round is in flight, what was already reviewed, and which surface still
owes a verdict.
