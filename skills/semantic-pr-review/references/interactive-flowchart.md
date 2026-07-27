# Interactive PR Flowchart

## Composition

Use a top-down flowchart for runtime sequence. Show branch lanes side by side and reconnect them visibly at the shared output. Place cross-cutting tests, rules, and documentation on a separate rail rather than pretending they run after the workflow.

Begin with one orientation block containing:

- the central goal in one sentence
- the old-to-new boundary or ownership shift
- the high-level owner-to-owner path
- the architectural payoff
- the most important residual debt or asymmetry

For each branch, show the full runtime path: dispatch, adapter, translated request or configuration, execution engine, mode-specific result, and shared convergence. Align comparable semantic stages across lanes.

Keep these controls only when supported by the PR:

- Previous and Next path navigation
- clickable flow nodes
- hover or keyboard-focus previews

When every branch is already visible, highlight the complete branch on hover or keyboard focus. Do not add `Trace ...` buttons that merely restate visible lanes. Use persistent mode or strategy controls only when they reveal, filter, or materially change the rendered information.

Keep one persistent selected-node detail area. Include:

- purpose
- receives and sends
- architectural role
- connection to adjacent nodes
- why the node or tradeoff matters
- exact source links

Give every node hover or keyboard-focus preview a compact source excerpt in addition to its purpose and transfer summary. The preview must remain open while the pointer moves from the node into the tooltip so the viewer can select code and activate its source link.

## Source excerpts

Use each node's `code_preview` record to render:

- the node status, purpose, receives, and sends summary
- a `Relevant code` label
- a linked `file · start–end` location
- a semantic `<pre><code>` block with syntax highlighting

Keep excerpts exact, contiguous, and small enough to comprehend without scrolling. Prefer 4–10 lines and cap at 12. Keep lines concise; select a narrower source region instead of introducing horizontal scrolling or arbitrary identifier breaks. Define the range in the raw model and derive the displayed label and code directly from the Git blob; never maintain those values separately.

Use Catppuccin Latte for the code surface in light mode and Catppuccin Mocha in dark mode. Tokenize at least comments, strings, keywords, built-ins, types, functions, variables, properties, numbers, operators, punctuation, and decorators when the language supports them. Support common PR languages (`python`, `javascript`, `typescript`, `json`, `toml`, `yaml`, `markdown`, `shell`) and use a conservative generic tokenizer for other languages.

Implement highlighting locally in the fragment. Do not depend on a network-loaded highlighter for core readability.

The tooltip must:

- use `pointer-events: auto` and selectable text
- stay visible while the pointer crosses the small gap from trigger to tooltip
- cancel its delayed dismissal when the pointer enters the tooltip
- dismiss after leaving both trigger and tooltip, on Escape, and on resize
- preserve keyboard-focus behavior through `aria-describedby`
- remain supplementary to the persistent click-selected detail area

## Edge contracts

Treat arrows as evidence-backed handoffs rather than decoration. Every runtime edge must have:

- a short visible action verb
- source and destination nodes
- exact transferred DTOs, events, or configuration objects
- optionality and wrapping containers when relevant
- transformation or normalization behavior
- a source or test reference

Show the action verb on the chart and expose the transfer details through hover and keyboard focus. Render a tooltip owned by the explorer and convert backtick-delimited names into real `<code>` elements. Do not rely on the host's plain-text `data-tooltip` treatment when monospace code styling is required.

Use a separate cross-cutting rail for tests, import rules, and documentation. Label it as having no runtime DTO.

## Change context

Give every node and runtime edge a `change_status` of `added`, `modified`, `removed`, or `context`. Display node status with text or shape in addition to color, and distinguish changed and contextual path segments with line treatment or emphasis as well as color.

When a small diff needs substantial neighboring context, provide separate `PR delta` and `Full request path` controls plus a visible status legend. The full path may retain context nodes in a secondary state; the delta view must preserve enough boundary information to explain the change. Show the analyzed immutable head SHA near the orientation block.

## Link strategy

Default to immutable GitHub links in standalone pages:

```text
https://github.com/OWNER/REPO/blob/HEAD_SHA/path/to/file.py#L40-L77
```

Use descriptive labels instead of bare filenames.

For optional local Cursor links on macOS:

```text
cursor://file/absolute/path/to/file.py:40
```

Cursor links are optional. Verify the application registers the `cursor` URL scheme before presenting them as working.

Always include an immutable GitHub URL derived from the analyzed SHA. In the hover preview, make the visible `file · start–end` location itself a link.

