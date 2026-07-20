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
  /** cross-commit-stable public identity: `file::kind::name` (+ `#n` on collision). Line-independent. */
  stableId: string;
  /** true when this symbol is in a dependency cycle (non-trivial SCC) — order isn't strict */
  inCycle?: boolean;
}

export interface Edge {
  source: string; // depends on target
  target: string;
  crossPkg: boolean;
  crossFile: boolean;
  /** an inspectable citation: `file:line` of a reference site where source uses target */
  evidence?: string;
}

export interface SubGroup {
  /** cross-commit-stable id: short hash of the sorted member stableIds. */
  id: string;
  cohortId: number;
  subId: number;
  symbols: Symbol[]; // ordered by layer, then degree desc
  pkgs: string[];
  crossPkg: boolean;
  /** true when every member is a test file — rendered last, as the verification layer */
  isTest: boolean;
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
    /** capabilities that were unavailable this run, so the graph is partial (e.g.
     * "python-edges-unavailable" when pyright is missing). Empty/absent = full analysis. */
    degraded?: string[];
  };
  symbols: Symbol[];
  edges: Edge[];
  subGroups: SubGroup[];
  /** dependency cycles among changed symbols (non-trivial SCCs), as stableId lists */
  cycles: string[][];
}
