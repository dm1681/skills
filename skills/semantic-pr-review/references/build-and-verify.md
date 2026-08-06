# Build and Verify

Commands and the verification procedure for the explorer artifacts. Resolve `<skill-root>` to the directory containing `SKILL.md`. Invoke whichever interpreter name this machine has: `python3` on most Unix-like systems, `python` on Windows, where a bare `python3` usually resolves to a Microsoft Store stub that exits without running anything. Every bundled script targets Python 3.9+ and imports only the standard library.

## Build

Validate the model first with the scaffold's `--check` mode (command and authoring rules in [explorer-data-model.md](explorer-data-model.md)). Then render the fragment:

```bash
python3 <skill-root>/scripts/scaffold_pr_explorer.py \
  --data /absolute/path/to/pr-model.json \
  --output /absolute/path/to/pr-fragment.html \
  --repo-root /absolute/path/to/repository \
  --source-ref <exact-analyzed-sha> \
  --cursor-root /absolute/path/to/matching-snapshot-worktree
```

`--source-ref` defaults to `pr.evidence_sha` when set, otherwise `pr.head_sha`. Omit `--cursor-root` to fail closed to immutable GitHub links; supply it only for a worktree on the same SHA. A remote path, a different `HEAD`, or drifted source bytes omit the editor links with a warning and still build the explorer; a link is never emitted for a file the scaffold cannot match byte for byte.

Set `pr.base_sha` in the model (fetch the merge base alongside the head in workflow step 1) to add `PR diff` links and hover diff previews; a base the repository cannot resolve degrades the same way, with a warning and a page notice rather than a failed build.

Create the standalone page with the bundled renderer, `scripts/render_standalone.py` — command, sandbox, and link rules in [interactive-flowchart.md](interactive-flowchart.md). Use `scripts/prepare_standalone.py` only when adapting a sandboxed iframe page produced by another renderer.

## Verification procedure

1. Run repository tests relevant to the changed contracts, adapters, and handoffs when the environment supports them. Distinguish assertion failures from dependency or environment failures.
2. Run the artifact validator:

```bash
python3 <skill-root>/scripts/verify_pr_explorer.py /absolute/path/to/fragment.html \
  --standalone /absolute/path/to/page.html \
  --source-repo /absolute/path/to/repository \
  --source-ref <exact-head-sha> \
  --strict
```

Strict validation must compare every rendered preview byte-for-byte with its Git blob, verify labels and immutable URLs from the same range, and verify every Cursor target's worktree `HEAD` and full source bytes. When the model carries `pr.base_sha`, it also recomputes every diff preview from the same base and head and every `PR diff` anchor from the file path's SHA-256.

3. In a real browser, exercise the assertions in [interactive-flowchart.md](interactive-flowchart.md) § Interaction checks: branch switching, Previous/Next navigation, node selection, dynamic source links, editor deep links, pointer entry into node tooltips, code selection, and delayed tooltip dismissal.
4. Assert the orientation title is populated and a primary button has non-default computed font, background, and border-radius values — this catches blocked scripts and missing base styles. Compare computed styles before and after clicking Next: a node's appearance must change (an `aria-pressed` move with identical styling means selection is invisible to sighted readers), and a changed node must differ from a context node in the default view, or the legend describes a view the reader is not in.
5. Render or screenshot the page at 736 px and 320 px. Check that `scrollWidth <= clientWidth` and inspect for clipped, overlapping, or arbitrarily broken identifiers. Confirm code previews use Catppuccin Mocha with readable contrast and distinguishable syntax categories; there is no light mode, so a page that renders light is a defect.
6. Verify in a Chromium-based and a Gecko-based browser. Engine differences in generated content, dashed borders, and URL parsing are invisible to single-engine checks.
7. If the build omitted any source link, confirm the page states so and that the affected nodes still offer their GitHub links.

## Setup facts

Two facts make the browser steps possible at all:

- **Serve the page over HTTP.** Browser-automation extensions routinely refuse `file://` URLs. Run `python3 -m http.server 8765 --bind 127.0.0.1` from the output directory and open `http://127.0.0.1:8765/<page>.html`.
- **Computed-style checks need an unsandboxed harness.** `render_standalone.py` puts the fragment in a sandboxed iframe, so `iframe.contentDocument` is `null` from the parent and no script can query it. Build a throwaway harness — `assets/pr-explorer-base.css` in a `<style>` tag followed by the fragment — and run the style, overflow, and tooltip assertions there. Use the standalone page itself for screenshots and visual checks.
