# Schema template

Write this to `AGENTS.md` at the wiki root during bootstrap, filled in for the
user's domain. Also write a one-line `CLAUDE.md` next to it containing
`@AGENTS.md`, so Claude Code and other agents load the same file.

This is the wiki's constitution and the reason a later session behaves like a
maintainer instead of a chatbot. Keep it current: whenever a convention is
decided mid-session, write it here before the session ends.

Placeholders are in `<angle brackets>`.

---

```markdown
# <Wiki name>

An agent-maintained wiki about <domain>. Sources are <what the sources are>.

Built on the `llm-wiki` pattern: `raw/` is immutable and user-owned, `wiki/`
is written entirely by the agent, and this file is the schema both follow.

## Rules

- Never modify anything under `raw/`. Read only.
- Never ask the user to write a wiki page. The agent writes all of `wiki/`.
- Every claim in a wiki page carries a citation to its source page.
- An ingest revises existing pages; writing only a summary page is incomplete.
- Contradictions are recorded with both sides and their sources, never
  silently resolved.
- Commit after each operation, so every ingest is one reviewable diff.

## Layout

<the directory layout actually in use — see the skill's conventions.md>

## Page types

| Type | Directory | Earns a page when |
| --- | --- | --- |
| source | `wiki/sources/` | Any ingested source. |
| <entity> | `wiki/<entities>/` | <two sources reference it, or one treats it as a subject> |
| <concept> | `wiki/<concepts>/` | <it is referenced from two or more pages> |
| synthesis | `wiki/syntheses/` | A query answer worth keeping. |

## Workflows

**Ingest.** <How this user likes it: one at a time with discussion, or
batched. Which sections a source page gets. What the agent should emphasize
for this domain.>

**Query.** <Preferred answer formats. Whether to file answers back by default
or ask each time.>

**Lint.** <How often. Which checks matter most here.>

## Conventions decided so far

<Append every convention agreed mid-session: naming, how dates are recorded,
how uncertain claims are marked, which distinctions this domain cares about.
This section is the one that grows.>

## Health check

    python3 <path-to-skill>/scripts/wiki_lint.py .
```

---

## Filling it in

Two questions decide most of it: what the wiki is about, and what the sources
are. Ask them, then propose the page types out loud before writing the file —
a wrong page-type split is cheap to fix on day one and expensive on day
thirty.

Leave "Conventions decided so far" empty at bootstrap. It fills itself as the
user corrects the agent, and that accumulation is what makes session ten
better than session one.
