---
name: character-measurement
description: Measure a 3D character against its reference art and gate each pipeline stage on scores instead of eyeballing - silhouette, proportions, face likeness at full-body and head scale, colour, and before/after regressions, with evidence recorded per run. Use when building or improving a 3D character from reference images, judging whether a render matches its reference, checking a cleanup, texture or rig pass for regressions, or dispatching specialist agents (shape, face, colour, texture, materials, hair, rig, lighting, scene) on a character asset.
version: 0.3.0
---

# Character measurement

Every stage of a character asset passes through **gates**: a locked shot, a fixed
command, a calibrated threshold, and a verdict saved with its JSON. The meshes are
what the gates judge; the reference art is what they are judged against.

## Ground rules

- **Thresholds come from 2D reference art or an explicit user tolerance.** The
  project's meshes only ever get scored, because they are the thing being
  improved. Renders of them never calibrate anything, in any role.
- **Compare locked shots only.** Every render comes from
  `scripts/render_character.py` with the framing, lens, lighting and colour
  management it fixes. A score moves because the asset changed, never because the
  shot did.
- **An uncalibrated metric is evidence, not a gate.** It reports as `REPORT`.
  Leave it ungated until a calibration separates it or the user sets a tolerance.
- **Every face score carries its tier** (below). Head-scale thresholds never
  apply to a full-body face.

## Procedure

1. **Write the character config** next to the project's art: the references that
   exist, what each is for, and the calibration files the character is gated
   against. Read [references/config.md](references/config.md). Done when
   `uv run scripts/gate.py plan CONFIG` lists every gate the references allow and
   reports no config errors.
2. **Calibrate** for the art style: tier-4 and tier-1 face, and shape fail lines.
   Read [references/calibration.md](references/calibration.md), including where
   impostor art comes from. Done when each metric `plan` lists is either
   calibrated or report-only with a stated reason.
3. **Run the stage gate** on the mesh:
   `uv run scripts/gate.py run CONFIG --stage STAGE --mesh MESH --run RUN [--prev PREV_STAGE_DIR]`.
   Stages: `generated`, `cleanup`, `texture`, `rig`. Read
   [references/gates.md](references/gates.md) for what each stage checks and
   what to do on each verdict. Done when the stage folder holds `summary.json`.
4. **Look at the evidence**: the silhouette overlay, the regression heatmaps, and
   the head renders. Tick `structural_checklist.md`, then run
   `uv run scripts/gate.py finalize STAGE_DIR`. Done when the verdict is `PASS`,
   `FAIL` or `LOOKALIKE`, not `PENDING_MANUAL`.
5. **Act on the verdict** using `summary.json` -> `next`, which applies the
   escalation rules mechanically. To improve the asset, dispatch specialists per
   [references/specialists.md](references/specialists.md).
6. **Report** the verdict, the stage folder, the face tier of each face score, and
   which gates stayed `REPORT` and why.

## Verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | Clears the calibrated line, by more than the run's measured noise, or meets the user's tolerance. |
| `FAIL` | As far from the reference as a different character (by more than the noise), beyond a user tolerance, or a regression beyond measured noise. |
| `LOOKALIKE` | Face score between the closest impostor and the weakest true match. Fix with geometry (face shape); texture passes do not move identity. |
| `BORDERLINE` | Shape metric past the impostor fail line but short of the user's tolerance. |
| `REPORT` | No calibration or tolerance: recorded, never gating. |
| `MANUAL` / `PENDING_MANUAL` | The structural checklist is still open. |
| `SETUP_ERROR` | The render missed the reference framing by more than 2 px. Fix the shot, not the model. |
| `NOT_RUN` | Input missing, e.g. no face found. |

## Face tiers

| Tier | Compares | Available | Thresholds |
|---|---|---|---|
| 1 | Full-body reference vs a full-body render at the same framing. Face located by body keypoints, compared at the reference's face size. | Always | Tier-1 calibration at that face size |
| 2 | Head close-ups of one mesh across passes (`diff`). Measures change, not likeness; it is the face the user reviews. | Always | Measured noise floor |
| 3 | Head render vs a head view derived from the full-body reference. Labelled "vs derived ref". | Only after the derived view passes tier 1 against the original and the user approves it | Tier-4 calibration |
| 4 | Head render vs a real head-sheet view. | When a head sheet exists | Tier-4 calibration |

## Scripts

`uv run` installs each script's dependencies, including CUDA PyTorch, from its
inline metadata. Every command prints one JSON object to stdout.

| Script | Job |
|---|---|
| `gate.py` | `plan`, `run`, `finalize`: renders the locked shots, runs the gates, writes evidence. |
| `render_character.py` | Locked shots inside Blender (`blender -b --factory-startup -P ... --`). Full-body camera solved onto the reference's silhouette box; head framing from keypoints; 45-degree quarter views. |
| `measure.py` | `compare` (face tiers 1 and 4), `diff` (LPIPS heatmap), `calibrate` (face). |
| `silhouette.py` | `matte`, `landmarks`, `compare` (IoU, boundary, proportions), `calibrate` (shape fail lines). |
| `color.py` | Per-region colour difference (report-only). |
| `tripo.py` | Generate a mesh through the Tripo API (image or multiview input) with its provenance; key from `TRIPO_API_KEY`. Spends credits. |

Shots, views, the pose caveat and Blender setup:
[references/rendering.md](references/rendering.md). Evidence layout and JSON
examples: [references/evidence.md](references/evidence.md).
