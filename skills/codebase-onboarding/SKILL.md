---
name: codebase-onboarding
description: Onboard someone to a codebase with an interactive, self-contained HTML flow diagram in the Catppuccin Mocha theme - an architecture map, one or more end-to-end flows, or both - where steps are grouped into one container per source file, shapes, colours and arrow styles carry defined meanings shown in a live legend, and every node reveals its real, syntax-highlighted source excerpt on hover. Use when a user is new to a repository, asks to be onboarded, wants a visual map of how a codebase fits together, asks how a request, command or feature flows through the code, or wants an onboarding page or diagram to share with a teammate.
version: 1.0.0
---

# Codebase onboarding

Turn a repository into an onboarding page a newcomer can explore: a map of
where things live, flows that trace real execution from entry to exit, or
both. You write a small JSON model; the bundled script pulls the real code
excerpts out of the repository and renders one self-contained HTML file (no
network, no dependencies beyond Python 3.9+).

## 1. Pick the scope

Decide from the request, and ask one question only if it is truly unclear:

| The user says… | Build |
|---|---|
| "onboard me", "I'm new to this repo" | **both**: an architecture view plus 1–3 flows for the paths they will touch first |
| "how is this organised", "where does X live" | an **architecture** view |
| "how does login / checkout / `cmd foo` work" | a **flow** view per path named |

If you would be guessing which flows matter, ask: "Which 1–3 things should a
newcomer be able to trace first?" and suggest candidates from the entry
points you found.

## 2. Explore before drawing

1. Find the entry points: README, manifest scripts (`package.json`,
   `pyproject.toml`, `Makefile`), `main`, route tables, CLI definitions.
   If `graphify-out/graph.json` exists, query it first.
2. For each flow, trace from the entry to every exit and failure. Read each
   hop; record `path:start-end` for the few lines that show the idea.
3. For the map, list the components a newcomer must know (not every file)
   and the dependencies between them.

Never draw an edge or a branch you have not seen in the code.

## 3. Write the model

Write `docs/onboarding/<name>.json` in the target repository. The field
reference and an example are in [references/model.md](references/model.md);
what each shape, colour and arrow means — and when to use it — is in
[references/visual-language.md](references/visual-language.md). The rules
that matter most:

- **One container per file.** A `file` group holds only nodes whose excerpt
  comes from that file; the build rejects anything else.
- **Kinds carry meaning, not decoration.** Every flow starts at an `entry`
  and ends at an `exit` or `error`; every `decision` fans out through
  labelled `branch` edges; red is only for failure.
- **Number the steps** of a flow (`step: 1, 2, …`) in reading order. The
  page's ◀ ▶ tour follows them.
- **Small excerpts.** ≤16 lines, ≤120 characters a line. Add `contains` to
  the ones that matter so drift fails the build instead of lying.
- **6–20 nodes a view.** Split bigger flows and link them with `drill`.
  In `both` mode, give architecture components a `drill` to their flow.

## 4. Build

```bash
python3 <skill-dir>/scripts/build_onboarding.py docs/onboarding/<name>.json --repo .
```

It writes `docs/onboarding/<name>.html` (override with `--out`). It reports
every problem at once; fix the model and rebuild — never hand-edit the HTML.
`--check` validates without writing. Excerpt links point at the web host
(GitHub/GitLab) at the exact commit when the worktree is clean;
`--editor-links` links to `vscode://` on this machine instead — handy
locally, but do not commit a page built that way.

## 5. Look at it

Open the page in a browser (serve it with `python3 -m http.server` if your
browser tool blocks `file://`). Check, per view:

- containers read as files, and a newcomer can follow the numbered steps;
- hovering a node shows the right code and lights up its neighbours;
- no label collides with a container header or another label badly enough
  to hide it — if one does, shorten the label or restructure the view.

Screenshot it if you can, and fix what looks wrong before handing it over.

## 6. Hand over

Tell the user the file path, how to open it, and the one flow to start
with. Offer to publish it as a shareable page if a publishing or artifact
tool is available (the file is self-contained, so it can be published
as-is). Suggest committing the `.json` next to the `.html` so the page can
be rebuilt when the code changes.

## Page features (for reference in your hand-over)

- Tabs per view; architecture nodes with "open ⤵" jump to their flow.
- Hover: kind, summary, file:lines link and highlighted excerpt; neighbours
  lit, everything else dimmed. Click pins it in the side panel with
  "Comes from" / "Leads to" navigation.
- Legend lists only the kinds the view uses; hovering an entry highlights
  every shape or arrow of that kind.
- Both side panels share one width and collapse to a rail (`[` and `]`).
- Keys: ← → walk steps, `/` search, `f` fit, `Esc` clear; drag to pan,
  wheel to zoom. The URL hash deep-links the view and selected node.
