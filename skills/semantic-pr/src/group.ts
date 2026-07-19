// Ticket #7 — cohorts (connected components) → sub-groups (Louvain community detection) → layers.
import Graph from "graphology";
import louvain from "graphology-communities-louvain";
import type { Symbol, Edge, SubGroup } from "./types.ts";

const SUBGROUP_THRESHOLD = 12; // cohorts larger than this get community-split

export function group(symbols: Symbol[], edges: Edge[]): SubGroup[] {
  const byId = new Map(symbols.map((s) => [s.id, s]));

  // ---- layering: longest-path over the depends-on DAG (edge source depends on target) ----
  const deps = new Map<string, string[]>(symbols.map((s) => [s.id, []]));
  for (const e of edges) if (e.source !== e.target) deps.get(e.source)!.push(e.target);
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
      const communities = louvain(g); // {nodeId: communityIndex}
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
      out.push({ cohortId, subId, symbols: syms, pkgs, crossPkg: pkgs.length > 1 });
    });
    cohortId++;
  }
  return out;
}