Include a Cursor URL only when the target is a worktree whose `HEAD` equals the analyzed SHA and whose full file bytes equal the Git blob. If the active checkout differs, either create a detached snapshot worktree or omit Cursor and use GitHub. Never silently open similar code from another commit.

If the standalone renderer places the fragment in a sandboxed iframe:

- give Cursor anchors `target="_blank"` and `rel="noopener"`
- include both `allow-popups` and `allow-popups-to-escape-sandbox` in the iframe sandbox
- trigger navigation only from a direct user click
- test that the original flowchart remains visible after the click

Without those conditions, Chromium can replace the embedded flowchart with a broken document view.

Create a self-contained standalone page without relying on a host renderer:

```bash
python3 <skill-root>/scripts/render_standalone.py \
  --fragment /absolute/path/to/pr-fragment.html \
  --output /absolute/path/to/page.html \
  --title "PR <number> <scope> Explorer"
```

The bundled renderer creates a self-contained sandboxed wrapper, embeds `assets/pr-explorer-base.css` inside the framed document, and applies restrictive outer and inner policies that still permit the explorer's local inline style and script. This keeps the page compatible with both ordinary browsers and embedded artifact viewers. Source links open a new browsing context. When adapting a sandboxed page produced by another renderer, run `scripts/prepare_standalone.py`; it preserves existing permissions and adds the popup permissions required by editor deep links.

## Visual requirements

- Use semantic native buttons and links.
- Keep tab order native.
- Support 736 px and widths down to 320 px.
- Reflow branches vertically on narrow screens.
- Avoid internal scrolling and fixed viewport heights.
- Use theme variables instead of hard-coded light or dark colors.
- Make inactive branches visibly secondary without relying on color alone.
- Do not load runtime data or make network requests from the fragment.
- Assign stable colors to owners, systems, or execution branches and reuse them on lane headers, edges, trace state, and the legend. Keep shared boundaries neutral.
- Format functions, classes, methods, fields, DTOs, and file names with `<code>` in HTML. Use backticks only as source notation that the rich-tooltip renderer converts into `<code>`.
- For rich tooltips, parse backtick-delimited names into actual `<code>` elements, associate triggers with the tooltip through `aria-describedby`, and support hover, focus, and Escape dismissal.
- Make node tooltips pointer-enterable and source-linked; do not let them disappear while the viewer moves in to select code or click the file-and-line location.
- Render node excerpts in `<pre><code>` with Catppuccin Latte/Mocha syntax colors and keep the highlighting self-contained.
- Embed the bundled base stylesheet in standalone output. Do not assume a host supplies `.card`, `.btn`, `.tooltip`, typography, theme variables, or accessibility utilities.
- Inside constrained flow nodes, remove decorative code-pill padding while preserving monospace type. Never use `word-break: break-all` or `overflow-wrap: anywhere` for identifiers.
- Add semantic `<wbr>` opportunities at CamelCase and snake_case boundaries for long identifiers. Put explanatory qualifiers on a separate stacked line instead of forcing arbitrary `<br>` breaks inside identifiers.

## Repository handoff

Keep the editable fragment in the current session's artifact or output directory. When the user asks for a repository-local copy:

1. Render a self-contained standalone page.
2. Save it under the closest architecture or developer-documentation directory.
3. Prefer `pr-<number>-<scope>-explorer.html` unless repository conventions specify otherwise.
4. Add a link to the nearest documentation index.
5. Re-run standalone validation against the repository copy.

## Interaction checks

Assert that:

1. the initial selected node populates every detail field
2. hovering or keyboard-focusing a visible branch emphasizes its complete path without hiding the shared trunk or convergence
3. Previous and Next follow only the active path
4. clicking an off-path node still updates its details
5. every source link changes with the selected node
6. source links include line anchors
7. editor deep links do not replace the flowchart frame
8. hover previews are supplementary and essential details remain visible on click
9. every runtime edge exposes at least one transfer object or explicitly states that none exists
10. every real branch reaches the shared convergence node
11. the orientation block, analyzed head SHA, node/edge change-status encoding, and status legend are present
12. long code identifiers do not clip, overflow, or break at arbitrary characters
13. every node has a source-backed `code_preview` whose source index resolves
14. node tooltips remain open while entered, code can be selected, and the linked file/range opens the configured target without replacing the chart
15. light and dark code surfaces use Catppuccin Latte and Mocha with distinguishable syntax categories
16. every displayed excerpt, label, immutable URL, and optional Cursor target verifies against the same `pr.head_sha`
17. the standalone page populates its orientation title and applies non-default computed styles to its primary controls
