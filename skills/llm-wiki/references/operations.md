# The three operations

Ingest, query, and lint. Each one ends by writing something durable — a page,
a revision, or a log entry. An operation that leaves the wiki unchanged did
not happen.

## Ingest

A new source lands in `raw/` and the user asks for it to be processed.

1. **Read the whole source.** Not a skim, and not the first chunk. If it is
   long, read it in passes and keep notes; the summary is written from the
   whole thing.
2. **Handle images separately.** Markdown with inline images cannot be read in
   one pass. Read the text first, then view the referenced images that carry
   real information (figures, charts, diagrams) — skip decorative ones.
3. **Discuss the takeaways with the user before writing.** Three to five
   points, in the session, not a file. This is where the user redirects
   emphasis, and it costs one exchange. Batch ingestion without this step is
   the user's explicit call, not the default.
4. **Write the source page** — `wiki/sources/<slug>.md`. Format in
   `conventions.md`.
5. **Find every page the source touches.** Grep the wiki for the entities and
   concepts the source names, and read `index.md`. Do not rely on memory of
   what exists.
6. **Revise those pages.** For each one, ask what this source *changes*:
   - New claim → add it with its citation.
   - Supporting evidence → strengthen the existing claim, add the citation.
   - Contradiction → record both sides. Never silently overwrite. Mark which
     is more recent and which the wiki currently leans toward, and why.
   - Nothing → leave it. A no-op edit is worse than no edit; it destroys the
     signal in `git log`.
7. **Create pages for entities and concepts that earn one.** An entity earns a
   page when two or more sources reference it, or when one source treats it as
   a subject rather than a mention.
8. **Update `index.md`** with any new pages.
9. **Append one `log.md` entry** naming the source and listing the pages
   touched.
10. **Report the blast radius** to the user: the source page, the pages
    revised, any contradiction surfaced. That last item is the one they care
    about most — lead with it when there is one.

A source that touches only its own summary page is a signal, not a success.
Either the wiki has no coverage of this area yet (fine, early on), or step 5
was done from memory.

## Query

The user asks a question against the wiki.

1. **Read `index.md` first**, then the pages it points at. Grep for terms the
   index does not cover.
2. **Answer from wiki pages, citing them.** When a wiki page's claim matters
   to the answer, follow it back to the source page and cite the source, not
   just the wiki page — the wiki is a cache, the sources are the truth.
3. **Say when the wiki cannot answer.** A gap is a finding: name it, and offer
   either a web search or a source the user could add. Never fill a gap with
   unsourced model knowledge silently — if unsourced reasoning is included,
   mark it as such inline.
4. **Choose the output form the question deserves** — prose, a comparison
   table, a chart, a slide deck. The user's question implies the shape.
5. **Offer to file the answer back into the wiki.** Comparisons, syntheses,
   and discovered connections are new knowledge; leaving them in chat history
   is the one place they cannot compound. Ask before filing — not every answer
   deserves a page — and log the ones filed.

## Lint

A periodic health check, run when the user asks or when a batch of ingests
lands.

Run the mechanical pass first — it is fast and its output narrows the semantic
pass:

```sh
python3 <skill-root>/scripts/wiki_lint.py <wiki-root>
```

Then do the half no script can do:

- **Contradictions between pages.** Two pages asserting incompatible things
  without either acknowledging the other.
- **Stale claims.** A page whose claim a newer source superseded — check
  claims whose source page predates recent ingests.
- **Missing pages.** A concept mentioned across several pages that has none of
  its own.
- **Missing cross-references.** Two pages about clearly related things that do
  not link to each other.
- **Thin pages.** A page that is one line and has not grown in many ingests —
  either fold it into its parent or note what source would fill it.
- **Gaps worth filling.** Questions the wiki raises but does not answer, and
  the sources or searches that would close them.

Present findings as a list the user can act on, grouped by whether the agent
can fix it now (missing cross-references, orphan pages, index drift) or needs
the user (a new source, a judgment call on which of two contradicting claims
to lean toward). Fix the first group on approval; never act on the second
alone.

Close the pass with a `log.md` entry recording what was checked and fixed.
