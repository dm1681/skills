# Review surfaces

A **surface** is one reviewer that reports on a PR. Which surfaces exist
varies per repository, so discover them rather than assuming the set below,
and read a verdict only in the way that surface actually reports one.

## What to discover

- **Surfaces** — which reviewers actually comment on this repo's PRs, and per
  surface the four facts below.
- **Deterministic gate** — the checks branch protection actually requires,
  rather than whichever look important:

  ```bash
  gh api repos/<owner>/<repo>/rulesets
  gh api repos/<owner>/<repo>/branches/<base>/protection
  ```

  Derive it from that configuration alone, whichever app or workflow produces
  each check. Model reviewers are *usually* comment-only, but one can also
  produce a required check — and then a clean comment from it is not a
  substitute for that check concluding successfully. Excluding a check because
  its producer also comments removes a real merge gate.
- **Local gate** — the verification command the repo tells contributors to run
  before pushing (`AGENTS.md`, `CLAUDE.md`, `package.json` scripts, `Makefile`).
- **Round cap** — how many rounds before stopping and handing back. Default 5.

Many repositories have no model reviewer at all. When discovery finds none,
say so and offer the choice rather than waiting on a surface that will never
report: run the loop against the deterministic gate alone, or stop and
provision a reviewer first. This skill drives a pipeline that already exists.

## Discovering the active surfaces

```bash
ls .github/workflows/                                   # which reviewers are wired up
gh pr list --state merged --limit 5 --json number       # then, per PR:
gh api --paginate repos/<owner>/<repo>/issues/<n>/comments --jq '.[].user.login' | sort -u
gh api --paginate repos/<owner>/<repo>/pulls/<n>/reviews  --jq '.[].user.login' | sort -u
```

**Paginate every query whose result feeds a verdict.** `gh api` fetches all
pages only under `--paginate`; without it a `VERDICT:` comment past the first
page is invisible and the round classifies as stalled when it was clean.

Bot logins end in `[bot]`. A workflow file present but never commenting on
recent PRs is *probably* inactive — but a reviewer added or enabled since
those PRs merged has had no chance to comment yet. Before excluding a
configured surface, check the current PR for its activity and its workflow's
triggers; exclude it only when both come up empty, and say that you did.

Past bot activity is the signal because app installation is not readable with
an ordinary token: `repos/<owner>/<repo>/installation` answers `401` without an
app JWT, and `/user/installations` answers `403` unless the token was issued
for a GitHub App. Codex and CodeRabbit are apps, so their presence can only be
inferred from what they have commented on. Claude Code Review is a workflow
file, so it is readable directly — and `gh api repos/<owner>/<repo>/actions/secrets
--jq '.secrets[].name'` confirms its API key exists, given repo admin.

When discovery finds no model reviewer at all, report that and fall back to
the deterministic gate rather than reporting a clean verdict nobody issued.
Installing one is out of scope here: a workflow file can be written into a
repo, but Codex and CodeRabbit are GitHub Apps a human must authorize through
GitHub's UI, so no agent can provision them end to end.

For each active surface, establish four things before the first round: how it
announces that it started, how it reports a verdict, how to reply to a finding
in-thread, and **how to rerun it**. A surface missing the first two cannot be
classified — see "Surfaces with no explicit verdict" below.

The rerun matters because `gh pr close && gh pr reopen` is not universal: it
fires the `reopened` event, so a workflow subscribing only to `synchronize`
ignores it, and a GitHub App reruns on its own triggers. Read the workflow's
`on:` block, or the app's documented command comment, and record the rerun
that surface actually answers to. Falling back to close/reopen for a surface
that ignores it produces another verdict-less round and burns a retry.

## Claude Code Review

`anthropics/claude-code-action`, posting as `claude[bot]`. Three comment kinds
per round:

- `🔍 Review started — ... head <sha>` — posted before the diff is read. This
  implements the announce-before-reviewing convention in this repo's
  `AGENTS.md`; its absence means the round never really began.
- A tracking comment (`**Claude finished** ...`) carrying a phase checklist —
  the live in-progress surface. Unchecked boxes with no finished comment mean
  the round died mid-review (trap 2).
