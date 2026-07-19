#!/usr/bin/env -S npx tsx
// Layered semantic PR walkthrough — CLI. See docs/layered-semantic-pr-spec.md
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { resolveRefs, changedRanges } from "./ingest.ts";
import { analyze } from "./analyze.ts";
import { group } from "./group.ts";
import { summarize } from "./summarize.ts";
import { render } from "./render.ts";
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
  const changed = changedRanges(repo, baseRef, headRef);
  console.error(`[ingest] ${changed.length} changed .ts/.tsx files`);
  if (!changed.length) { console.error("No TypeScript changes in range."); process.exit(0); }

  const { symbols, edges, loadMs, analyzeMs, filesLoaded } = analyze(repo, changed);
  console.error(`[analyze] ${symbols.length} symbols, ${edges.length} edges (load ${loadMs}ms, total ${analyzeMs}ms)`);

  const subGroups = group(symbols, edges);
  console.error(`[group] ${subGroups.length} sub-groups`);

  const summarized = await summarize(subGroups);

  const analysis: Analysis = {
    meta: {
      repo: repo.split("/").pop() || repo, base: baseRef, head: headRef,
      filesChanged: changed.length, filesLoaded,
      symbolCount: symbols.length, edgeCount: edges.length,
      crossFile: edges.filter((e) => e.crossFile).length,
      crossPkg: edges.filter((e) => e.crossPkg).length,
      loadMs, analyzeMs,
    },
    symbols, edges, subGroups: summarized,
  };

  const md = render(analysis);
  if (args.out) { writeFileSync(args.out, md); console.error(`[render] wrote ${args.out}`); }
  else process.stdout.write(md + "\n");
  if (args.json) { writeFileSync(args.json, JSON.stringify(analysis, null, 2)); console.error(`[render] wrote ${args.json}`); }
}

main().catch((e) => { console.error(e); process.exit(1); });
