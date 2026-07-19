// Minimal glob → RegExp for path filtering (--include/--exclude). Supports ** * ?.
// Avoids a dependency; good enough for path patterns like "tests/**", "**/*.test.ts", "apps/web/**".
export function globToRe(glob: string): RegExp {
  let re = "^";
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === "*") {
      if (glob[i + 1] === "*") { re += ".*"; i++; if (glob[i + 1] === "/") i++; }
      else re += "[^/]*";
    } else if (c === "?") {
      re += "[^/]";
    } else {
      re += c.replace(/[.+^${}()|[\]\\]/g, "\\$&");
    }
  }
  return new RegExp(re + "$");
}

export const matchAny = (file: string, patterns: string[]) =>
  patterns.some((p) => globToRe(p).test(file));

/** Test-file heuristic: tests/ · test/ · __tests__/ dirs, or *.test/*.spec .ts/.tsx/.js/.jsx */
export const isTestFile = (file: string) =>
  /(^|\/)(tests?|__tests__)\//.test(file) || /\.(test|spec)\.[tj]sx?$/.test(file);
