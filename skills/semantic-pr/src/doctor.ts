// Preflight / readiness check. Uses ONLY node builtins so it runs before (and independently of)
// the heavy deps — the whole point is to diagnose a broken or partial install without crashing.
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const NM = join(ROOT, "node_modules");

// deps whose absence disables a whole capability
const TS_DEPS = ["ts-morph", "graphology", "graphology-communities-louvain", "tsx", "typescript"];

export interface Check {
  name: string;
  ok: boolean;
  detail: string;
  fix?: string;
  /** optional checks gate an add-on capability (Python); they never make the skill "not ready" */
  optional?: boolean;
}
export interface DoctorReport {
  checks: Check[];
  verdict: "ready" | "typescript-only" | "not-ready";
}

/** The required TS/runtime deps are present on disk (reused by the CLI first-run guard). */
export function depsInstalled(): boolean {
  return existsSync(NM) && TS_DEPS.every((d) => existsSync(join(NM, d)));
}

function tryVersion(bin: string, args: string[]): string | null {
  try { return execFileSync(bin, args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(); }
  catch { return null; }
}

export function doctor(): DoctorReport {
  const checks: Check[] = [];

  // node >= 18 (native test runner, fetch, stable ESM)
  const nodeMajor = parseInt(process.versions.node.split(".")[0], 10);
  checks.push({
    name: "Node.js >= 18", ok: nodeMajor >= 18,
    detail: `found v${process.versions.node}`,
    fix: "install Node.js 18 or newer",
  });

  // git (ingest shells out to it)
  const git = tryVersion("git", ["--version"]);
  checks.push({ name: "git", ok: !!git, detail: git ?? "not found", fix: "install git" });

  // required deps installed
  const missingDeps = TS_DEPS.filter((d) => !existsSync(join(NM, d)));
  checks.push({
    name: "dependencies installed", ok: missingDeps.length === 0,
    detail: missingDeps.length ? `missing: ${missingDeps.join(", ")}` : `${TS_DEPS.length} packages present`,
    fix: "run: npm install   (in skills/semantic-pr)",
  });

  // python3 (optional — enables Python symbol extraction)
  const py = tryVersion("python3", ["--version"]);
  checks.push({
    name: "python3 (Python support)", ok: !!py, optional: true,
    detail: py ?? "not found — Python files will be skipped",
    fix: "install python3 to analyze Python diffs",
  });

  // pyright language server (optional — enables precise Python edges)
  const pyright = existsSync(join(NM, ".bin", "pyright-langserver"));
  checks.push({
    name: "pyright (Python edges)", ok: pyright, optional: true,
    detail: pyright ? "present" : "not found — Python edges will be unavailable",
    fix: "run: npm install   (pyright is a listed dependency)",
  });

  const requiredOk = checks.filter((c) => !c.optional).every((c) => c.ok);
  const pythonOk = checks.filter((c) => c.optional).every((c) => c.ok);
  const verdict = !requiredOk ? "not-ready" : pythonOk ? "ready" : "typescript-only";
  return { checks, verdict };
}

const VERDICT_LINE: Record<DoctorReport["verdict"], string> = {
  "ready": "READY — TypeScript and Python analysis available.",
  "typescript-only": "TYPESCRIPT-ONLY — TS works; install python3 + deps for Python.",
  "not-ready": "NOT READY — required dependencies are missing (see fixes below).",
};

/** Human-readable report for `--doctor`. */
export function formatDoctor(r: DoctorReport): string {
  const lines = ["semantic-pr doctor", ""];
  for (const c of r.checks) {
    const mark = c.ok ? "✓" : c.optional ? "○" : "✗";
    lines.push(`  ${mark} ${c.name}`);
    lines.push(`      ${c.detail}`);
    if (!c.ok && c.fix) lines.push(`      → ${c.fix}`);
  }
  lines.push("", VERDICT_LINE[r.verdict]);
  return lines.join("\n");
}
