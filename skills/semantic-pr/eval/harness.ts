// Golden-eval harness. Each fixture is `fixtures/<name>/{base,head}/**` (plain source, no nested
// git). We materialize a throwaway 2-commit repo from base→head, run the real pipeline, and
// normalize out run-varying fields so the snapshot is byte-stable. Used by both `npm run eval`
// (eval/run.ts, with UPDATE_GOLDENS) and the gating suite (tests/golden.test.ts).
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { changedRanges } from "../src/ingest.ts";
import { analyze } from "../src/analyze.ts";
import { group } from "../src/group.ts";
import { label } from "../src/label.ts";
import { render } from "../src/render.ts";
import { toArtifact, type Artifact } from "../src/contract.ts";
import type { Analysis } from "../src/types.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
export const FIXTURES_DIR = join(HERE, "fixtures");

export function listFixtures(): string[] {
  return readdirSync(FIXTURES_DIR, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

export function goldenPaths(name: string) {
  return { json: join(FIXTURES_DIR, name, "expected.json"), md: join(FIXTURES_DIR, name, "expected.md") };
}

function copyTree(src: string, dst: string) {
  for (const e of readdirSync(src, { withFileTypes: true })) {
    const s = join(src, e.name), d = join(dst, e.name);
    if (e.isDirectory()) { mkdirSync(d, { recursive: true }); copyTree(s, d); }
    else { mkdirSync(dirname(d), { recursive: true }); writeFileSync(d, readFileSync(s)); }
  }
}

/** Build a 2-commit git repo from the fixture's base/ then head/ trees. Returns the temp dir. */
function materialize(name: string): string {
  const fx = join(FIXTURES_DIR, name);
  const dir = mkdtempSync(join(tmpdir(), `eval-${name}-`));
  const git = (...a: string[]) =>
    execFileSync("git", ["-C", dir, "-c", "user.email=t@t", "-c", "user.name=t", ...a], { stdio: "pipe" });
  git("init", "-q");
  copyTree(join(fx, "base"), dir);
  git("add", "-A"); git("commit", "-q", "-m", "base");
  // clear tracked files (so head-side deletions are honored), then lay down head/
  for (const e of readdirSync(dir)) if (e !== ".git") rmSync(join(dir, e), { recursive: true, force: true });
  copyTree(join(fx, "head"), dir);
  git("add", "-A"); git("commit", "-q", "-m", "head");
  return dir;
}

/** Strip run-varying / machine-dependent fields so the JSON golden is byte-stable. */
function normalizeJson(a: Artifact): Artifact {
  const meta: any = { ...a.meta };
  delete meta.loadMs; delete meta.analyzeMs; delete meta.filesLoaded; // timing + resolver-dependent count
  return { ...a, meta };
}

export async function runFixture(name: string): Promise<{ json: Artifact; md: string }> {
  const dir = materialize(name);
  try {
    const changed = changedRanges(dir, "HEAD~1", "HEAD");
    const { symbols, edges, degraded } = await analyze(dir, changed);
    const { subGroups, cycles } = group(symbols, edges);
    const labeled = label(subGroups);
    const meta = {
      repo: name, base: "HEAD~1", head: "HEAD",
      filesChanged: changed.length, filesLoaded: 0,
      symbolCount: symbols.length, edgeCount: edges.length,
      crossFile: edges.filter((e) => e.crossFile).length,
      crossPkg: edges.filter((e) => e.crossPkg).length,
      loadMs: 0, analyzeMs: 0, degraded,
    };
    const analysis: Analysis = { meta, symbols, edges, subGroups: labeled, cycles: cycles.map((c) => c.map((s) => s.stableId)) };
    return { json: normalizeJson(toArtifact(analysis)), md: render(analysis) };
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

export const serializeJson = (j: Artifact) => JSON.stringify(j, null, 2) + "\n";
export const serializeMd = (md: string) => md + "\n";
