// Smoke test for wayfinder ticket #6 — edge-detection engine on a real Olympus PR.
// Two-tier recommendation, spike variant:
//   (A) hunk -> enclosing symbol  : done with ts-morph AST (prod would use tree-sitter)
//   (B) edges among changed symbols: ts-morph findReferencesAsNodes()
// Throwaway. Reads Olympus read-only. Commits nothing.

import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { Project, Node } from "ts-morph";

const ROOT = "/workspace/olympus";
const BASE = "HEAD~1";
const HEAD = "HEAD";

// ---- 1. changed .ts/.tsx product files + new-side changed line ranges (from diff) ----
const raw = execSync(
  `git -C ${ROOT} diff -U0 ${BASE} ${HEAD} -- 'apps/**/*.ts' 'apps/**/*.tsx' 'packages/**/*.ts' 'packages/**/*.tsx'`,
  { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
);

/** file -> array of [startLine, endLine] on the NEW side */
const changed = new Map();
let curFile = null;
for (const line of raw.split("\n")) {
  const m = line.match(/^\+\+\+ b\/(.+)$/);
  if (m) { curFile = m[1]; if (!changed.has(curFile)) changed.set(curFile, []); continue; }
  const h = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/);
  if (h && curFile) {
    const start = parseInt(h[1], 10);
    const count = h[2] === undefined ? 1 : parseInt(h[2], 10);
    if (count > 0) changed.get(curFile).push([start, start + count - 1]);
  }
}
const changedFiles = [...changed].filter(([, r]) => r.length).map(([f]) => f);
console.log(`changed product files: ${changedFiles.length}`);

// ---- 2. build the ts-morph Project over the whole monorepo (measure latency) ----
const t0 = Date.now();
const project = new Project({
  skipAddingFilesFromTsConfig: true,
  compilerOptions: {
    strict: true, skipLibCheck: true, moduleResolution: 100 /* Bundler */,
    module: 99 /* ESNext */, target: 99, baseUrl: ROOT,
    paths: {
      "@olympus/contracts": [`${ROOT}/packages/contracts/src/index.ts`],
      "@olympus/contracts/*": [`${ROOT}/packages/contracts/src/*`],
    },
  },
});
project.addSourceFilesAtPaths([
  `${ROOT}/apps/**/*.ts`, `${ROOT}/apps/**/*.tsx`,
  `${ROOT}/packages/**/*.ts`, `${ROOT}/packages/**/*.tsx`,
  `!${ROOT}/**/node_modules/**`, `!${ROOT}/**/dist/**`,
]);
project.resolveSourceFileDependencies();
const loadMs = Date.now() - t0;
console.log(`ts-morph Program: ${project.getSourceFiles().length} files loaded in ${loadMs} ms`);

// ---- 3. (A) map changed line ranges -> enclosing named symbols ----
const DECL_KINDS = new Set([
  "FunctionDeclaration", "MethodDeclaration", "ClassDeclaration",
  "InterfaceDeclaration", "TypeAliasDeclaration", "EnumDeclaration",
]);
const pkgOf = (p) => {
  const rel = p.replace(ROOT + "/", "");
  const m = rel.match(/^(apps\/[^/]+|packages\/[^/]+)/);
  return m ? m[1] : rel.split("/")[0];
};

/** key -> {id, name, kind, file, pkg, nameNode} */
const symbols = new Map();
const keyOf = (file, name, line) => `${file}::${name}@${line}`;

function enclosingNamed(node) {
  let n = node;
  while (n) {
    const k = n.getKindName();
    if (DECL_KINDS.has(k)) return n;
    if (k === "VariableDeclaration") {
      const init = n.getInitializer?.();
      if (init && (Node.isArrowFunction(init) || Node.isFunctionExpression(init))) return n;
    }
    n = n.getParent();
  }
  return undefined;
}

