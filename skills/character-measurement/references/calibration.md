# Calibration

A score means nothing alone. Calibration measures each metric on **same-character
pairs** and **different-character pairs (impostors)** and keeps the metric only
where the two separate. Everything here comes from 2D reference art. The project's
meshes, and renders of them, never enter a calibration: they are what the gates
judge, so using them would let a flawed model set its own pass line.

## What 2D art can calibrate

| Calibration | Command | Same-character pairs | Impostors | Gives |
|---|---|---|---|---|
| Face tier 4 | `measure.py calibrate --config A --config B ...` | one character's front-facing head art (head sheet front, expressions) | other characters' front-facing head art | `pass_at`, `fail_at`, the lookalike band |
| Face tier 1 | `... --tier 1 --face-px N` | the same art, every face cropped by keypoints and degraded to N px | other characters' art, including full-body references | the same, at full-body scale |
| Shape | `silhouette.py calibrate --config A --config B ...` | none (see below) | other characters' full-body references | a fail line only |

`N` is the face box of the full-body reference:
`uv run scripts/silhouette.py landmarks REF` -> `head_box[2]`. `gate.py plan`
warns when a reference's face size is more than 20% off the calibrated size.

Inputs come from each config: its front-facing references (`full_body_front`,
`head_front`, `expression`) plus `calibration.images`. Only front-facing art is
used because every gate compares a view with the same view; mixing front and
profile pairs widens the same-character spread and loosens the line.

## Reading the output

- `separated: true`: `pass_at` is the weakest true match, `fail_at` the closest
  impostor. Scores between them are the **lookalike band**.
- `separated: false`: the distributions overlap. The metric stays report-only.
  A threshold picked inside an overlap would pass impostors or fail the
  character itself, so pick none.
- A shape fail line says "no closer to its own reference than another character
  is". It catches a wrong silhouette; it cannot certify a right one. Impostors in
  a different pose from the character (T-pose vs A-pose) give a lenient line.

## Shape has no calibrated pass line

A pass line needs same-character examples of the silhouette: two images of one
character in one pose and framing. Reference sets rarely contain that, and
renders of the existing meshes are excluded by the ground rule. So a shape pass
line is a **user tolerance** (`tolerances` in the config, with `set_by`). An agent
may propose one with the evidence behind it; the user sets it.

## Where impostor art comes from

Impostors must be the **same art style** as the character, or the line is
trivially loose (a photo-real human tells a stylised elf apart from anything).

1. Other characters' references in the same project.
2. Character art of the same style from other projects or sheets.
3. Generated portraits and full-body images of *different* characters in the same
   style. Keep them as 2D art with the prompt and seed recorded beside them, and
   check none resembles the character being gated.

Never use a render of any existing mesh, the character's own or another's.

A tier-4 calibration needs head-scale art (at least 40 px between the eyes) from
**two or more characters**. With one character it reports
`need both same- and different-character pairs` and tier-4 gates stay
report-only.

## When to re-run

- A new art style, or a character whose style differs from the calibration set.
- A character's full-body face size is more than 20% off `face_px` (tier 1).
- The render setup changed: lens, look, light rig, resolution.
- A reference was added, replaced or re-matted, or a new character joined the
  impostor set.

Keep one set of calibration files per art style in the project, and point every
character of that style at them through `calibration.files`.
