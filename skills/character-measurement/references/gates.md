# Gates per stage

Run each stage with
`uv run scripts/gate.py run CONFIG --stage STAGE --mesh MESH --run RUN --prev PREV_STAGE_DIR`
(`--prev` from `cleanup` on). Use one `RUN` id for the stages of one attempt, so
the evidence for that attempt sits together.

## Every stage

| Gate | Metric | Decides by |
|---|---|---|
| `silhouette_front` | `iou_aligned`, `boundary_mean_pct_h` (+ `framing_error_px` setup check) | impostor fail line; user tolerance for pass |
| `proportions` | height-normalised keypoint ratios: head height, shoulder width, hip width, waist width, torso length, leg length | user tolerance per ratio |
| `face_tier1` | DreamSim face distance (+ identity cosine if the small face is still detectable) | tier-1 calibration |
| `dreamsim_full` | whole-frame DreamSim | report only: uncalibrated |
| `structural` | the checklist: back plausible, arms separated, fingers, legs and feet, no floating islands, seams on face and chest | manual |
| `regression` | per shot LPIPS heatmap vs `--prev`; every face score's change | change within both runs' measured noise floors |

Extra gates when the reference exists: `face_tier4_<kind>` per head reference,
`face_tier3_head_front_derived` for an approved derived view, and
`silhouette_back` for a `full_body_back`.

## Stage by stage

| Stage | Mesh | What must hold | On `FAIL` |
|---|---|---|---|
| `generated` | straight from the generator, in the reference pose | silhouette and face tier 1 not worse than an impostor; structural checklist | regenerate: fix the input image's pose and silhouette first, then try another generator; never tune sampler settings to chase a score |
| `cleanup` | repaired geometry and textures | regression clean: heatmaps light up only what the pass targeted, no face score drops beyond noise; silhouette unchanged | revert the pass; repair it, never compensate downstream |
| `texture` | retextured or re-baked | regression clean with target masks; face scores hold; silhouette identical (geometry untouched) | revert; a silhouette change means geometry was edited and belongs to a geometry stage |
| `rig` | rigged, rendered in rest pose | regression vs `texture` near zero on head shots; deformation spot-checks on the checklist; `--pose-changed` if the rest pose differs from the reference pose | fix weights or rest pose; a head-shot change at rest means the bind altered the mesh |

## The lookalike band

`LOOKALIKE` means the face sits between the closest impostor and the weakest true
match: close, not the same person. It is **geometry work**: face shape,
proportions of features, jaw and brow. Texture, colour and material passes do not
move identity scores, so route a `LOOKALIKE` to the face specialist, never to a
texture pass.

## Noise decides close calls

Every face gate re-renders its shot with the camera turned +-2 degrees and records
the score spread as `noise_floor`. A score counts as `PASS` or `FAIL` only when it
clears the calibrated line by more than that; a score within noise of a line is in
the band. Without this, a 0.001 change flips a verdict that the shot itself cannot
resolve.

## The regression rule

- The likeness check compares every face score with the previous stage's. The
  allowed change is the sum of both runs' **noise floors**, measured by
  re-rendering each shot with the camera turned +-2 degrees. Noise is measured per
  run and per gate, never assumed.
- The heatmaps (`overlays/regression_*.png`) must light up only the regions the
  pass targeted. Give the gate those regions as masks
  (`--target-mask head_front=mask.png`) and it reports
  `hot_outside_mask_frac`: the share of the worst 1% of changed pixels that fall
  outside the target. That number is report-only until calibrated on passes the
  user has labelled good and bad; until then the heatmap is read by eye.

## Escalation

`summary.json` -> `next` applies these mechanically:

- Two or more failed silhouette or face gates on one stage across runs: change the
  input image or the generator, not the settings.
- `LOOKALIKE` after cleanup: geometry work on the face.
- A regression `FAIL`: revert the pass.
- `SETUP_ERROR`: fix the shot before reading anything else.
- `REPORT` gates are evidence. Say which stayed `REPORT` when reporting.

## Mistakes that cost a run

- Calibrating from a render of any existing mesh. Calibrate from 2D art only.
- Reading a head-scale threshold against a full-body face. Tier 1 has its own.
- Reusing one style's or one face size's calibration for another without
  re-running it.
- Comparing renders made with different framing, look or lighting. Re-render
  both through the gate.
- Gating on an uncalibrated metric. It stays `REPORT`.
- Editing thresholds, tolerances or calibration files to turn a verdict. Those are
  set by calibration runs and the user, never by the agent being judged.
