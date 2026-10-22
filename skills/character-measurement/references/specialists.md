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

Regeneration (shape, and the face tournament's regenerate candidate) can run
headless through `scripts/tripo.py`: image-to-model from the full-body reference,
or multiview-to-model when front plus side or back views exist. It writes the
model with a provenance JSON (inputs and their hashes, parameters, seeds, credits)
and spends credits, about 30-50 per textured model, so check `tripo.py balance`
and keep candidate counts deliberate. Tripo moderates inputs at submission: a
rejected image (code 2008) costs nothing, and revealing outfits can be rejected
even when Tripo Studio once accepted the same character, so a regenerate
candidate may need a more covered view or must hand that step to the user.

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

`assets/workflow-template.js` runs the loop deterministically. Use it only when the
user has asked for a workflow or multi-agent orchestration.

**One workflow per stage.** Each run gates one stage (`generated`, `cleanup`,
`texture` or `rig`) and may dispatch only that stage's specialists:

| Stage | Specialists |
|---|---|
| `generated` | shape, face, hair |
| `cleanup` | repair, face, hair, texture |
| `texture` | texture, colour, materials, hair |
| `rig` | rig, expression |

A fix that belongs to another stage makes the planner escalate rather than reach
across. A `PASS` returns `next`, the arguments for the following stage's run. Read
the evidence before starting it.

**Inside a run:** gate, then plan, then fix, then re-gate, until the stage passes,
escalates, or runs out of `maxRounds`.

- **Face tournament.** A face task becomes several face specialists in parallel,
  one per approach (regenerate, landmark-guided deformation, head rebuild by
  default). Each writes its own candidate, each candidate is gated, and the best
  is kept, but only if it beats the current face by more than both runs' noise.
- **Waves.** The planner lists the exact files each task replaces. Tasks with
  disjoint files run in parallel. Tasks that share a file keep the plan's order. A
  wave with several outputs is combined by an assemble agent, then gated. A wave
  whose regression fails is reverted.
- **Three-lens verification.** A claimed `PASS` faces three verifiers in parallel,
  each trying to refute it from one angle: shot integrity, regression
  confinement, and a visual review. Any refutation, or a verifier that died,
  blocks the pass and goes to the planner.

Specialists write only under `workdir` and never modify an existing file, so
parallel agents cannot collide.

**Models and effort.** Defaults are tiered by difficulty:

| Agent | Default |
|---|---|
| Gate runner | haiku, low |
| Planner, verifiers | opus, high |
| Assemble | sonnet, medium |
| Specialists | per role (face, shape and rig high) |

Overrides, most specific first: `tiers.roles.<role>` or `tiers.<agent>`, then
`tiers.specialists`, then `override`, which sets every agent at once.

```json
{"config": "...", "stage": "cleanup", "mesh": "...", "run": "attempt-3",
 "prev": "<previous stage folder or null>", "skillDir": "<this skill's folder>",
 "maxRounds": 3, "candidates": 3,
 "override": {"model": "opus", "effort": "max"},
 "tiers": {"gate": {"model": "haiku", "effort": "low"}}}
```

It returns `NEEDS_HUMAN` when only the structural checklist is open: that tick is
the user's.
