// Ticket #6 — symbol extraction + dependency edges, dispatched across language providers.
// Each provider (TypeScript via ts-morph, Python via ast+pyright) turns changed line-ranges
// into raw symbols + raw edges for its file types; this module merges them and does the
// language-agnostic finalize: crossPkg/crossFile classification, degree, and cross-commit-
// stable public ids (`file::kind::name`). Providers keep their own precise reference engines.
import { extname } from "node:path";
import type { ChangedRange, Symbol, Edge } from "./types.ts";
import type { LanguageProvider } from "./providers/types.ts";
import { typescriptProvider } from "./providers/typescript.ts";
import { pythonProvider } from "./providers/python.ts";

const PROVIDERS: LanguageProvider[] = [typescriptProvider, pythonProvider];
const extOf = (f: string) => extname(f).toLowerCase();

/** Which providers own at least one changed file, in stable registration order. */
function providersFor(changed: ChangedRange[]): Array<{ provider: LanguageProvider; files: ChangedRange[] }> {
  return PROVIDERS.map((provider) => {
    const exts = new Set(provider.extensions);
    const files = changed.filter((c) => exts.has(extOf(c.file)));
    return { provider, files };
  }).filter((p) => p.files.length > 0);
}

export async function analyze(repo: string, changed: ChangedRange[]) {
  const t0 = Date.now();
  const active = providersFor(changed);

  // Run each provider over its own files. Ids embed the file path, so they never collide
  // across providers; merge order = provider registration order (deterministic).
  const rawSymbols: import("./providers/types.ts").RawSymbol[] = [];
  const rawEdges: import("./providers/types.ts").RawEdge[] = [];
  let filesLoaded = 0;
  for (const { provider, files } of active) {
    const res = await provider.analyze(repo, files);
    rawSymbols.push(...res.symbols);
    rawEdges.push(...res.edges);
    filesLoaded += res.filesLoaded;
  }
  const loadMs = Date.now() - t0;

  const byId = new Map(rawSymbols.map((s) => [s.id, s]));

  // Edges reference symbols by provider-local id; classify cross-pkg / cross-file here.
  const edges: Edge[] = rawEdges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => {
      const sa = byId.get(e.source)!, sb = byId.get(e.target)!;
      return { source: e.source, target: e.target, crossPkg: sa.pkg !== sb.pkg, crossFile: sa.file !== sb.file, evidence: e.evidence };
    });

  // degree
  const deg = new Map<string, number>([...byId.keys()].map((k) => [k, 0]));
  for (const e of edges) { deg.set(e.source, deg.get(e.source)! + 1); deg.set(e.target, deg.get(e.target)! + 1); }

  const symbols: Symbol[] = rawSymbols.map((s) => ({
    id: s.id, name: s.name, kind: s.kind, file: s.file, pkg: s.pkg,
    line: s.line, layer: 0, degree: deg.get(s.id)!, snippet: s.snippet, stableId: "",
  }));

  // Cross-commit-stable public ids: file::shortKind::name, disambiguated on collision.
  // Deterministic given the same diff (provider order, then each provider's scan order).
  const seen = new Map<string, number>();
  const shortById = new Map(rawSymbols.map((s) => [s.id, s.shortKind]));
  for (const s of symbols) {
    const base = `${s.file}::${shortById.get(s.id) ?? s.kind}::${s.name}`;
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    s.stableId = n === 0 ? base : `${base}#${n + 1}`;
  }

  return { symbols, edges, loadMs, analyzeMs: Date.now() - t0, filesLoaded };
}
