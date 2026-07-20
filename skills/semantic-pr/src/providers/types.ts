// Language-provider interface. Each provider turns changed line-ranges into raw
// symbols + raw edges for its file types; analyze.ts merges providers and does the
// shared finalize (crossPkg/crossFile, degree, cross-commit-stable ids).
import type { ChangedRange } from "../types.ts";

/** A changed symbol as a provider sees it, before the shared finalize. */
export interface RawSymbol {
  /** provider-local unique key — MUST embed the file path so ids never collide across providers */
  id: string;
  name: string;
  kind: string; // native AST kind name (e.g. "FunctionDeclaration", "def", "class")
  /** compact kind used in the public stableId (e.g. "fn", "class", "method") */
  shortKind: string;
  file: string; // repo-relative
  pkg: string;
  line: number; // 1-based declaration line on the HEAD side
  snippet: string; // truncated declaration text, for the summarizer
}

/** A dependency between two changed symbols: `source` uses `target`. */
export interface RawEdge {
  source: string; // RawSymbol.id
  target: string; // RawSymbol.id
  /** `file:line` of a reference site where source uses target */
  evidence?: string;
}

export interface ProviderResult {
  symbols: RawSymbol[];
  edges: RawEdge[];
  filesLoaded: number;
  /** capabilities this provider couldn't use this run, making its slice of the graph partial
   * (e.g. "python-edges-unavailable" when pyright is missing). Surfaced in the artifact meta. */
  degraded?: string[];
}

export interface LanguageProvider {
  name: string;
  /** lowercase extensions this provider owns, with the dot (e.g. [".ts", ".tsx"]) */
  extensions: string[];
  analyze(repo: string, changed: ChangedRange[]): ProviderResult;
}