for (const file of changedFiles) {
  const abs = `${ROOT}/${file}`;
  const sf = project.getSourceFile(abs);
  if (!sf) { console.log(`  (no source file for ${file})`); continue; }
  const full = sf.getFullText();
  // line -> starting char offset
  const lineStart = [0];
  for (let i = 0; i < full.length; i++) if (full[i] === "\n") lineStart.push(i + 1);
  for (const [a, b] of changed.get(file)) {
    for (let ln = a; ln <= b; ln++) {
      const off = lineStart[ln - 1];
      if (off === undefined) continue;
      // first non-space column on that line
      let p = off; while (p < full.length && (full[p] === " " || full[p] === "\t")) p++;
      const desc = sf.getDescendantAtPos(p);
      if (!desc) continue;
      const decl = enclosingNamed(desc);
      if (!decl) continue;
      const nameNode = decl.getNameNode?.();
      if (!nameNode) continue;
      const name = nameNode.getText();
      const line = decl.getStartLineNumber();
      const key = keyOf(file, name, line);
      if (!symbols.has(key)) {
        symbols.set(key, {
          id: key, name, kind: decl.getKindName(), file, pkg: pkgOf(abs), nameNode,
        });
      }
    }
  }
}
console.log(`\n(A) changed symbols extracted: ${symbols.size}`);

// ---- 4. (B) edges among changed symbols via findReferences ----
const symList = [...symbols.values()];
const byNameNodeStart = new Map(); // quick "is this node inside a changed symbol" test
for (const s of symList) {
  const decl = s.nameNode.getParent();
  byNameNodeStart.set(s.id, decl);
}
function enclosingChangedSymbol(node) {
  // find nearest ancestor decl that is one of our changed symbols
  let n = node;
  while (n) {
    const k = n.getKindName();
    if (DECL_KINDS.has(k) || k === "VariableDeclaration") {
      const nn = n.getNameNode?.();
      if (nn) {
        const file = n.getSourceFile().getFilePath().replace(ROOT + "/", "");
        const key = keyOf(file, nn.getText(), n.getStartLineNumber());
        if (symbols.has(key)) return symbols.get(key);
      }
    }
    n = n.getParent();
  }
  return undefined;
}

const edges = new Set(); // "src -> dst"  (src references/depends-on dst)
const tRef = Date.now();
let refCalls = 0;
for (const s of symList) {
  let refs = [];
  try { refs = s.nameNode.findReferencesAsNodes(); refCalls++; }
  catch { continue; }
  for (const r of refs) {
    const owner = enclosingChangedSymbol(r);
    if (owner && owner.id !== s.id) edges.add(`${owner.id}==>${s.id}`);
  }
}
const refMs = Date.now() - tRef;
console.log(`(B) edges among changed symbols: ${edges.size}  (findReferences x${refCalls} in ${refMs} ms)`);

// cross-file / cross-package edges
let crossFile = 0, crossPkg = 0;
const sampleCross = [];
for (const e of edges) {
  const [a, b] = e.split("==>");
  const sa = symbols.get(a), sb = symbols.get(b);
  if (sa.file !== sb.file) crossFile++;
  if (sa.pkg !== sb.pkg) { crossPkg++; if (sampleCross.length < 8) sampleCross.push([sa, sb]); }
}
console.log(`    cross-file edges: ${crossFile}   cross-PACKAGE edges: ${crossPkg}`);

// ---- 5. cohorts = connected components (union-find over undirected edges) ----
const parent = new Map(symList.map((s) => [s.id, s.id]));
const find = (x) => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x); } return x; };
const union = (a, b) => { parent.set(find(a), find(b)); };
for (const e of edges) { const [a, b] = e.split("==>"); union(a, b); }
const groups = new Map();
for (const s of symList) { const r = find(s.id); (groups.get(r) ?? groups.set(r, []).get(r)).push(s); }
const cohorts = [...groups.values()].sort((a, b) => b.length - a.length);
console.log(`\ncohorts (connected components): ${cohorts.length}  (largest ${cohorts[0]?.length ?? 0} symbols)`);

