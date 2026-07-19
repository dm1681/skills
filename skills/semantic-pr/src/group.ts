// Ticket #7 — cohorts (connected components) → sub-groups (Louvain community detection) → layers.
import { createHash } from "node:crypto";
import Graph from "graphology";
import louvain from "graphology-communities-louvain";
import { isTestFile } from "./glob.ts";
import type { Symbol, Edge, SubGroup } from "./types.ts";

/** Stable id for a group = short hash of its sorted member stableIds (order-independent). */
const groupId = (syms: Symbol[]) =>
  createHash("sha1").update(syms.map((s) => s.stableId).sort().join("\n")).digest("hex").slice(0, 12);

/** Seeded PRNG so Louvain is deterministic → group membership (and thus group ids) is reproducible. */
function seededRng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const SUBGROUP_THRESHOLD = 12; // cohorts larger than this get community-split

/** Tarjan SCC over a directed adjacency map; returns strongly-connected components. */
function sccs(nodes: string[], adj: Map<string, string[]>): string[][] {
  let idx = 0;
  const index = new Map<string, number>(), low = new Map<string, number>();
  const stack: string[] = [], onStack = new Set<string>(), comps: string[][] = [];
  const connect = (v: string) => {
    index.set(v, idx); low.set(v, idx); idx++; stack.push(v); onStack.add(v);
    for (const w of adj.get(v) ?? []) {
      if (!index.has(w)) { connect(w); low.set(v, Math.min(low.get(v)!, low.get(w)!)); }
      else if (onStack.has(w)) low.set(v, Math.min(low.get(v)!, index.get(w)!));
    }
    if (low.get(v) === index.get(v)) {
      const comp: string[] = []; let w: string;
      do { w = stack.pop()!; onStack.delete(w); comp.push(w); } while (w !== v);
      comps.push(comp);
    }
  };
  for (const v of nodes) if (!index.has(v)) connect(v);
  return comps;
}

export function group(symbols: Symbol[], edges: Edge[]): { subGroups: SubGroup[]; cycles: Symbol[][] } {
  const byId = new Map(symbols.map((s) => [s.id, s]));

  // ---- layering: longest-path over the depends-on DAG (edge source depends on target) ----
  const deps = new Map<string, string[]>(symbols.map((s) => [s.id, []]));
  for (const e of edges) if (e.source !== e.target) deps.get(e.source)!.push(e.target);

  // Cycles: non-trivial SCCs. Mark members so the ordering can be flagged as non-strict.
  const byIdScc = new Map(symbols.map((s) => [s.id, s]));
  const cycles: Symbol[][] = sccs(symbols.map((s) => s.id), deps)
    .filter((c) => c.length > 1).map((c) => c.map((id) => byIdScc.get(id)!));
  for (const c of cycles) for (const s of c) s.inCycle = true;
  const layerMemo = new Map<string, number>();
  const layerOf = (id: string, stack = new Set<string>()): number => {
    if (layerMemo.has(id)) return layerMemo.get(id)!;
    if (stack.has(id)) return 0; // cycle guard
    stack.add(id);
    let mx = -1;
    for (const d of deps.get(id) ?? []) mx = Math.max(mx, layerOf(d, stack));
    stack.delete(id);
    const L = mx + 1;
    layerMemo.set(id, L);
    return L;
  };
  for (const s of symbols) s.layer = layerOf(s.id);

  // ---- cohorts: connected components (undirected) ----
  const parent = new Map(symbols.map((s) => [s.id, s.id]));
  const find = (x: string): string => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x)!)!); x = parent.get(x)!; } return x; };
  for (const e of edges) parent.set(find(e.source), find(e.target));
  const cohorts = new Map<string, Symbol[]>();
  for (const s of symbols) { const r = find(s.id); (cohorts.get(r) ?? cohorts.set(r, []).get(r)!).push(s); }

  // ---- sub-groups: Louvain within any large cohort ----
  const out: SubGroup[] = [];
  let cohortId = 0;
  for (const members of [...cohorts.values()].sort((a, b) => b.length - a.length)) {
    const ids = new Set(members.map((s) => s.id));
    let partitions: Symbol[][];
    if (members.length > SUBGROUP_THRESHOLD) {
      const g = new Graph({ type: "undirected" });
      for (const s of members) g.addNode(s.id);
      for (const e of edges) if (ids.has(e.source) && ids.has(e.target) && e.source !== e.target && !g.hasEdge(e.source, e.target)) g.addEdge(e.source, e.target);
      const communities = louvain(g, { rng: seededRng(0x5eed) }); // deterministic partition
      const buckets = new Map<number, Symbol[]>();
      for (const s of members) { const c = communities[s.id] ?? 0; (buckets.get(c) ?? buckets.set(c, []).get(c)!).push(s); }
      partitions = [...buckets.values()];
    } else {
      partitions = [members];
    }
    partitions.sort((a, b) => b.length - a.length);
    partitions.forEach((syms, subId) => {
      syms.sort((a, b) => a.layer - b.layer || b.degree - a.degree);
      const pkgs = [...new Set(syms.map((s) => s.pkg))];
      out.push({
        id: groupId(syms), cohortId, subId, symbols: syms, pkgs,
        crossPkg: pkgs.length > 1, isTest: syms.every((s) => isTestFile(s.file)),
      });
    });
    cohortId++;
  }
  // Verification last: product groups keep their order; all-test groups sink to the end.
  const subGroups = [...out.filter((g) => !g.isTest), ...out.filter((g) => g.isTest)];
  return { subGroups, cycles };
}
