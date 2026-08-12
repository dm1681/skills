# Traps

Traps 1–8 each produce a **green check while nothing useful happened**, which
is why a round's outcome has to be read from a posted verdict rather than from
CI status. Traps 9 and 10 are different: they break the loop's own recovery
and waiting machinery. All of them were found by losing a real round to them —
1–8 while driving two pull requests by hand, 9 and 10 while reviewing this
skill.

## 1. Workflow-file mismatch silently disables the review

`claude-code-action` refuses to run when the PR branch's copy of the workflow
file differs from the base branch's. It logs `Workflow validation failed` and
reports **success in ~15 seconds**. Any change to the review workflow on the
base branch therefore disables reviews on every open PR until the base is
merged into each branch.

**Detection** — run duration under ~30s, or in the run log:

```bash
gh run view <run-id> --log | grep -i "workflow validation"
# "Action skipped due to workflow validation error"
```

**Recovery** — merge the base branch into the PR branch and push. Handle this
in pre-flight; it is the cheapest trap to prevent and the most expensive to
discover on round four.

## 2. A round can end "successfully" mid-review

Ending the agent's turn in a non-interactive CI run terminates the job
immediately. A reviewer that launches sub-agents in the background and ends its
turn to wait for them dies silently: tracking checklist half-ticked, no
finished comment, check green.

**Detection** — a tracking comment with unchecked boxes and no matching
`✅ Review finished` for that head SHA.

**Recovery** — re-trigger using *this surface's* rerun, recorded in
[surfaces.md](surfaces.md). Close/reopen fires `reopened`, which a
`synchronize`-only workflow ignores, so reaching for it by reflex spends a
retry and produces another verdict-less round. The durable fix belongs in the
reviewer's workflow: run sub-agents synchronously so the turn does not end
while work is outstanding.

## 3. Permission denials exhaust the turn budget

A CI reviewer whose sub-agents reach for non-allowlisted tools burns its turns
on denials and stalls before posting findings — 11 denials in one observed run.

**Detection** — repeated permission-denial lines in the run log, and a round
that stalls at the same phase every retry.

**Recovery** — extend the workflow's allowlist to the read-only tools a review
actually needs: `gh pr view`, `gh pr diff`, `gh pr comment`, `gh issue view`,
`git log`, `git show`, `git diff`, `git fetch`.

## 4. A silent clean pass is indistinguishable from a broken reviewer

Before lifecycle comments existed, a clean review posted nothing at all — no
comment, no review, no check summary.

**Detection** — impossible by construction, which is the point.

**Recovery** — require an explicit verdict. Never infer clean from silence.

## 5. Re-reviewing byte-identical diffs is the largest source of waste

Merging the base branch — often forced by trap 1 — produces a new head SHA
whose substantive diff is unchanged. A naive loop pays for a full re-review.

**Detection** — the **full** fingerprint matches the previously reviewed head:
both the patch hash and the base revision it was reviewed against.

```bash
git diff "origin/<base>...<head-sha>" | git hash-object --stdin
git rev-parse "origin/<base>"
```

**Recovery** — carry forward the **model-review verdicts only**, and only when
both halves match and that prior verdict was explicit. Record the round as
`unchanged` in the ledger instead of counting it as a fresh round.

Three ways the shortcut turns into a false clean, so none of them is optional:
a moved base is a different integration even over identical patch bytes; a
rewritten commit keeps the patch identical while changing metadata a DCO or
signed-commit check reads, so **the deterministic gate always re-runs for the
current head**; and carrying an unresolved or stalled round forward
manufactures a verdict nobody issued.

## 6. Drafts still trigger reviews

The `synchronize` event fires on pushes to draft PRs, so iterating in a draft
does not avoid expensive rounds unless the workflow filters on
`github.event.pull_request.draft == false`.

**Recovery** — expect rounds on drafts, or check for that filter before
promising the user that draft pushes are free.

## 7. `gh` throws transient TLS errors

`certificate signed by unknown authority` appears intermittently on otherwise
valid calls.

**Recovery** — retry the call. Treat it as a hard failure only after it
repeats.

## 8. Environment-flaky test suites poison the signal

Some suites fail identically on an untouched base branch — on the reference
repo, several Playwright `[mobile-safari]` specs. A failure there means nothing
without an A/B run against base.

**Recovery** — gate on a check known to be deterministic, or compare the
failure against a recent base-branch run before reporting it as a regression.

## 9. A failed reopen leaves the PR closed

`gh pr close <n> && gh pr reopen <n>` is two calls. When the first succeeds
and the second fails — permissions, or the transient error in trap 7 — the
loop has closed a pull request and moved on. This is the worst state the
procedure can produce, and it produces it while trying to recover.

**Detection** — after any re-trigger:

```bash
gh pr view <n> --json state --jq .state     # expect OPEN
```

**Recovery** — retry the reopen. If it still fails, stop the loop and report
the PR as closed and needing a human. Never leave a closed PR behind an
unreported round.

## 10. Polling `gh pr checks` on exit status spins forever

`gh pr checks` exits non-zero both when no checks are reported *and* when a
check has failed, so `until gh pr checks <n>; do ...; done` never terminates
on a red gate — and, written without a sleep, spins as a busy loop.

**Recovery** — poll for the suite's *existence* instead, then hand off to the
watcher:

```bash
until [ "$(gh pr view <n> --json statusCheckRollup --jq length)" -gt 0 ]
do sleep 10; done
```
