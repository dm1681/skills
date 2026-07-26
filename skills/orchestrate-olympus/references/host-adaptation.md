# Olympus host adaptation

The orchestration contract is host-neutral. "Parent session", "subagent",
"task ID", "follow-up turn", "wait", "pin", and "archive" name capabilities,
not features of one product. Codex, Claude Code, Cursor, Copilot, and other
agent hosts expose these capabilities differently; this reference defines how
to map them and what to do when one is missing. It never expands authority:
every fallback obeys the same dispatch, merge, and pause controls.

## Required host capabilities

These are hard requirements. If the host cannot provide one and no fallback
below applies, enter `ESCALATED` and report the missing capability instead of
improvising a weaker substitute:

- a resident parent session that can keep working across child turns without
  terminating;
- child subagents or sessions with a stable identifier the parent can record;
- delivery of follow-up input to a child, or the one-shot re-brief fallback;
- bounded waits on child results or external conditions;
- an isolated git worktree per mutating child;
- authenticated GitHub CLI or API access.

Use the host's stable identifier for every task and subagent exactly as the
host exposes it: a UUID, slug, session path, or other token is equally valid.
Record it verbatim in signatures, hidden markers, and the checkpoint. If the
host exposes no identifier, mint one stable lane-scoped identifier, record it
in the checkpoint at creation, and reuse it for the child's lifetime.

## Capability fallbacks

| Capability | If the host lacks it |
| --- | --- |
| Task pinning | Skip pinning; standard task titles and the checkpoint carry the same recovery information. |
| Follow-up turns to a reusable child | Create a fresh one-shot child per round from the same role prompt, re-briefed with the current exact head, finding ledger, and scope version. It inherits the role's identity rules; record each new ID. |
| Parallel child slots | Run the Standards and Spec axes sequentially; parallelism is an optimization, never an acceptance requirement. |
| Bounded external waits or a Watcher | Wait inside the parent with the same explicit condition, evidence source, and finite timeout. Never convert this into unbounded or fixed-cadence polling. |
| Independent subagents entirely | `ESCALATED`. Reviewer and source-axis independence cannot be satisfied from the parent's own context; do not self-review. |
| Archiving completed children | Leave the child session in place and record its terminal state in the checkpoint. |

## Invocation

Hosts invoke skills differently: `$orchestrate-olympus` on Codex,
`/orchestrate-olympus` or the Skill tool on Claude Code, and a plain
instruction naming the skill elsewhere. Prompts in this collection say "use
the orchestrate-olympus skill"; substitute the host's own invocation syntax
when rendering a prompt for a specific host.

## Hosted cloud reviews

Never request a hosted cloud review (for example, Codex Cloud) by GitHub
comment, regardless of host. No hosted review service is an Olympus phase,
readiness gate, repair actor, or merge requirement. Treat any that appears as
external feedback under the normal review-boundaries rules.

## Artifact workspace

Prefer repository-tracked evidence. Otherwise use the host's durable artifact
or visualization workspace when one exists. Never make an ephemeral local path
the only handoff.

## Script runtime

`scripts/checkpoint.py` needs any Python 3.9+. Invoke it with the interpreter
the host provides: `python3` on most Unix hosts, `python` or `py` on Windows,
or `uv run python` inside this repository's synced environment.
