# Character config

One JSON file per character, kept in the project next to its art, never in the
skill. Relative paths resolve against the config file. `scripts/config.py` is the
schema; `assets/character.example.json` is a filled-in example.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `character` | yes | Name used for evidence folders and as the calibration group. |
| `references` | yes | The 2D art that exists for this character (below). One `full_body_front` is mandatory. |
| `front_axis` | no | Direction the character faces in the mesh file: `-Y` (default), `+Y`, `+X`, `-X`. Confirm on a first render. |
| `calibration.files` | no | `tier4`, `tier1`, `shape`: the calibration JSON this character is gated against. Shared by every character of one art style. |
| `calibration.images` | no | Extra **front-facing 2D art** of this character for face calibration. |
| `tolerances` | no | User-set pass lines for shape metrics. Requires `set_by`. |
| `render` | no | `lens` (85) and `cam_height` (0.5 of character height). Change only to match a reference's evident camera, then keep it fixed for every stage. |
| `evidence_root` | no | Where gate evidence goes (default `measure-out`). |

## Reference kinds

Gates follow from the kinds listed. Every gate works from the single
`full_body_front`; each extra kind upgrades or adds one.

| Kind | Render view | Gate it serves | Upgrade over full-body only |
|---|---|---|---|
| `full_body_front` | full-body front | silhouette, proportions, face tier 1, colour | the baseline |
| `full_body_back` | full-body back | back silhouette | the back stops being unmeasured |
| `head_front` | head front | face tier 4 | head-scale likeness, real thresholds |
| `head_q_left` / `head_q_right` | head 45 degrees | face tier 4 | likeness off-axis, where generators drift |
| `head_side_left` / `head_side_right` | head 90 degrees | face tier 4 (profile, report-weight) | nose/jaw profile |
| `head_back` | head back | face tier 4 (hair only) | back of the hair |
| `head_front_derived` | head front | face tier 3, labelled "vs derived ref" | head-scale check when no sheet exists |
| `expression` | none | calibration only (same-character pairs) | sharper face thresholds |

Each reference may override `view` and give a `matte` (a mask PNG) when the
automatic matte is wrong. Pair a head reference with a view by **where the nose
points**, not by its file name: in `q_left` and `left` the nose points
image-left.

## A derived head reference

When only a full-body reference exists, a head view can be generated or upscaled
from it (tier 3). It becomes a reference only after both of these:

1. It passes tier 1 against the original: `uv run scripts/measure.py compare
   ORIGINAL_FULL_BODY DERIVED_HEAD --tier 1`, judged against the tier-1
   calibration.
2. The user looks at it and approves it. Record that in the config:
   `{"path": "...", "kind": "head_front_derived", "approved_by": "<user>",
   "tier1_evidence": "<path to that JSON>"}`. The loader refuses a derived
   reference without `approved_by`.

It never enters calibration: the generator's drift is built into it.

## Tolerances

A shape pass line cannot be calibrated from 2D art alone (see
[calibration.md](calibration.md)), so it is a user decision, recorded as one:

```json
"tolerances": {
  "set_by": "user, 2026-10-21",
  "iou_aligned": 0.93,
  "boundary_mean_pct_h": 0.4,
  "proportions": {"shoulder_width": 0.01, "leg_length": 0.015}
}
```

Agents propose tolerances with the evidence behind them; the user sets them.
Without them, shape gates can `FAIL` (worse than an impostor) but never `PASS`.
