// Shared package attribution. A symbol's "package" is its monorepo workspace
// (apps/foo, packages/bar, libs/baz) or else the top-level directory. Language-agnostic.
import { relative } from "node:path";

export function pkgOf(repo: string, absFile: string): string {
  const rel = relative(repo, absFile);
  const m = rel.match(/^(apps\/[^/]+|packages\/[^/]+|libs\/[^/]+)/);
  return m ? m[1] : rel.split("/")[0] || ".";
}
