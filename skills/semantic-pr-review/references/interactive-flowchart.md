# Interactive PR Flowchart

The explorer is the shared flow-diagram page with this skill's extension
injected. The page owns the canvas, layout, legend, hover cards, details
panel, step tour, search and deep links; the extension (`assets/pr-extension.*`)
owns everything about the pull request. Read
[visual-language.md](visual-language.md) for what shapes, colours, arrows and
borders mean — those meanings are fixed and shared with every other diagram.

## Composition

The page draws top to bottom in runtime order. The scaffold derives it from
the model's paths:

- **Containers are systems.** Each node sits in the solid-bordered container
  of its `system`, headed with the system's label. Branches that belong to
  different systems sit side by side; their reconnection at the convergence
  node is visible as arrows crossing back.
- **Kinds come from the runtime role** unless a node names one. The first
  node is the `entry` (green stadium), a dispatch that fans out to several
  branches is a `decision` (yellow diamond), the last node is the `exit`
  (pink double stadium), and the rest are `step`s. Set `kind` on a node that
  is something else — a `store`, an `external` service, `async` work, an
  `error` path.
- **Handoffs are arrows.** Each runtime edge is drawn with its `verb` as the
  visible label. A dispatch-to-branch handoff is a yellow `branch` edge
  labelled with the branch it opens, and its card shows the verb.
- **Steps** follow the shared trunk, each branch in turn, convergence, then the
  tail. ◀ ▶ and the arrow keys walk them; the URL hash deep-links a node.
- **Views.** `Full request path` always exists. A `PR delta` tab appears when
  the PR changed only part of the path: it keeps every changed node plus its
  direct neighbours, so each change is shown with the boundaries it plugs into.

Above the canvas, the extension draws one orientation block (hidden with the
rest of the header when the reader minimises it with ▴ or `h`):

- the PR number (linked when `pr.url` is set) and the analyzed snapshot badge
- old → new boundary or ownership shift
- the owner-to-owner chain
- the architectural payoff
- the most important residual debt or asymmetry

The page title carries the central goal. Below the orientation sit build
notices (when any) and the cross-cutting evidence rail: tests, import rules
and documentation, labelled as having no runtime DTO, never drawn as runtime
nodes.

## Hover cards and the details panel

A node's hover card reads, in order:

