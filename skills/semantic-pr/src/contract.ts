// The stable, versioned public artifact (ticket #16). Consumers should depend on THIS shape,
// not on internal fields. See references/cohort-contract.md.
import type { Analysis } from "./types.ts";

export const SCHEMA_VERSION = "1.0";

export interface Artifact {
  schemaVersion: string;
  meta: Analysis["meta"];
  /** every changed symbol, keyed by its cross-commit-stable id */
  symbols: Array<{
    id: string; name: string; kind: string; file: string; pkg: string;
    line: number; layer: number; degree: number;
    snippet: string; // truncated declaration text — enough for a caller to summarize the group
  }>;
  /** dependency edges (source depends on target), stable-id endpoints */
  edges: Array<{ source: string; target: string; crossPkg: boolean; crossFile: boolean }>;
  /** the walkthrough: dependency cohorts → feature groups → ordered symbols */
  groups: Array<{
    id: string; cohort: number; pkgs: string[]; crossPkg: boolean;
    title: string | null; summary: string | null;
    layerNotes: Array<{ layer: number; note: string }>;
    symbols: string[]; // member stableIds, in layer order
  }>;
}

export function toArtifact(a: Analysis): Artifact {
  const stable = new Map(a.symbols.map((s) => [s.id, s.stableId]));
  return {
    schemaVersion: SCHEMA_VERSION,
    meta: a.meta,
    symbols: a.symbols.map((s) => ({
      id: s.stableId, name: s.name, kind: s.kind, file: s.file, pkg: s.pkg,
      line: s.line, layer: s.layer, degree: s.degree, snippet: s.snippet ?? "",
    })),
    edges: a.edges.map((e) => ({
      source: stable.get(e.source)!, target: stable.get(e.target)!,
      crossPkg: e.crossPkg, crossFile: e.crossFile,
    })),
    groups: a.subGroups.map((g) => ({
      id: g.id, cohort: g.cohortId, pkgs: g.pkgs, crossPkg: g.crossPkg,
      title: g.title ?? null, summary: g.summary ?? null,
      layerNotes: g.layerNotes ?? [],
      symbols: g.symbols.map((s) => s.stableId),
    })),
  };
}