- `✅ Review finished — head <sha>` whose **second line is exactly**
  `VERDICT: CLEAN` or `VERDICT: FINDINGS (<count>)`.

```bash
gh api --paginate repos/<owner>/<repo>/issues/<n>/comments \
  --jq '.[] | select(.user.login=="claude[bot]") | .body'
```

The verdict line exists so tooling can classify a round without parsing prose.
Key on it, match its head SHA against the head under review, and treat its
absence as a stalled round.

Reply to a finding by commenting on the PR, quoting the finding.

## Codex

`chatgpt-codex-connector[bot]` posts a PR review plus inline comments badged by
priority (P1/P2/…). Read the review body for the summary and the inline
comments for the findings:

Both endpoints return **every round's** reviews and comments, so filter to the
current head before classifying anything. A review carries `commit_id`; each
inline comment carries `original_commit_id` and the `pull_request_review_id`
of the review it belongs to.

Filter on **both** the head and the bot. Selecting the newest review for the
head alone picks up whatever a human or another bot submitted after this
surface did, and reads that stranger's approval as this surface's verdict.

```bash
head=$(gh pr view <n> --json headRefOid --jq .headRefOid)
bot=chatgpt-codex-connector[bot]
# this surface's most recent review for this head, and its id
gh api --paginate repos/<owner>/<repo>/pulls/<n>/reviews \
  --jq "[.[] | select(.commit_id==\"$head\" and .user.login==\"$bot\")] | last"
# only the comments belonging to that review
gh api --paginate repos/<owner>/<repo>/pulls/<n>/comments \
  --jq ".[] | select(.pull_request_review_id==<review-id>)"
```

Skipping that filter fails in both directions: a prior round's neutral review
gets reused as a clean verdict while the current review is still pending, and
stale inline findings make a genuinely clean current review look dirty.

Reply in-thread on the comment that raised the finding:

```bash
gh api -X POST repos/<owner>/<repo>/pulls/<n>/comments/<comment-id>/replies \
  -f body="Fixed in <sha> — <what changed>"
```

Treat a review **for the current head** with no inline comments and an
approving or neutral body as that surface's clean verdict.

## CodeRabbit

`coderabbitai[bot]` posts a walkthrough summary, and — depending on plan and
configuration — line-level inline comments badged by severity
(Major/Minor/Trivial). Read both; treat the inline comments as findings.

Do not assume the summary-only shape: an earlier draft of this file asserted
CodeRabbit "never" posts line-level findings on the free plan, and CodeRabbit
posted eighteen of them on the PR that added the file. Check what it actually
posted on this repo rather than trusting a plan-shaped rule.

Scope its findings to the current head exactly as for Codex: select the review
whose `commit_id` matches, then read only the comments carrying that review's
`pull_request_review_id`. Reading every inline comment instead keeps findings
from earlier heads alive and the loop dirty forever.

It enforces an hourly review limit, and reports hitting it as a **passing
check reading `Review rate limited`** — observed on the PR that added this
file. That is not a clean verdict: the surface did not review this head.
Record the round as **unresolved** for CodeRabbit rather than letting it
satisfy the clean predicate, and either wait the limit out and re-trigger, or
finish with an explicitly reduced-confidence verdict that names the surface
which never reported.

## Deterministic CI

```bash
gh pr checks <n>
```

This is the gate that actually matters; model reviewers are comment-only and
gate nothing. Prefer a check known to be deterministic. Before reporting a
failing check as a regression, confirm it fails only on this branch — some
suites fail identically on an untouched base (trap 8):

```bash
gh run list --branch <base> --workflow <gate> --limit 5
```

## Surfaces with no explicit verdict

A surface that reports nothing when it finds nothing cannot be distinguished
from a broken one (trap 4). Options, best first:

1. Ask the repo to add an explicit verdict line to that reviewer's output.
2. Fall back to the run's own success plus a non-trivial duration, and report
   the reduced confidence in the final summary.

Never infer clean from silence without saying that is what you did.
