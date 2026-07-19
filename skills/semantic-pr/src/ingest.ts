// Ticket #5 — ingestion. Local `git diff <base>..<head>` → changed TS/TSX files + HEAD-side line ranges.
import { execFileSync } from "node:child_process";
import type { ChangedRange } from "./types.ts";

export function resolveRefs(repo: string, base?: string, head?: string) {
  const git = (args: string[]) =>
    execFileSync("git", ["-C", repo, ...args], { encoding: "utf8" }).trim();
  const headRef = head ?? "HEAD";
  let baseRef = base;
  if (!baseRef) {
    // default base = merge-base with the default branch (origin/HEAD, else main/master)
    let def = "";
    try { def = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]); } catch {}
    if (!def) { for (const c of ["main", "master"]) { try { git(["rev-parse", "--verify", c]); def = c; break; } catch {} } }
    baseRef = def ? git(["merge-base", def, headRef]) : `${headRef}~1`;
  }
  return { baseRef, headRef };
}

export function changedRanges(repo: string, base: string, head: string): ChangedRange[] {
  const raw = execFileSync(
    "git",
    ["-C", repo, "diff", "-U0", `${base}..${head}`, "--", "*.ts", "*.tsx"],
    { encoding: "utf8", maxBuffer: 128 * 1024 * 1024 },
  );
  const byFile = new Map<string, Array<[number, number]>>();
  let cur: string | null = null;
  for (const line of raw.split("\n")) {
    const f = line.match(/^\+\+\+ b\/(.+)$/);
    if (f) { cur = f[1]; if (!byFile.has(cur)) byFile.set(cur, []); continue; }
    const h = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/);
    if (h && cur) {
      const start = parseInt(h[1], 10);
      const count = h[2] === undefined ? 1 : parseInt(h[2], 10);
      if (count > 0) byFile.get(cur)!.push([start, start + count - 1]);
    }
  }
  return [...byFile].filter(([, r]) => r.length).map(([file, ranges]) => ({ file, ranges }));
}
