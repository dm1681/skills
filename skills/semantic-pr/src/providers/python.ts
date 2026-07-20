// Python provider — stdlib `ast` for symbol extraction (py_extract.py), pyright's LSP
// `textDocument/references` for precise dependency edges. Mirrors the ts-morph provider:
// only references whose enclosing symbol is another changed symbol become edges, so opening
// the changed files alone is sufficient (every such reference site lives in a changed file).
import { spawn, execFileSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { ChangedRange } from "../types.ts";
import type { LanguageProvider, RawSymbol, RawEdge, ProviderResult } from "./types.ts";
import { pkgOf } from "../pkg.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXTRACT = join(HERE, "py_extract.py");
const PYRIGHT = join(HERE, "..", "..", "node_modules", ".bin", "pyright-langserver");

/** A changed Python symbol as py_extract.py emits it (LSP-native positions). */
interface PySym extends RawSymbol {
  endLine: number;
  nameLine: number; // 0-based
  nameChar: number; // 0-based
}

/** Extract changed symbols via the stdlib-`ast` helper. Returns null if python3 is
 * unavailable (a degraded run), or the symbol list (possibly empty) on success. */
function extract(repo: string, changed: ChangedRange[]): PySym[] | null {
  const job = JSON.stringify({ repo, files: changed.map((c) => ({ file: c.file, ranges: c.ranges })) });
  let raw: string;
  try {
    raw = execFileSync("python3", [EXTRACT], { input: job, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  } catch (e) {
    console.error(`[python] python3 unavailable — cannot extract Python symbols: ${(e as Error).message}`);
    return null;
  }
  const parsed = JSON.parse(raw) as { symbols: Array<Omit<PySym, "pkg">> };
  return parsed.symbols.map((s) => ({ ...s, pkg: pkgOf(repo, join(repo, s.file)) }));
}

/** Minimal LSP client over pyright-langserver stdio. */
class Pyright {
  private srv;
  private buf = Buffer.alloc(0);
  private pending = new Map<number, (r: any) => void>();
  private diags = new Set<string>();
  private id = 0;

  constructor(bin: string) {
    this.srv = spawn(bin, ["--stdio"], { stdio: ["pipe", "pipe", "ignore"] });
    this.srv.stdout.on("data", (d: Buffer) => this.onData(d));
  }
  private onData(d: Buffer) {
    this.buf = Buffer.concat([this.buf, d]);
    for (;;) {
      const sep = this.buf.indexOf("\r\n\r\n");
      if (sep === -1) break;
      const m = /Content-Length: (\d+)/.exec(this.buf.slice(0, sep).toString());
      if (!m) { this.buf = this.buf.slice(sep + 4); continue; }
      const len = +m[1];
      if (this.buf.length < sep + 4 + len) break;
      const msg = JSON.parse(this.buf.slice(sep + 4, sep + 4 + len).toString());
      this.buf = this.buf.slice(sep + 4 + len);
      if (msg.id !== undefined && this.pending.has(msg.id)) { this.pending.get(msg.id)!(msg.result); this.pending.delete(msg.id); }
      else if (msg.method === "textDocument/publishDiagnostics") this.diags.add(msg.params.uri);
    }
  }
  private write(obj: any) {
    const m = JSON.stringify(obj);
    this.srv.stdin.write(`Content-Length: ${Buffer.byteLength(m)}\r\n\r\n${m}`);
  }
  request(method: string, params: any): Promise<any> {
    const id = ++this.id;
    this.write({ jsonrpc: "2.0", id, method, params });
    return new Promise((res) => this.pending.set(id, res));
  }
  notify(method: string, params: any) { this.write({ jsonrpc: "2.0", method, params }); }
  diagCount() { return this.diags.size; }
  kill() { try { this.srv.kill(); } catch {} }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Drive pyright to find edges among the changed symbols. `pyrightOk` is false when pyright is
 * unavailable (symbols emitted without edges — a degraded run), true otherwise even if 0 edges. */
async function edgesViaPyright(repo: string, syms: PySym[]): Promise<{ edges: RawEdge[]; pyrightOk: boolean }> {
  if (!existsSync(PYRIGHT)) {
    console.error("[python] pyright-langserver not found — emitting symbols without edges");
    return { edges: [], pyrightOk: false };
  }
  // per-file changed-symbol intervals, innermost-first, for enclosing lookup
  const byFile = new Map<string, PySym[]>();
  for (const s of syms) { (byFile.get(s.file) ?? byFile.set(s.file, []).get(s.file)!).push(s); }
  for (const list of byFile.values()) list.sort((a, b) => b.line - a.line);
  const byId = new Map(syms.map((s) => [s.id, s]));

  const enclosing = (file: string, line: number): PySym | undefined =>
    (byFile.get(file) ?? []).find((s) => s.line <= line && line <= s.endLine);

  const py = new Pyright(PYRIGHT);
  try {
    const rootUri = pathToFileURL(repo).href;
    await py.request("initialize", {
      processId: process.pid, rootUri,
      workspaceFolders: [{ uri: rootUri, name: "semantic-pr" }],
      capabilities: {},
    });
    py.notify("initialized", {});

    const files = [...byFile.keys()];
    for (const f of files) {
      const abs = join(repo, f);
      let text = "";
      try { text = readFileSync(abs, "utf8"); } catch { continue; }
      py.notify("textDocument/didOpen", {
        textDocument: { uri: pathToFileURL(abs).href, languageId: "python", version: 1, text },
      });
    }
    // let pyright bind the workspace: wait for diagnostics on the open files, or time out
    for (let i = 0; i < 150 && py.diagCount() < files.length; i++) await sleep(100);

    const edgeEv = new Map<string, string>(); // `owner==>dep` → first evidence `file:line`
    for (const s of syms) {
      let refs: Array<{ uri: string; range: { start: { line: number } } }> = [];
      try {
        refs = (await py.request("textDocument/references", {
          textDocument: { uri: pathToFileURL(join(repo, s.file)).href },
          position: { line: s.nameLine, character: s.nameChar },
          context: { includeDeclaration: false },
        })) ?? [];
      } catch { continue; }
      for (const r of refs) {
        const rf = relative(repo, fileURLToPath(r.uri));
        const line = r.range.start.line + 1; // 0-based LSP → 1-based
        const owner = enclosing(rf, line);
        if (owner && owner.id !== s.id && byId.has(owner.id)) {
          const key = `${owner.id}==>${s.id}`;
          if (!edgeEv.has(key)) edgeEv.set(key, `${rf}:${line}`);
        }
      }
    }
    const edges = [...edgeEv].map(([e, evidence]) => {
      const [source, target] = e.split("==>");
      return { source, target, evidence };
    });
    return { edges, pyrightOk: true };
  } catch (e) {
    console.error(`[python] pyright edge resolution failed: ${(e as Error).message}`);
    return { edges: [], pyrightOk: false };
  } finally {
    py.kill();
  }
}

async function analyzePy(repo: string, changed: ChangedRange[]): Promise<ProviderResult> {
  const pySyms = extract(repo, changed);
  if (pySyms === null) {
    // python3 unavailable: the whole Python slice is missing, not just edges.
    return { symbols: [], edges: [], filesLoaded: 0, degraded: ["python-symbols-unavailable"] };
  }
  if (!pySyms.length) return { symbols: [], edges: [], filesLoaded: 0 };
  const { edges, pyrightOk } = await edgesViaPyright(repo, pySyms);
  const filesLoaded = new Set(pySyms.map((s) => s.file)).size;
  // strip Python-only positional fields; the shared finalize wants a plain RawSymbol
  const symbols: RawSymbol[] = pySyms.map(({ endLine, nameLine, nameChar, ...s }) => s);
  return { symbols, edges, filesLoaded, degraded: pyrightOk ? [] : ["python-edges-unavailable"] };
}

export const pythonProvider: LanguageProvider = {
  name: "python",
  extensions: [".py"],
  analyze: analyzePy,
};
