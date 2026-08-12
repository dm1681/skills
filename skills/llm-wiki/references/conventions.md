# Wiki conventions

The defaults below are what `scripts/wiki_lint.py` checks. They are a starting
point, not a standard — change them to fit the domain, but change them in the
wiki's `AGENTS.md` *and* pass `--no-<check>` flags to the linter for whatever
no longer applies, so the mechanical pass keeps telling the truth.

## Layout

```
raw/                  sources, immutable, any format
wiki/
  index.md            catalog of every page
  log.md              chronological, append-only
  sources/            one page per ingested source
  entities/           people, organizations, products, places, characters
  concepts/           ideas, mechanisms, themes, methods
  syntheses/          answers and comparisons filed back from queries
AGENTS.md             the schema
```

`entities/`, `concepts/`, and `syntheses/` are the generic split. A domain
usually wants its own: a book wiki wants `characters/` and `threads/`, a
research wiki wants `papers/` and `claims/`. Decide once, record it in
`AGENTS.md`, and use it consistently — the linter reads whatever directories
exist.

## File naming

Kebab-case slugs matching the page title: `wiki/entities/ada-lovelace.md`.
The slug is the link target, so renaming a page means updating its inbound
links — the linter catches the ones missed.

## Page format

```markdown
---
type: entity
title: Ada Lovelace
sources: [analytical-engine-memoir, hopper-biography]
updated: 2026-04-02
---

One-paragraph answer to "what is this page about" — written so it can be read
alone, because the index shows only its first line.

## <Section per aspect>

A claim, with its citation attached [[sources/analytical-engine-memoir]].

## Open questions

- What the wiki does not yet know, and what source would answer it.
```

Rules that matter:

- **Every claim carries a citation** to the source page it came from. A claim
  with no citation is either the agent's inference — mark it inline as such —
  or a bug.
- **`sources:` lists every source page that fed this one.** It is how a lint
  pass finds pages that predate a recent ingest.
- **`updated:` is the last substantive revision**, not the last touch.
- **Open questions are part of the page.** They are what turns a wiki into a
  research direction instead of an archive.

## Source pages

Source pages additionally record where the raw file lives, which is how the
linter tells an ingested source from an un-ingested one:

```markdown
---
type: source
title: The Analytical Engine, a memoir
source: raw/analytical-engine-memoir.md
date: 1843-01-01
updated: 2026-04-02
---
```

The `source:` path must be the real relative path of the raw file.

## Links

Wikilinks — `[[entities/ada-lovelace]]` or `[[ada-lovelace|Lovelace]]`. Both
the full relative path and the bare slug resolve, but be consistent within one
wiki. Standard markdown links work too and are checked the same way.

Link generously. The cross-references are the artifact; a page with no
outbound links is a document that happens to live in a wiki.

## index.md

Content-oriented, grouped by category, one line per page:

```markdown
## Entities

- [[entities/ada-lovelace]] — mathematician, first published algorithm (3 sources)
```

Updated on every ingest. It is read first on every query, so its one-line
summaries do real work — write them to discriminate between pages, not to
restate their titles.

## log.md

Chronological and append-only. Every entry starts with the same prefix so the
file stays greppable:

```markdown
## [2026-04-02] ingest | The Analytical Engine, a memoir

Touched: [[sources/analytical-engine-memoir]], [[entities/ada-lovelace]],
[[concepts/stored-program]]. Contradiction: the memoir dates the engine's
design to 1837, against 1834 in [[sources/babbage-letters]].
```

`## [YYYY-MM-DD] <ingest|query|lint> | <title>` — the linter checks this
shape. It makes `grep "^## \[" log.md | tail -5` a session-start briefing.

Newest entries at the bottom. Never rewrite history in this file; a correction
is a new entry.
