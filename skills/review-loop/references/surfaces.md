# Review surfaces

A **surface** is one reviewer that reports on a PR. Which surfaces exist
varies per repository, so discover them rather than assuming the set below,
and read a verdict only in the way that surface actually reports one.

## Discovering the active surfaces

```bash
ls .github/workflows/                                   # which reviewers are wired up
gh pr list --state merged --limit 5 --json number       # then, per PR:
gh api repos/<owner>/<repo>/issues/<n>/comments --jq '.[].user.login' | sort -u
gh api repos/<owner>/<repo>/pulls/<n>/reviews  --jq '.[].user.login' | sort -u
```

Bot logins end in `[bot]`. A workflow file present but never commenting on
recent PRs is not an active surface — treat it as inactive and say so, rather
than waiting on a verdict that will never arrive.

For each active surface, establish three things before the first round: how it
announces that it started, how it reports a verdict, and how to reply to a
finding in-thread. A surface missing the first two cannot be classified — see
"Surfaces with no explicit verdict" below.

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
gh api repos/<owner>/<repo>/issues/<n>/comments \
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

```bash
gh api repos/<owner>/<repo>/pulls/<n>/reviews
gh api repos/<owner>/<repo>/pulls/<n>/comments
```

Reply in-thread on the comment that raised the finding:

```bash
gh api -X POST repos/<owner>/<repo>/pulls/<n>/comments/<comment-id>/replies \
  -f body="Fixed in <sha> — <what changed>"
```

Treat a review with no inline comments and an approving or neutral body as
that surface's clean verdict.

## CodeRabbit

On the free plan CodeRabbit posts a walkthrough summary only — never
line-level findings — and enforces an hourly review limit. It is
informational: read it for context, never wait on it for a verdict, and never
count its silence as either clean or stalled.

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
