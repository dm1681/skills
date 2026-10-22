# Locked shots

A score is only comparable when the shot is reproducible. `gate.py` makes every
shot through `scripts/render_character.py`; run it by hand only to debug a shot,
with the same arguments the gate used (they are in each render's JSON sidecar).

## Full-body shot

- **Solved onto the reference.** The gate mattes the reference, takes its
  silhouette's top row, bottom row and centre column, and renders at the
  reference's resolution. The renderer solves camera distance and lens shift
  analytically from the mesh's projected vertices, so the render's silhouette
  lands on the same box.
- **The camera stays level** at `cam_height` (default half the character's
  height), so verticals stay vertical, like a turnaround sheet. Lens 85 mm.
- **Verification**: the silhouette gate reports `framing_error_px`. More than 2 px
  is a `SETUP_ERROR`; fix the shot before reading any score. The overlay
  (`overlays/silhouette_front.png`: white both, red reference only, cyan render
  only) shows the match.

## Head close-ups

- Framing comes from the mesh, through the full-body render: the chin keypoint
  and the silhouette top give the head's height band, the head fills 60% of a
  1024 px frame, with an 8% top margin. No per-character numbers.
- Views orbit the head: `front`, `q_left`/`q_right` at 45 degrees, `left`/`right`
  at 90, `back`. In `q_left` and `left` the camera moves toward the character's
  own left, so the nose points image-left.
- `view@DEG` turns the camera a further DEG. The gate renders `@2` and `@-2` to
  measure each run's noise floor.

## Look

| `--look` | Use |
|---|---|
| `studio` | File materials under a fixed key/fill/rim rig that turns with the camera, so every view is lit alike. All gates. |
| `clay` | Uniform grey: geometry only. Shape debugging. |
| `flat` | Unlit base colour: albedo only. Separates "wrong colour" from "wrong light" in `color.py`. |

Colour management is Standard (never AgX or Filmic, which wash out product
renders and shift colour), exposure 0, gamma 1. Cycles, fixed seed, denoised,
transparent background. `measure.py` composites a transparent render onto `--bg`;
pass the reference's background colour, because DreamSim weighs colour and
layout and a mismatched background dominates the score.

## Pose

Silhouette and proportions are valid only while the mesh is in the reference's
pose. That is true from `generated` until something re-poses the mesh, usually the
rig (a T-pose rig from an A-pose reference). From then on run the gate with
`--pose-changed`: shape gates turn `NOT_RUN`, and the regression against the last
same-pose stage carries the shape forward. Rigs render in rest pose.

## Mesh files

- **Front axis** belongs to the mesh file, not the character. Tripo API
  exports face `+X` (their default `export_orientation`); Studio exports and
  TRELLIS GLBs usually face `-Y`. Pass `gate.py run --front-axis=+X` when the
  file differs from the config. A wrong axis shows as a profile where the front
  should be.
- **GLB over FBX.** A Tripo FBX may carry extension-less embedded textures that
  render white; convert or fix the texture paths first.
- **.blend** files are opened directly. One saved in Edit or Texture Paint mode is
  switched to Object Mode; the file's own lights and cameras are hidden.
- The mesh is normalised to 1.75 m, feet on the floor, centred. Proportions are
  ratios, so the scale changes no score.

## Blender

`gate.py` looks in `$BLENDER`, then scoop's versioned folders, then
`Program Files`, macOS `/Applications`, and `PATH`. On some Windows shells the
scoop `blender` shim fails to spawn and its `current` junction reads as a
directory (an "untrusted mount point"). The versioned path,
`~/scoop/apps/blender/<version>/blender.exe`, always works. Pass `--blender` to
override.

Inside Blender, write the front axis with `=` (`--front-axis=-Y`): argparse reads
a bare `-Y` as a flag.
