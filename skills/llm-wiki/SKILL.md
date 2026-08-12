---
name: llm-wiki
description: Build and maintain a persistent, agent-written markdown wiki over a growing collection of sources - ingest each source into interlinked pages, answer questions from those pages, and lint the wiki for contradictions and staleness. Use when the user wants a knowledge base that compounds across sessions (research, reading a book, personal notes, team knowledge, competitive analysis) rather than one-shot retrieval or a single research write-up.
---

# LLM wiki

A wiki the agent writes and maintains, sitting between the user and their raw
sources. The point is *accumulation*: knowledge is compiled once and then kept
current, instead of being re-derived from raw documents on every question.

The user curates sources, directs the analysis, and asks the questions. The
agent does everything else — summarizing, cross-referencing, filing, and the
bookkeeping that makes a knowledge base survive its second month.

Adapted from Andrej Karpathy's "LLM Wiki" gist. The pattern is deliberately
modular: instantiate the parts that fit this domain and skip the rest.

## The three layers

| Layer | Path | Who writes it |
| --- | --- | --- |
| Raw sources | `raw/` | The user. **Immutable** — read, never modify. |
| The wiki | `wiki/` | The agent, entirely. |
| The schema | `AGENTS.md` at the wiki root | Agent and user, co-evolved. |

The schema is the load-bearing file. It records this wiki's conventions —
page types, naming, citation format, what an ingest touches — so the next
session is a disciplined maintainer rather than a fresh chatbot. Everything
learned about what works here goes back into it.

## First run: bootstrap

Do not scaffold silently. Ask the user for the domain and the shape of their
sources first, because both decide the page types.

1. **Ask two questions.** What is this wiki *about*, and what will the sources
   be (papers, articles, chapters, transcripts, journal entries)? Nothing else
   is needed to start.
2. **Create the layout** — `raw/`, `wiki/`, `wiki/index.md`, `wiki/log.md`,
   and `AGENTS.md`. Start `AGENTS.md` from
   [`references/schema-template.md`](references/schema-template.md), filled in
   for the answers above.
3. **`git init`** if the directory is not already a repo. The wiki is a folder
   of markdown; version history and diffs come free, and the user reviews the
   agent's edits as diffs.
4. **Ingest one source end to end** before scaffolding page types
   speculatively. The first real source reveals the right structure faster
   than any planning does.
5. **Tell the user where it lives** and suggest opening `wiki/` in Obsidian
   (or any markdown browser) alongside the session — reading the pages as they
   change is how the user stays in control of the wiki's direction.

## Operations

Three operations, detailed in
[`references/operations.md`](references/operations.md) — read it before
running any of them for the first time.

- **Ingest** — a new source arrives. Read it, discuss the takeaways, write its
  summary page, then *revise every existing page it touches* and append to the
  log. One source routinely touches 10–15 pages.
- **Query** — answer from the wiki's pages, with citations. File good answers
  back as new pages so explorations compound like sources do.
- **Lint** — a periodic health check for contradictions, stale claims,
  orphans, and gaps.

Page formats, `index.md` and `log.md` conventions, and the citation rules are
in [`references/conventions.md`](references/conventions.md).

## The rule that makes this different from RAG

**Ingest revises; it does not append.** Writing a summary page and stopping is
the failure mode that turns this into a folder of unread summaries. The value
is in the second half of the ingest: finding the pages whose claims the new
source strengthens, weakens, or contradicts, and editing them.

When a new source contradicts an existing page, never silently overwrite.
Record both claims with their sources and say which is more recent and why the
wiki now leans one way — a contradiction the user can see is worth more than a
clean page that hid it.

## Mechanical lint

Structural checks that need no judgment are scripted, so the agent's attention
goes to the semantic half of a lint pass:

```sh
python3 <skill-root>/scripts/wiki_lint.py <wiki-root>
```

It reports broken links, orphan pages, pages missing from `index.md`, index
entries with no page, un-ingested sources in `raw/`, and malformed log
entries. Pass `--strict` to exit non-zero when anything is found (for a
pre-commit hook). It cannot see contradictions or staleness — that half of the
lint pass is the agent's, per `references/operations.md`.

## Scale, honestly

`index.md` plus grep carries a wiki to roughly a hundred sources and a few
hundred pages, with no embedding infrastructure. Past that, add a real search
tool over the markdown — [`qmd`](https://github.com/tobi/qmd) is local, hybrid
BM25/vector, and ships both a CLI and an MCP server. Do not reach for it
early; the index file is genuinely enough at small scale, and say so if the
user asks for search before they need it.

## When not to use this

- **A one-shot question or write-up** — no wiki survives to justify the
  overhead. Just research and answer.
- **Code understanding** — a codebase already has structure to exploit; a
  knowledge-graph tool over the repo fits better than a hand-built wiki.
- **The user only wants notes stored** — if nothing is going to be re-read or
  revised, this pattern is maintenance for its own sake. Say so.