1. its kind chip, step number and label (the page's own)
2. the summary — the first line of `purpose`
3. the change — `change_note`, or the sentence for its `change_status`
4. the detail — the remaining lines of `purpose`, bullets intact
5. the handoff — `Receives: … Sends: …`
6. the source location, linked, and the highlighted excerpt

Clicking pins the node in the details panel, which adds `receives`, `sends`,
`role`, `connection` and `tradeoff` as labelled fields, a `Sources` list with
every source link (editor link first when verified, GitHub beside it), and
"Comes from" / "Leads to" navigation through each handoff.

Cards stay open while the pointer crosses into them, so code can be selected
and the source link clicked; they dismiss after leaving both node and card,
on Escape, and on resize.

An edge's hover card shows its kind, endpoints and definition, then the
change, the verb (when the visible label is a branch name), every transferred
object as code, optional members, containers, the transformation and the
evidence. An edge with an empty `transfer` says it carries control flow only.

## Source excerpts

Each node's `code_preview` selects one of its `sources`; the scaffold derives
the excerpt bytes, label and links from the Git blob. Keep excerpts exact,
contiguous and small enough to read without scrolling: prefer 4–10 lines; the
scaffold rejects more than 12, and any line over 110 characters. Select a
narrower region rather than forcing horizontal scrolling.

Excerpts are highlighted locally with Catppuccin Mocha token colours — no
network highlighter. A `markdown` excerpt renders as the document it is
(headings, emphasis, inline code, lists, quotes, rules, fenced code
highlighted in its own language); the bytes are untouched and verified like
any other. Links in a markdown excerpt become links only for `http`, `https`
and `mailto`; raw HTML renders as text.

## Change context

Give every node and runtime edge a `change_status` of `added`, `modified`,
`removed`, or `context`. Colour already means kind on this page, so change is
drawn without a second hue channel:

- a changed node carries a corner delta with `+`, `~` or `−`
- a removed node's outline is dashed as well
- context edges recede; changed edges keep full weight with a faint glow
- the legend's "Change in this PR" section lists only the statuses the view
  uses, and hovering one highlights every node with it

Rosewater is the one palette hue the visual language leaves free, so it is
used only for change marks and the notice rule. Mark changed nodes in every
view, not only the delta.

When the PR has several branches, the legend's "Execution branches" section
lists them; hovering one lights its whole run from the shared trunk through
convergence and the tail.

## Link strategy

Default to immutable GitHub links:

```text
https://github.com/OWNER/REPO/blob/HEAD_SHA/path/to/file.py#L40-L77
```

Use descriptive source labels instead of bare filenames.

For optional local Cursor links, the path always rides behind the URL's leading separator:

```text
cursor://file/absolute/path/to/file.py:40
cursor://file/C:/absolute/path/to/file.py:40
```

A POSIX path already opens with that separator; a Windows path opens at its drive letter, so it needs the separator added and its backslashes turned into forward slashes. Concatenating a native path directly onto `cursor://file` produces `cursor://fileC:\...`, which browsers refuse to parse: the protocol reads as `:` rather than `cursor:` and a click opens a blank blocked tab. `scripts/scaffold_pr_explorer.py` handles this; hand-authored links must do the same.

Cursor links are optional. Verify the application registers the `cursor` URL scheme before presenting them as working.

Include a Cursor URL only when the target is a worktree whose `HEAD` equals the analyzed SHA and whose full file bytes equal the Git blob. Never silently open similar code from another commit.

The scaffold enforces this without failing the build. A `--cursor-root` that is a remote path, sits at another `HEAD`, or is not a readable worktree drops every editor link; an individual file that is missing or has drifted drops only its own link. Each refusal is recorded as a notice that reaches both the operator's console and the rendered page, and the affected nodes fall back to their immutable GitHub links. To get editor links against a moved checkout, add a detached worktree at the analyzed SHA and point `--cursor-root` at that.

An editor deep link names a path on the machine running the browser. A page served to another host offers links its reader cannot open, so generate them for the machine where the page will actually be viewed, or omit them.

Every source link opens a new browsing context (`target="_blank"`, `rel="noopener"`), so following one never replaces the explorer. If a host embeds the page in a sandboxed iframe, that iframe needs `allow-popups` and `allow-popups-to-escape-sandbox` for editor links to work.

## Visual requirements

- Dark-only Catppuccin Mocha; never branch on the reader's colour scheme.
- Never use `word-break: break-all` or `overflow-wrap: anywhere` for
  identifiers; the extension inserts `<wbr>` at CamelCase and snake_case
  boundaries instead.
- Write identifiers in prose fields between backticks; the extension turns
  them into real `<code>` elements. Labels and summary fields take no
  backticks (see [explorer-data-model.md](explorer-data-model.md)).
- Surface a degraded build on the page: the reader never sees the console.
- Make no network requests and load no runtime data.
- Keep labels short enough that the page never truncates the meaning away;
  put detail in `purpose`.

## Repository handoff

When the user asks for a repository-local copy:

1. Build the page into the closest architecture or developer-documentation directory.
2. Prefer `pr-<number>-<scope>-explorer.html` unless repository conventions specify otherwise.
3. Add a link to the nearest documentation index.
4. Re-run strict validation against the repository copy.

## Interaction checks

Assert that:

1. the orientation block, PR badge and analyzed snapshot badge are populated
2. every node shows its kind shape and colour, and the legend lists only kinds the view uses
3. every changed node carries its corner mark in the full-path view, not only in the delta
4. hovering a node opens a card with summary, change line, detail, handoff and a highlighted excerpt
5. the card stays open while the pointer enters it, code inside can be selected, and its source link opens a new context
6. clicking a node pins it in the details panel with every field, every source link, and Comes from / Leads to buttons that move the selection
7. ◀ ▶ walk the steps in order and visibly move the selection highlight
8. hovering an edge shows its verb, transfers (or "control flow only"), transformation and evidence
9. every real branch reaches the convergence node, and hovering a branch in the legend lights its whole run
10. the delta tab, when present, keeps each changed node's direct neighbours
11. a markdown excerpt renders as a document and its non-http links stay plain text
12. long identifiers wrap only at their `<wbr>` boundaries
13. a build that omitted editor links states so in the notice, and every affected node still offers its GitHub link
14. the page never renders light and makes no network requests
15. `verify_pr_explorer.py --strict` passes against the same snapshot the page names
