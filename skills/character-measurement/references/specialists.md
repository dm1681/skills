# Specialists

Improving a character splits into parts, each with its own craft. A
**specialist** is a subagent that owns one part: it edits only that part's files,
works toward a named gate, and is judged by gates it cannot edit. The
orchestrator, usually the main agent, runs the gates, picks specialists from what
fails, and re-gates after each one.

## Rules every specialist follows

- **Owns one part.** It edits the files in its row below and nothing else. One
  writer per file at a time.
- **Starts from evidence.** Its brief quotes the failing gate and metric from
  `summary.json` and names the overlay or heatmap that shows the problem.
- **Leaves the yardstick alone.** The shot (`render` block, `front_axis`, mattes),
  the references, the calibration files and the tolerances belong to the
  orchestrator and the user.
- **Hands back, never self-grades.** It returns the new asset path, the files it
  changed, a target mask per shot it meant to change (white = intended region),
  and what it did not fix. The orchestrator re-gates with `--prev` set to the
  evidence from before the change, and the verifier reviews any `PASS`.

## Roster

| Role | Owns | Reads | Judged by |
|---|---|---|---|
| **reference** | references, mattes, the config's reference list; derived head views (user approves) | `gate.py plan`, `overlays/ref_mask_*.png` | `plan` clean; derived view passes tier 1 |
| **shape** | the generator input image and generator choice; gross body geometry | silhouette overlay, proportion deltas | `silhouette_front`, `proportions`, structural |
| **face** | head and face geometry (sculpt, morphs, headshot tools) | face tier 1/3/4 scores, head renders | face gates; no regression elsewhere |
| **repair** | topology: holes, blobs, floating islands, normals | clay, backface and cavity renders; checklist | regression confined to targets; structural |
| **texture** | texture atlases: seams, bleed, compression, tears | regression heatmaps, `--look flat` renders | regression with target masks; face scores hold |
| **colour** | base colour: hue, saturation, value against the reference | `color.py` on studio and flat looks | colour report improves; regression elsewhere clean |
| **materials** | non-albedo channels: roughness, metal, normal, subsurface | studio-look renders; colour `dL` studio vs flat | regression; colour report |
| **hair** | hair meshes, cards, alpha and hair textures | head silhouette region, head renders, back views | silhouette; regression |
| **rig** | armature, weights, rest pose | rest-pose regression vs the texture stage; deformation renders | regression near zero on head shots; checklist |
| **expression** | blendshapes and visemes | expression references (tier 4, report) | neutral face regression clean |
| **lighting** | the app's scene lighting and post-processing, never the measurement rig | in-app captures from a fixed camera, before and after | capture `diff`; user review |
| **scene** | placement, scale and camera framing in the app | in-app captures | capture `diff`; user review |
| **verifier** | nothing: read-only | all evidence of a claimed `PASS` | tries to refute the pass |

The measurement rig and the app's look are separate on purpose: lighting and
scene work happen in the app, and the gates keep judging the asset under the
locked studio rig.

## From verdict to specialist

| Gate result | Specialist |
|---|---|
| `silhouette_front` / `proportions` `FAIL` at `generated` | shape (regenerate) |
| silhouette difference sits in the hair (overlay) | hair |
| any face gate `LOOKALIKE` or `FAIL` | face |
| structural item: holes, islands, normals | repair |
| structural item: fused arms, legs or fingers | shape |
| regression `FAIL` | revert; the specialist that made the pass reworks it |
| colour `d_chroma` large under the flat look | colour |
| colour off only under the studio look | materials |
| `SETUP_ERROR` | the orchestrator fixes the shot; no specialist |

## Order

shape -> face -> repair -> texture, colour, materials, hair -> rig -> expression ->
lighting, scene. A `FAIL` upstream stops downstream work: texturing a face that
reads as a lookalike polishes the wrong face.

Specialists that write the same file run one after another. Ones with disjoint
files may run side by side (in a repository, each in its own worktree). Re-gate
after each specialist, so every change has its own regression evidence.

## Dispatching with the Agent tool

The default. Brief each specialist like this:

```
You are the <role> specialist for <character>.
Target: <gate>.<metric> = <value>, calibrated pass_at <x> (from <stage>/summary.json).
Look at: <stage>/overlays/<file>, <stage>/renders/<file>.
You own: <files>. Change nothing else - not the shot settings, references,
calibration files or tolerances.
Return: the new asset path; the files you changed; a target mask PNG per shot you
meant to change (white = intended region, same size as that render); what you did
not fix and why. Do not judge the result; the orchestrator re-gates.
```

Then re-gate:
`gate.py run CONFIG --stage STAGE --mesh NEW --run RUN-rN --prev <stage folder before the change> --target-mask SHOT=MASK ...`.

## Running it as a Workflow

`assets/workflow-template.js` runs the same loop deterministically: gate, plan,
one specialist at a time, re-gate, verify a `PASS`, stop on escalation or after
`maxRounds`. Use it only when the user has asked for a workflow or multi-agent
orchestration. Every agent in it sets `model` and `effort` by how hard its job
is: the gate runner is mechanical (smallest model, low effort); specialists get
medium to high; the planner and verifier judge, so they get the strongest model at
high effort. Pass:

```json
{"config": "...", "stage": "cleanup", "mesh": "...", "run": "attempt-3",
 "prev": "<previous stage folder or null>", "skillDir": "<this skill's folder>",
 "maxRounds": 3}
```

It stops and returns `NEEDS_HUMAN` when only the structural checklist is open:
that tick is the user's.
