// Ticket #6 — symbol extraction (A) + dependency edges (B).
// Spec calls for tree-sitter on (A); v1 implements (A) with ts-morph's AST to keep the tool a single
// dependency and to reuse the proven spike. `enclosingNamed` is the seam where tree-sitter drops in.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { Project, Node, ScriptTarget, ModuleKind, ModuleResolutionKind } from "ts-morph";
import type { ChangedRange, Symbol, Edge } from "./types.ts";

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

const pkgOf = (repo: string, absFile: string) => {
  const rel = relative(repo, absFile);
  const m = rel.match(/^(apps\/[^/]+|packages\/[^/]+|libs\/[^/]+)/);
  return m ? m[1] : rel.split("/")[0] || ".";
};

export function analyze(repo: string, changed: ChangedRange[]) {
  const t0 = Date.now();
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
  const loadMs = Date.now() - t0;

  // (A) changed ranges -> enclosing named symbols
  const symbols = new Map<string, Symbol & { _decl: Node }>();
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
          symbols.set(id, {
            id, name, kind: decl.getKindName(), file, pkg: pkgOf(repo, abs),
            line, layer: 0, degree: 0, _decl: decl,
          });
        }
      }
    }
  }

  // (B) edges among changed symbols via findReferences
  const enclosingChanged = (node: Node): (Symbol & { _decl: Node }) | undefined => {
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

  const edgeSet = new Set<string>();
  for (const s of symbols.values()) {
    const nameNode = (s._decl as any).getNameNode?.();
    if (!nameNode) continue;
    let refs: Node[] = [];
    try { refs = nameNode.findReferencesAsNodes(); } catch { continue; }
    for (const r of refs) {
      const owner = enclosingChanged(r);
      if (owner && owner.id !== s.id) edgeSet.add(`${owner.id}==>${s.id}`);
    }
  }

  const edges: Edge[] = [...edgeSet].map((e) => {
    const [source, target] = e.split("==>");
    const sa = symbols.get(source)!, sb = symbols.get(target)!;
    return { source, target, crossPkg: sa.pkg !== sb.pkg, crossFile: sa.file !== sb.file };
  });

  // degree
  const deg = new Map<string, number>([...symbols.keys()].map((k) => [k, 0]));
  for (const e of edges) { deg.set(e.source, deg.get(e.source)! + 1); deg.set(e.target, deg.get(e.target)! + 1); }

  const plain: Symbol[] = [...symbols.values()].map(({ _decl, ...s }) => ({
    ...s, degree: deg.get(s.id)!, snippet: _decl.getText().slice(0, 500), stableId: "",
  }));

  // Assign cross-commit-stable public ids: file::kind::name, disambiguated on collision.
  // Deterministic given the same diff (insertion order of the changed-symbol scan).
  const seen = new Map<string, number>();
  for (const s of plain) {
    const base = `${s.file}::${SHORT_KIND[s.kind] ?? s.kind}::${s.name}`;
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    s.stableId = n === 0 ? base : `${base}#${n + 1}`;
  }
  return {
    symbols: plain, edges, loadMs, analyzeMs: Date.now() - t0,
    filesLoaded: project.getSourceFiles().length,
  };
}
