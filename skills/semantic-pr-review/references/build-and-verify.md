# Build and Verify

Commands and the verification procedure for the explorer page. Resolve `<skill-root>` to the directory containing `SKILL.md`. Invoke whichever interpreter name this machine has: `python3` on most Unix-like systems, `python` on Windows, where a bare `python3` usually resolves to a Microsoft Store stub that exits without running anything. Every bundled script targets Python 3.9+ and imports only the standard library (plus the bundled `diagram_core.py`, which does too).

## Build

Validate the model first with the scaffold's `--check` mode (command and authoring rules in [explorer-data-model.md](explorer-data-model.md)). Then render the page:

```bash
python3 <skill-root>/scripts/scaffold_pr_explorer.py \
  --data /absolute/path/to/pr-model.json \
  --output /absolute/path/to/pr-<number>-<scope>-explorer.html \
  --repo-root /absolute/path/to/repository \
  --source-ref <exact-analyzed-sha> \
  --cursor-root /absolute/path/to/matching-snapshot-worktree
```

The output is one self-contained HTML page — no network, no host stylesheet, no wrapper. Open it directly or hand it to an artifact surface as-is.

`--source-ref` defaults to `pr.evidence_sha` when set, otherwise `pr.head_sha`. Omit `--cursor-root` to fail closed to immutable GitHub links; supply it only for a worktree on the same SHA. A remote path, a different `HEAD`, or drifted source bytes omit the editor links with a warning and still build the explorer; a link is never emitted for a file the scaffold cannot match byte for byte.

## Verification procedure

1. Run repository tests relevant to the changed contracts, adapters, and handoffs when the environment supports them. Distinguish assertion failures from dependency or environment failures.
2. Run the page validator:

```bash
python3 <skill-root>/scripts/verify_pr_explorer.py /absolute/path/to/page.html \
  --source-repo /absolute/path/to/repository \
  --source-ref <exact-head-sha> \
  --strict
```

Strict validation compares every preview byte-for-byte with its Git blob, verifies labels and immutable URLs from the same range, verifies every Cursor target's worktree `HEAD` and full source bytes, and checks that every excerpt and link the page *draws* is the verified record's own, so an edit to the displayed copy alone is caught too.

3. In a real browser, exercise the assertions in [interactive-flowchart.md](interactive-flowchart.md) § Interaction checks: hover cards, pointer entry into a card, code selection, delayed dismissal, the step tour, node selection, source links, branch highlighting from the legend, and the delta tab when present.
4. Screenshot the full-path view at a desktop width and at 736 px and 320 px. Check that no label is hidden by a container header or another label, that the orientation block and snapshot badge are populated, and that changed nodes carry their corner mark. There is no light mode; a page that renders light is a defect.
5. Verify in a Chromium-based and a Gecko-based browser. Engine differences in SVG text, dashed strokes, and URL parsing are invisible to single-engine checks.
6. If the build omitted any source link, confirm the page's notice says so and that the affected nodes still offer their GitHub links.

## Setup facts

- **Serve the page over HTTP** for browser automation. Automation extensions routinely refuse `file://` URLs. Run `python3 -m http.server 8765 --bind 127.0.0.1` from the output directory and open `http://127.0.0.1:8765/<page>.html`.
- **Deep links select a state.** `#v=full&n=<node-id>` opens a view with that node pinned in the details panel, which makes screenshots of specific cards reproducible without scripting a hover.
- **The page is not sandboxed**, so computed-style and DOM assertions can run against it directly.
