// Shared types for the layered-semantic-PR pipeline.

export interface ChangedRange {
  file: string;
  /** inclusive 1-based line ranges on the HEAD side */
  ranges: Array<[number, number]>;
}

export interface Symbol {
  id: string; // `${file}::${name}@${line}`
  name: string;
  kind: string;
  file: string;
  pkg: string;
  line: number;
  layer: number; // 0 = foundational
  degree: number;
  snippet?: string; // truncated declaration text, for the summarizer
}

export interface Edge {
  source: string; // depends on target
  target: string;
  crossPkg: boolean;
  crossFile: boolean;
}

export interface SubGroup {
  cohortId: number;
  subId: number;
  symbols: Symbol[]; // ordered by layer, then degree desc
  pkgs: string[];
  crossPkg: boolean;
  /** filled by the summarizer */
  title?: string;
  summary?: string;
  layerNotes?: Array<{ layer: number; note: string }>;
}

export interface Analysis {
  meta: {
    repo: string;
    base: string;
    head: string;
    filesChanged: number;
    filesLoaded: number;
    symbolCount: number;
    edgeCount: number;
    crossFile: number;
    crossPkg: number;
    loadMs: number;
    analyzeMs: number;
  };
  symbols: Symbol[];
  edges: Edge[];
  subGroups: SubGroup[];
}
