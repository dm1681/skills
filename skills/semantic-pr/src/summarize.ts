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

export async function summarize(subGroups: SubGroup[]): Promise<SubGroup[]> {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("[summarize] ANTHROPIC_API_KEY unset → placeholder titles (structure is still real).");
    return subGroups.map(placeholder);
  }
  const client = new Anthropic();
  const out: SubGroup[] = new Array(subGroups.length);

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

  // simple concurrency pool
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, subGroups.length) }, async () => {
    while (next < subGroups.length) { const i = next++; await one(subGroups[i], i); }
  }));
  return out;
}
