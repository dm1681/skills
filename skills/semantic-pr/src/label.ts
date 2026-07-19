// Ticket #20 — the skill does NOT call any model. It assigns each group a deterministic
// fallback title and leaves summaries empty for the invoking agent to fill from the JSON.
// `--prev` carries an agent's prior summaries forward for unchanged groups (ticket #19).
import type { SubGroup } from "./types.ts";

/** Prior title/summaries keyed by stable group id, for incremental re-review. */
export type Reuse = Map<string, { title?: string; summary?: string; layerNotes?: SubGroup["layerNotes"] }>;

const fallbackTitle = (sg: SubGroup) => {
  const hub = [...sg.symbols].sort((a, b) => b.degree - a.degree)[0];
  return `${hub?.name ?? "changes"} & related`;
};

export function label(subGroups: SubGroup[], reuse?: Reuse): SubGroup[] {
  let reused = 0;
  const out = subGroups.map((sg) => {
    const cached = reuse?.get(sg.id);
    if (cached && cached.summary != null) {
      reused++;
      return { ...sg, title: cached.title ?? fallbackTitle(sg), summary: cached.summary, layerNotes: cached.layerNotes ?? [] };
    }
    return { ...sg, title: fallbackTitle(sg) }; // summary/layerNotes left empty for the caller
  });
  const need = subGroups.length - reused;
  if (reused) console.error(`[label] reused ${reused} group summary/ies from --prev; ${need} need summaries`);
  else console.error(`[label] ${need} groups labeled; summaries left for the invoking agent (no model called)`);
  return out;
}
