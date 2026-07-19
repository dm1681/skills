// Ticket #9 — one structured LLM call per sub-group. Claude, structured outputs, prompt caching.
// Degrades gracefully to deterministic placeholder titles when ANTHROPIC_API_KEY is unset,
// so the pipeline always produces a walkthrough.
import Anthropic from "@anthropic-ai/sdk";
import type { SubGroup } from "./types.ts";

const MODEL = process.env.SEMANTIC_PR_MODEL || "claude-opus-4-8"; // #9: opus default; set to claude-sonnet-5 for cost
const CONCURRENCY = 5;

const SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string", description: "3-6 word plain-language name for this group of changes" },
    summary: { type: "string", description: "1-2 sentences: what this group of changes does and why" },
    layer_notes: {
      type: "array",
      items: {
        type: "object",
        properties: { layer: { type: "integer" }, note: { type: "string" } },
        required: ["layer", "note"], additionalProperties: false,
      },
    },
  },
  required: ["title", "summary", "layer_notes"],
  additionalProperties: false,
} as const;

const SYSTEM =
  "You explain a group of related code changes from one pull request. You are given the changed " +
  "symbols in dependency order (foundational first) with short code snippets. Write a concise, " +
  "plain-language title and summary a reviewer can skim. Name what the change accomplishes, not " +
  "how the tool grouped it. Be specific; do not invent behavior not evidenced by the snippets.";

function placeholder(sg: SubGroup): SubGroup {
  const hub = [...sg.symbols].sort((a, b) => b.degree - a.degree)[0];
  return {
    ...sg,
    title: `${hub?.name ?? "changes"} & related`,
    summary: `${sg.symbols.length} changed symbol(s) across {${sg.pkgs.join(", ")}}. ` +
      `Set ANTHROPIC_API_KEY for LLM summaries.`,
    layerNotes: [],
  };
}

function payload(sg: SubGroup) {
  const byLayer = new Map<number, string[]>();
  for (const s of sg.symbols) {
    const line = `- [L${s.layer}] ${s.name} (${short(s.kind)}) in ${s.file}\n    ${(s.snippet ?? "").replace(/\s+/g, " ").slice(0, 240)}`;
    (byLayer.get(s.layer) ?? byLayer.set(s.layer, []).get(s.layer)!).push(line);
  }
  const layers = [...byLayer.keys()].sort((a, b) => a - b)
    .map((L) => `Layer ${L}${L === 0 ? " (foundational)" : ""}:\n${byLayer.get(L)!.join("\n")}`).join("\n\n");
  return `Packages: ${sg.pkgs.join(", ")}${sg.crossPkg ? " (cross-package)" : ""}\n\n${layers}`;
}

const short = (k: string) =>
  ({ FunctionDeclaration: "fn", MethodDeclaration: "method", ClassDeclaration: "class",
     InterfaceDeclaration: "interface", TypeAliasDeclaration: "type", EnumDeclaration: "enum",
     VariableDeclaration: "const" } as Record<string, string>)[k] ?? k;

/** Prior summaries keyed by stable group id, for incremental re-review (ticket #19). */
export type Reuse = Map<string, { title?: string; summary?: string; layerNotes?: SubGroup["layerNotes"] }>;

export async function summarize(subGroups: SubGroup[], reuse?: Reuse): Promise<SubGroup[]> {
  const out: SubGroup[] = new Array(subGroups.length);

  // #19: reuse unchanged groups by exact stable-id match; only new/changed groups get summarized.
  const todo: Array<[SubGroup, number]> = [];
  let reused = 0;
  subGroups.forEach((sg, i) => {
    const cached = reuse?.get(sg.id);
    if (cached && cached.summary != null) {
      out[i] = { ...sg, title: cached.title, summary: cached.summary, layerNotes: cached.layerNotes ?? [] };
      reused++;
    } else {
      todo.push([sg, i]);
    }
  });
  if (reused) console.error(`[summarize] reused ${reused} unchanged group(s) from --prev; ${todo.length} to summarize`);

  if (!process.env.ANTHROPIC_API_KEY) {
    if (todo.length) console.error(`[summarize] ANTHROPIC_API_KEY unset → placeholder titles for ${todo.length} group(s).`);
    for (const [sg, i] of todo) out[i] = placeholder(sg);
    return out;
  }
  const client = new Anthropic();

  const one = async (sg: SubGroup, i: number) => {
    try {
      const resp = await client.messages.create({
        model: MODEL,
        max_tokens: 1024,
        thinking: { type: "adaptive" },
        // @ts-expect-error output_config is newer than the pinned SDK types
        output_config: { effort: "medium", format: { type: "json_schema", schema: SCHEMA } },
        system: [{ type: "text", text: SYSTEM, cache_control: { type: "ephemeral" } }],
        messages: [{ role: "user", content: payload(sg) }],
      });
      const text = resp.content.find((b: any) => b.type === "text") as any;
      const parsed = JSON.parse(text.text);
      out[i] = { ...sg, title: parsed.title, summary: parsed.summary, layerNotes: parsed.layer_notes };
    } catch (err) {
      console.error(`[summarize] group ${i} failed: ${(err as Error).message} → placeholder`);
      out[i] = placeholder(sg);
    }
  };

  // simple concurrency pool over the groups that need summarizing
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, todo.length) }, async () => {
    while (next < todo.length) { const k = next++; await one(todo[k][0], todo[k][1]); }
  }));
  console.error(`[summarize] summarized ${todo.length} group(s) via ${MODEL}`);
  return out;
}
