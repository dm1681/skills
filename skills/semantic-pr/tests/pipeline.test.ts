// Node-native tests (`npm test`). Build tiny synthetic git repos, run the real pipeline,
// assert layering, cross-file edges, cycle detection, small-PR degradation, and stable ids.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";

import { changedRanges } from "../src/ingest.ts";
import { analyze } from "../src/analyze.ts";
import { group } from "../src/group.ts";
import { label } from "../src/label.ts";
import { toArtifact } from "../src/contract.ts";
import { matchAny, isTestFile } from "../src/glob.ts";

/** Make a 2-commit repo: `base` files in commit 1, `head` files in commit 2. Returns the dir. */
function makeRepo(base: Record<string, string>, head: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "spr-"));
  const git = (...a: string[]) =>
    execFileSync("git", ["-C", dir, "-c", "user.email=t@t", "-c", "user.name=t", ...a], { stdio: "pipe" });
  const putAll = (files: Record<string, string>) => {
    for (const [p, c] of Object.entries(files)) { const f = join(dir, p); mkdirSync(dirname(f), { recursive: true }); writeFileSync(f, c); }
  };
  git("init", "-q");
  putAll(base); git("add", "-A"); git("commit", "-q", "-m", "base");
  putAll(head); git("add", "-A"); git("commit", "-q", "-m", "head");
  return dir;
}

/** Drive the deterministic pipeline against a repo's HEAD~1..HEAD. */
async function run(dir: string) {
  const changed = changedRanges(dir, "HEAD~1", "HEAD");
  const { symbols, edges, filesLoaded } = await analyze(dir, changed);
  const { subGroups, cycles } = group(symbols, edges);
  const labeled = label(subGroups);
  const meta = { repo: "fixture", base: "HEAD~1", head: "HEAD", filesChanged: changed.length, filesLoaded,
    symbolCount: symbols.length, edgeCount: edges.length, crossFile: edges.filter((e) => e.crossFile).length,
    crossPkg: edges.filter((e) => e.crossPkg).length, loadMs: 0, analyzeMs: 0 };
  return toArtifact({ meta, symbols, edges, subGroups: labeled, cycles: cycles.map((c) => c.map((s) => s.stableId)) });
}