// ---- report ----
console.log(`\n===== SAMPLE CROSS-PACKAGE EDGES (the monorepo test) =====`);
for (const [sa, sb] of sampleCross) {
  console.log(`  [${sa.pkg}] ${sa.name} (${sa.kind})  ──uses──▶  [${sb.pkg}] ${sb.name} (${sb.kind})`);
}
console.log(`\n===== TOP COHORTS =====`);
for (const c of cohorts.slice(0, 5)) {
  if (c.length < 2) continue;
  const pkgs = [...new Set(c.map((s) => s.pkg))];
  console.log(`  • cohort of ${c.length} symbols across {${pkgs.join(", ")}}:`);
  for (const s of c.slice(0, 6)) console.log(`      - [${s.pkg}] ${s.name} (${s.kind})`);
  if (c.length > 6) console.log(`      … +${c.length - 6} more`);
}
const singletons = cohorts.filter((c) => c.length === 1).length;
console.log(`\n  singleton symbols (no edge to another changed symbol): ${singletons}`);
console.log(`\n===== LATENCY =====`);
console.log(`  Program load: ${loadMs} ms   |   findReferences total: ${refMs} ms   |   end-to-end: ${Date.now() - t0} ms`);

// ---- 6. foundational-first LAYERING (longest-path on the depends-on DAG, cycles guarded) ----
// edge "owner ==> dep" means owner depends on dep, so dep is more foundational (lower layer).
const deps = new Map(symList.map((s) => [s.id, []]));    // id -> [ids it depends on]
for (const e of edges) { const [owner, dep] = e.split("==>"); if (owner !== dep) deps.get(owner).push(dep); }
const layerMemo = new Map();
function layerOf(id, stack = new Set()) {
  if (layerMemo.has(id)) return layerMemo.get(id);
  if (stack.has(id)) return 0;               // cycle guard
  stack.add(id);
  let mx = -1;
  for (const d of deps.get(id)) mx = Math.max(mx, layerOf(d, stack));
  stack.delete(id);
  const L = mx + 1;
  layerMemo.set(id, L);
  return L;
}
const degree = new Map(symList.map((s) => [s.id, 0]));
for (const e of edges) { const [a, b] = e.split("==>"); degree.set(a, degree.get(a) + 1); degree.set(b, degree.get(b) + 1); }

const compId = new Map();
cohorts.forEach((c, i) => c.forEach((s) => compId.set(s.id, i)));

const nodes = symList.map((s) => ({
  id: s.id, name: s.name, kind: s.kind, pkg: s.pkg, file: s.file.replace(/^.*\//, ""),
  layer: layerOf(s.id), degree: degree.get(s.id), cohort: compId.get(s.id),
}));
const edgeList = [...edges].map((e) => {
  const [a, b] = e.split("==>");
  const sa = symbols.get(a), sb = symbols.get(b);
  return { source: a, target: b, crossPkg: sa.pkg !== sb.pkg, crossFile: sa.file !== sb.file };
});
const cohortMeta = cohorts.map((c, i) => ({
  id: i, size: c.length, pkgs: [...new Set(c.map((s) => s.pkg))],
  crossPkg: new Set(c.map((s) => s.pkg)).size > 1,
}));

writeFileSync(new URL("./graph.json", import.meta.url), JSON.stringify({
  meta: {
    pr: "#50 — Promote, archive, and delete Ideas",
    filesChanged: changedFiles.length, filesLoaded: project.getSourceFiles().length,
    symbolCount: symList.length, edgeCount: edgeList.length,
    crossFile, crossPkg, cohortCount: cohorts.length,
    loadMs, refMs, endMs: Date.now() - t0,
  },
  nodes, edges: edgeList, cohorts: cohortMeta,
}, null, 2));
console.log(`\nwrote graph.json (${nodes.length} nodes, ${edgeList.length} edges)`);
