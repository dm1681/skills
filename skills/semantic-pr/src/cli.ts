#!/usr/bin/env -S npx tsx
// Layered semantic PR walkthrough — CLI. See docs/layered-semantic-pr-spec.md
import { writeFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { resolveRefs, changedRanges } from "./ingest.ts";
import { analyze } from "./analyze.ts";
import { group } from "./group.ts";
import { label, type Reuse } from "./label.ts";
import { render } from "./render.ts";
import { toArtifact } from "./contract.ts";
import { matchAny } from "./glob.ts";
import type { Analysis } from "./types.ts";

function parseArgs(argv: string[]) {
  const a: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    const m = argv[i].match(/^--([^=]+)(?:=(.*))?$/);
    if (m) a[m[1]] = m[2] ?? argv[++i] ?? "";
  }
  return a;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repo = resolve(args.repo || ".");
  const { baseRef, headRef } = resolveRefs(repo, args.base, args.head);

  console.error(`[ingest] ${repo}  ${baseRef.slice(0, 12)}..${headRef.slice(0, 12)}`);
  let changed = changedRanges(repo, baseRef, headRef);
  console.error(`[ingest] ${changed.length} changed .ts/.tsx files`);

  // #1 fog: optional path filtering (comma-separated globs). Tests are still shown by default —
  // exclude them explicitly (e.g. --exclude 'tests/**') for a product-only view.
  const inc = (args.include || "").split(",").map((s) => s.trim()).filter(Boolean);
  const exc = (args.exclude || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (inc.length || exc.length) {
    const before = changed.length;
    changed = changed.filter((c) => (inc.length ? matchAny(c.file, inc) : true) && !matchAny(c.file, exc));
    console.error(`[filter] ${before}→${changed.length} files (include:${inc.join("|") || "*"} exclude:${exc.join("|") || "none"})`);
  }
  if (!changed.length) { console.error("No TypeScript changes in range."); process.exit(0); }

  const { symbols, edges, loadMs, analyzeMs, filesLoaded } = analyze(repo, changed);
  console.error(`[analyze] ${symbols.length} symbols, ${edges.length} edges (load ${loadMs}ms, total ${analyzeMs}ms)`);

  const { subGroups, cycles } = group(symbols, edges);
  console.error(`[group] ${subGroups.length} sub-groups${cycles.length ? `, ${cycles.length} cycle(s)` : ""}`);

  // #19: incremental re-review — reuse summaries from a prior artifact by stable group id.
  let reuse: Reuse | undefined;
  if (args.prev) {
    try {
      const prev = JSON.parse(readFileSync(args.prev, "utf8"));
      reuse = new Map();
      for (const g of prev.groups ?? []) if (g.summary != null) reuse.set(g.id, { title: g.title, summary: g.summary, layerNotes: g.layerNotes ?? [] });
      console.error(`[prev] ${reuse.size} reusable group summaries from ${args.prev}`);
    } catch (e) { console.error(`[prev] could not read ${args.prev}: ${(e as Error).message}`); }
  }

  const labeled = label(subGroups, reuse);

  const analysis: Analysis = {
    meta: {
      repo: repo.split("/").pop() || repo, base: baseRef, head: headRef,
      filesChanged: changed.length, filesLoaded,
      symbolCount: symbols.length, edgeCount: edges.length,
      crossFile: edges.filter((e) => e.crossFile).length,
      crossPkg: edges.filter((e) => e.crossPkg).length,
      loadMs, analyzeMs,
    },
    symbols, edges, subGroups: labeled,
    cycles: cycles.map((c) => c.map((s) => s.stableId)),
  };

  const md = render(analysis);
  if (args.out) { writeFileSync(args.out, md); console.error(`[render] wrote ${args.out}`); }
  else process.stdout.write(md + "\n");
  if (args.json) { writeFileSync(args.json, JSON.stringify(toArtifact(analysis), null, 2)); console.error(`[render] wrote ${args.json}`); }
}

main().catch((e) => { console.error(e); process.exit(1); });