test("multi-layer PR: foundational-first layering + cross-file edge", async () => {
  const dir = makeRepo(
    { "a.ts": `export function base() { return 0; }\n`,
      "b.ts": `import { base } from "./a";\nexport function top() { return base(); }\n` },
    { "a.ts": `export function base() { return 1; }\n`,
      "b.ts": `import { base } from "./a";\nexport function top() { return base() + 1; }\n` },
  );
  try {
    const art = await run(dir);
    const base = art.symbols.find((s) => s.name === "base")!;
    const top = art.symbols.find((s) => s.name === "top")!;
    assert.ok(base && top, "both symbols extracted");
    assert.equal(base.layer, 0, "base is foundational (layer 0)");
    assert.ok(top.layer > base.layer, "top builds on base");
    const e = art.edges.find((x) => x.source === top.id && x.target === base.id)!;
    assert.ok(e, "edge top -> base exists");
    assert.equal(e.crossFile, true, "edge is cross-file");
    assert.ok(e.evidence && /b\.ts:\d+/.test(e.evidence), "edge cites a reference site");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("cycle: mutual dependency is detected and flagged", async () => {
  const dir = makeRepo(
    { "c.ts": `export function f() { return 0; }\nexport function g() { return 0; }\n` },
    { "c.ts": `export function f() { return g(); }\nexport function g() { return f(); }\n` },
  );
  try {
    const art = await run(dir);
    assert.ok(art.cycles.length >= 1, "a cycle is reported");
    const cyc = new Set(art.cycles.flat());
    assert.ok(cyc.size >= 2, "cycle has >= 2 members");
    assert.ok(art.symbols.filter((s) => s.inCycle).length >= 2, "members flagged inCycle");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("small single-symbol PR degrades to one short group, no cycles", async () => {
  const dir = makeRepo(
    { "s.ts": `export function only() { return 0; }\n` },
    { "s.ts": `export function only() { return 1; }\n` },
  );
  try {
    const art = await run(dir);
    assert.equal(art.symbols.length, 1, "one changed symbol");
    assert.equal(art.groups.length, 1, "one group");
    assert.equal(art.cycles.length, 0, "no cycles");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("stable ids reproduce across runs (byte-stable minus latency)", async () => {
  const files = {
    base: { "a.ts": `export function base() { return 0; }\n`,
            "b.ts": `import { base } from "./a";\nexport function top() { return base(); }\n` },
    head: { "a.ts": `export function base() { return 2; }\n`,
            "b.ts": `import { base } from "./a";\nexport function top() { return base() * 2; }\n` },
  };
  const d1 = makeRepo(files.base, files.head);
  const d2 = makeRepo(files.base, files.head);
  try {
    const a = await run(d1), b = await run(d2);
    assert.deepEqual(a.groups.map((g) => g.id), b.groups.map((g) => g.id), "group ids stable");
    assert.deepEqual(a.symbols.map((s) => s.id).sort(), b.symbols.map((s) => s.id).sort(), "symbol ids stable");
    assert.ok(a.symbols.every((s) => !s.id.includes("@")), "symbol ids are line-free");
  } finally { rmSync(d1, { recursive: true, force: true }); rmSync(d2, { recursive: true, force: true }); }
});

test("path globs and test-file detection", () => {
  assert.equal(matchAny("tests/e2e/x.ts", ["tests/**"]), true);
  assert.equal(matchAny("apps/web/src/App.tsx", ["apps/web/**"]), true);
  assert.equal(matchAny("src/a.ts", ["tests/**"]), false);
  assert.equal(matchAny("src/a.test.ts", ["**/*.test.ts"]), true);
  assert.equal(isTestFile("src/a.test.ts"), true);
  assert.equal(isTestFile("tests/x.ts"), true);
  assert.equal(isTestFile("src/a.ts"), false);
});

test("python: cross-file edge resolves via pyright, foundational-first layering", async () => {
  const dir = makeRepo(
    { "a.py": `def base():\n    return 0\n`,
      "b.py": `from a import base\n\n\ndef top():\n    return base()\n` },
    { "a.py": `def base():\n    return 1\n`,
      "b.py": `from a import base\n\n\ndef top():\n    return base() + 1\n` },
  );
  try {
    const art = await run(dir);
    const base = art.symbols.find((s) => s.name === "base")!;
    const top = art.symbols.find((s) => s.name === "top")!;
    assert.ok(base && top, "both python symbols extracted");
    assert.equal(base.layer, 0, "base is foundational (layer 0)");
    assert.ok(top.layer > base.layer, "top builds on base");
    const e = art.edges.find((x) => x.source === top.id && x.target === base.id)!;
    assert.ok(e, "edge top -> base exists (pyright reference)");
    assert.equal(e.crossFile, true, "edge is cross-file");
    assert.ok(e.evidence && /b\.py:\d+/.test(e.evidence), "edge cites a reference site");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("python: methods are extracted with class-qualified names", async () => {
  const dir = makeRepo(
    { "svc.py": `class Service:\n    def run(self):\n        return 0\n` },
    { "svc.py": `class Service:\n    def run(self):\n        return self.helper()\n\n    def helper(self):\n        return 1\n` },
  );
  try {
    const art = await run(dir);
    const run_ = art.symbols.find((s) => s.name === "Service.run")!;
    const helper = art.symbols.find((s) => s.name === "Service.helper")!;
    assert.ok(run_ && helper, "both methods extracted with qualified names");
    const e = art.edges.find((x) => x.source === run_.id && x.target === helper.id)!;
    assert.ok(e, "edge run -> helper exists (same-file method call)");
    assert.equal(e.crossFile, false, "same-file edge");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("mixed TS + Python diff: both providers contribute symbols in one run", async () => {
  const dir = makeRepo(
    { "a.ts": `export function tbase() { return 0; }\n`,
      "m.py": `def pbase():\n    return 0\n` },
    { "a.ts": `export function tbase() { return 1; }\n`,
      "m.py": `def pbase():\n    return 1\n` },
  );
  try {
    const art = await run(dir);
    assert.ok(art.symbols.some((s) => s.name === "tbase" && s.file === "a.ts"), "TS symbol present");
    assert.ok(art.symbols.some((s) => s.name === "pbase" && s.file === "m.py"), "Python symbol present");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("--prev reuse: unchanged group ids carry a prior summary forward", async () => {
  const dir = makeRepo(
    { "a.ts": `export function base() { return 0; }\n`,
      "b.ts": `import { base } from "./a";\nexport function top() { return base(); }\n` },
    { "a.ts": `export function base() { return 1; }\n`,
      "b.ts": `import { base } from "./a";\nexport function top() { return base() + 1; }\n` },
  );
  try {
    const changed = changedRanges(dir, "HEAD~1", "HEAD");
    const { symbols, edges } = await analyze(dir, changed);
    const { subGroups } = group(symbols, edges);
    const gid = subGroups[0].id;
    const reuse = new Map([[gid, { title: "Prior title", summary: "prior summary" }]]);
    const out = label(subGroups, reuse);
    const g = out.find((x) => x.id === gid)!;
    assert.equal(g.summary, "prior summary", "summary reused by stable id");
    assert.equal(g.title, "Prior title", "title reused");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
