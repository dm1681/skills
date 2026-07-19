// TypeScript/TSX provider — ts-morph AST for symbol extraction + `findReferencesAsNodes`
// for precise dependency edges. `enclosingNamed` is the seam where tree-sitter drops in.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { Project, Node, ScriptTarget, ModuleKind, ModuleResolutionKind } from "ts-morph";
import type { ChangedRange } from "../types.ts";
import type { LanguageProvider, RawSymbol, RawEdge, ProviderResult } from "./types.ts";
import { pkgOf } from "../pkg.ts";

const DECL_KINDS = new Set([
  "FunctionDeclaration", "MethodDeclaration", "ClassDeclaration",
  "InterfaceDeclaration", "TypeAliasDeclaration", "EnumDeclaration",
]);

const SHORT_KIND: Record<string, string> = {
  FunctionDeclaration: "fn", MethodDeclaration: "method", ClassDeclaration: "class",
  InterfaceDeclaration: "interface", TypeAliasDeclaration: "type",
  EnumDeclaration: "enum", VariableDeclaration: "const",
};

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === "dist" || e.name === ".git") continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name === "package.json") out.push(p);
  }
  return out;
}

/** Auto-detect workspace packages so cross-package imports resolve without node_modules. */
function workspacePaths(repo: string): Record<string, string[]> {
  const paths: Record<string, string[]> = {};
  for (const pj of walk(repo)) {
    try {
      const j = JSON.parse(readFileSync(pj, "utf8"));
      if (!j.name) continue;
      const base = dirname(pj);
      const entry = j.source || j.module || j.main || "src/index.ts";
      const abs = join(base, entry).replace(/\.(js|mjs|cjs)$/, ".ts");
      paths[j.name] = [existsSync(abs) ? abs : join(base, "src/index.ts")];
      paths[`${j.name}/*`] = [join(base, "src/*")];
    } catch {}
  }
  return paths;
}

function analyzeTs(repo: string, changed: ChangedRange[]): ProviderResult {
  const project = new Project({
    skipAddingFilesFromTsConfig: true,
    compilerOptions: {
      allowJs: true, strict: false, skipLibCheck: true,
      target: ScriptTarget.ESNext, module: ModuleKind.ESNext,
      moduleResolution: ModuleResolutionKind.Bundler,
      baseUrl: repo, paths: workspacePaths(repo),
    },
  });
  project.addSourceFilesAtPaths([
    `${repo}/**/*.ts`, `${repo}/**/*.tsx`,
    `!${repo}/**/node_modules/**`, `!${repo}/**/dist/**`,
  ]);
  project.resolveSourceFileDependencies();

  // (A) changed ranges -> enclosing named symbols
  const symbols = new Map<string, RawSymbol & { _decl: Node }>();
  const keyOf = (file: string, name: string, line: number) => `${file}::${name}@${line}`;

  const enclosingNamed = (node: Node): Node | undefined => {
    let n: Node | undefined = node;
    while (n) {
      const k = n.getKindName();
      if (DECL_KINDS.has(k)) return n;
      if (k === "VariableDeclaration") {
        const init = (n as any).getInitializer?.();
        if (init && (Node.isArrowFunction(init) || Node.isFunctionExpression(init))) return n;
      }
      n = n.getParent();
    }
    return undefined;
  };

  for (const { file, ranges } of changed) {
    const abs = join(repo, file);
    const sf = project.getSourceFile(abs);
    if (!sf) continue;
    const full = sf.getFullText();
    const lineStart = [0];
    for (let i = 0; i < full.length; i++) if (full[i] === "\n") lineStart.push(i + 1);
    for (const [a, b] of ranges) {
      for (let ln = a; ln <= b; ln++) {
        const off = lineStart[ln - 1];
        if (off === undefined) continue;
        let p = off;
        while (p < full.length && (full[p] === " " || full[p] === "\t")) p++;
        const desc = sf.getDescendantAtPos(p);
        if (!desc) continue;
        const decl = enclosingNamed(desc);
        const nameNode = (decl as any)?.getNameNode?.();
        if (!decl || !nameNode) continue;
        const name = nameNode.getText();
        const line = decl.getStartLineNumber();
        const id = keyOf(file, name, line);
        if (!symbols.has(id)) {
          const kind = decl.getKindName();
          symbols.set(id, {
            id, name, kind, shortKind: SHORT_KIND[kind] ?? kind,
            file, pkg: pkgOf(repo, abs), line,
            snippet: decl.getText().slice(0, 500), _decl: decl,
          });
        }
      }
    }
  }

  // (B) edges among changed symbols via findReferences
  const enclosingChanged = (node: Node): (RawSymbol & { _decl: Node }) | undefined => {
    let n: Node | undefined = node;
    while (n) {
      const k = n.getKindName();
      if (DECL_KINDS.has(k) || k === "VariableDeclaration") {
        const nn = (n as any).getNameNode?.();
        if (nn) {
          const file = relative(repo, n.getSourceFile().getFilePath());
          const id = keyOf(file, nn.getText(), n.getStartLineNumber());
          if (symbols.has(id)) return symbols.get(id);
        }
      }
      n = n.getParent();
    }
    return undefined;
  };

  const edgeEv = new Map<string, string>(); // `owner==>dep` → evidence `file:line` (first ref site)
  for (const s of symbols.values()) {
    const nameNode = (s._decl as any).getNameNode?.();
    if (!nameNode) continue;
    let refs: Node[] = [];
    try { refs = nameNode.findReferencesAsNodes(); } catch { continue; }
    for (const r of refs) {
      const owner = enclosingChanged(r);
      if (owner && owner.id !== s.id) {
        const key = `${owner.id}==>${s.id}`;
        if (!edgeEv.has(key)) {
          const f = relative(repo, r.getSourceFile().getFilePath());
          edgeEv.set(key, `${f}:${r.getStartLineNumber()}`);
        }
      }
    }
  }

  const edges: RawEdge[] = [...edgeEv].map(([e, evidence]) => {
    const [source, target] = e.split("==>");
    return { source, target, evidence };
  });

  const rawSymbols: RawSymbol[] = [...symbols.values()].map(({ _decl, ...s }) => s);
  return { symbols: rawSymbols, edges, filesLoaded: project.getSourceFiles().length };
}

export const typescriptProvider: LanguageProvider = {
  name: "typescript",
  extensions: [".ts", ".tsx"],
  analyze: analyzeTs,
};
