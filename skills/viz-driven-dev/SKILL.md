---
name: viz-driven-dev
description: Hypothesis-first visualization workflow for feature development - build the plot, overlay, rendered artifact, or video that would show the feature's effect before implementing it, then regenerate the same artifact from real output to confirm or refute the hypothesis. Use when building or changing a feature whose effect can be seen or watched - signals over time, overlays on media, spatial or sequential behavior, state evolution, or any before/after comparison.
---

# Visualization-driven development

Treat the visualization as the feature's hypothesis-and-check, not an
afterthought.

## The loop

1. **Build the visualization first, before implementing the feature.**
   Generate it against expected, synthetic, or baseline data so it cements
   understanding and states an explicit *hypothesis*: what should the result
   look like if the feature works?
2. **Then implement** the feature.
3. **Then regenerate the same visualization for real**, against actual output,
   and compare it to the hypothesis to confirm or refute it.

Prefer watchable or lookable artifacts — overlays, rendered media, charts,
side-by-side before/after — over terminal tables when the effect is spatial or
temporal. Tell the user where the artifact is saved so they can look at it.

## Prefer videos to convey understanding

Generate videos (before, after, or both side-by-side) whenever they would help
the user *understand* the effect — and that is most of the time, not the
exception. A playhead sweeping an analysis, an overlay riding the actual
footage, an animated before/after: these convey temporal and spatial behavior
that a still frame cannot, and they are how the user catches errors a static
artifact would hide.

- Default to producing a video when the effect is temporal, spatial, or
  sequential (signals over time, tracking or overlays on media, transitions,
  simulations, state evolution). Skip it only when a video genuinely adds
  nothing over a still — and say so explicitly when you skip.
- A "before" video shows the old, baseline, or naive behavior; an "after"
  shows the new, correct behavior; both, side-by-side or sequential, is ideal
  for proving a change did what was intended.
- Make videos honest: label what each panel is, and if an artifact is later
  found wrong or misleading, keep it but caption it as not-entirely-correct
  rather than silently deleting it.
- Always tell the user the path, and surface the file so they can watch it.
