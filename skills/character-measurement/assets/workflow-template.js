export const meta = {
  name: 'character-stage-loop',
  description: 'Gate one character pipeline stage, send specialists at what fails (face candidates in parallel), verify a pass from three angles',
  whenToUse: 'One stage (generated, cleanup, texture or rig) of a 3D character must reach PASS against its reference art, and the user asked for a workflow',
  phases: [
    { title: 'Gate', detail: 'run gate.py on the current asset' },
    { title: 'Plan', detail: "map failing gates to this stage's specialists" },
    { title: 'Face', detail: 'candidates from different approaches, each gated; the best is kept' },
    { title: 'Fix', detail: 'specialists in waves; ones with disjoint files run in parallel' },
    { title: 'Assemble', detail: "combine a wave's outputs into one asset" },
    { title: 'Verify', detail: 'three lenses try to refute a pass' },
  ],
}

// One workflow = one stage. Review the evidence before starting the next stage;
// a PASS returns the arguments for that next run in `next`.
//
// args:
//   config, stage, mesh, run, skillDir   required
//   prev            evidence folder of the previous stage (the regression baseline)
//   workdir         where specialists write new files (default: <mesh folder>/wf-<run>-<stage>)
//   maxRounds       plan-and-fix rounds before giving up (default 3)
//   candidates      face approaches tried in parallel when a face gate is not PASS (default 3)
//   faceApproaches  replaces the default approach list
//   poseChanged     the asset no longer stands in the reference pose (usually the rig stage)
//   override        {model, effort} for every agent, e.g. {model: 'opus', effort: 'max'}
//   tiers           per-agent overrides, which beat `override`:
//                   {gate, plan, verify, assemble, specialists, roles: {face: {...}, ...}}
const A = args || {}
for (const k of ['config', 'stage', 'mesh', 'run', 'skillDir']) {
  if (!A[k]) throw new Error(`args.${k} is required`)
}
const STAGE_ROLES = {
  generated: ['shape', 'face', 'hair'],
  cleanup: ['repair', 'face', 'hair', 'texture'],
  texture: ['texture', 'colour', 'materials', 'hair'],
  rig: ['rig', 'expression'],
}
const NEXT_STAGE = { generated: 'cleanup', cleanup: 'texture', texture: 'rig', rig: null }
if (!STAGE_ROLES[A.stage]) throw new Error(`args.stage must be one of ${Object.keys(STAGE_ROLES).join(', ')}`)
const MAX = A.maxRounds || 3
const GATE_PY = `${A.skillDir}/scripts/gate.py`
const WORKDIR = A.workdir || `${A.mesh.replace(/[\\/][^\\/]*$/, '')}/wf-${A.run}-${A.stage}`

// ------------------------------------------------------------------ model tiers
// Defaults are tiered by difficulty: mechanical work cheap, judging strongest.
const DEFAULTS = {
  gate: { model: 'haiku', effort: 'low' },
  plan: { model: 'opus', effort: 'high' },
  verify: { model: 'opus', effort: 'high' },
  assemble: { model: 'sonnet', effort: 'medium' },
}
const ROLES = {
  shape: { owns: 'the generator input image, generator choice, gross body geometry', model: 'opus', effort: 'high' },
  face: { owns: 'head and face geometry', model: 'opus', effort: 'high' },
  repair: { owns: 'topology: holes, blobs, floating islands, normals', model: 'sonnet', effort: 'medium' },
  texture: { owns: 'texture atlases: seams, bleed, compression, tears', model: 'sonnet', effort: 'medium' },
  colour: { owns: 'base colour maps: hue, saturation, value', model: 'sonnet', effort: 'medium' },
  materials: { owns: 'roughness, metal, normal and subsurface channels', model: 'sonnet', effort: 'medium' },
  hair: { owns: 'hair meshes, cards, alpha, hair textures', model: 'opus', effort: 'medium' },
  rig: { owns: 'armature, weights, rest pose', model: 'opus', effort: 'high' },
  expression: { owns: 'blendshapes and visemes', model: 'sonnet', effort: 'medium' },
}
function tier(key, role) {
  const base = role ? ROLES[role] : DEFAULTS[key]
  const t = A.tiers || {}
  const specific = role ? ((t.roles || {})[role] || t.specialists || {}) : (t[key] || {})
  const global = A.override || {}
  return { model: specific.model || global.model || base.model,
           effort: specific.effort || global.effort || base.effort }
}
log(`tiers: gate ${JSON.stringify(tier('gate'))}, plan ${JSON.stringify(tier('plan'))}, ` +
    `verify ${JSON.stringify(tier('verify'))}, face ${JSON.stringify(tier(null, 'face'))}`)

const FACE_APPROACHES = [
  'Regenerate: improve the generator input so the face matches the reference, regenerate (scripts/tripo.py for Tripo; it spends credits), and keep the existing body',
  'Deform: move the head mesh toward the reference proportions with landmark-guided deformation in headless Blender',
  'Rebuild the head: build or fit a head from the reference with a head-generation or headshot tool, then graft it onto the body',
]

// --------------------------------------------------------------------- schemas
const NUM_OR_NULL = { type: ['number', 'null'] }
const GATE = {
  type: 'object',
  properties: {
    verdict: { type: 'string' },
    stage_dir: { type: 'string' },
    gates: { type: 'object', description: 'gate name -> verdict' },
    face_tier1_dreamsim: { ...NUM_OR_NULL, description: 'gates/face_tier1.json dreamsim_face' },
    face_tier1_noise: { ...NUM_OR_NULL, description: 'gates/face_tier1.json noise_floor.dreamsim_face' },
    next: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'stage_dir', 'gates', 'face_tier1_dreamsim', 'face_tier1_noise', 'next'],
}
const PLAN = {
  type: 'object',
  properties: {
    escalate: { type: 'boolean' },
    reason: { type: 'string' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          role: { type: 'string', enum: STAGE_ROLES[A.stage] },
          target: { type: 'string', description: 'gate.metric = value, with its calibrated line' },
          look_at: { type: 'array', items: { type: 'string' } },
          owns: { type: 'array', items: { type: 'string' }, description: 'exact files this task will replace' },
        },
        required: ['role', 'target', 'look_at', 'owns'],
      },
    },
  },
  required: ['escalate', 'reason', 'tasks'],
}
const FIX = {
  type: 'object',
  properties: {
    mesh: { type: ['string', 'null'], description: 'a complete new asset, or null if only parts were produced' },
    parts: {
      type: 'array',
      items: { type: 'object', properties: { replaces: { type: 'string' }, file: { type: 'string' } },
               required: ['replaces', 'file'] },
    },
    target_masks: { type: 'array', items: { type: 'string' }, description: 'SHOT=mask.png per shot meant to change' },
    not_fixed: { type: 'string' },
  },
  required: ['mesh', 'parts', 'target_masks', 'not_fixed'],
}
const ASSEMBLE = {
  type: 'object',
  properties: { mesh: { type: 'string' }, notes: { type: 'string' } },
  required: ['mesh', 'notes'],
}
const VERIFY = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reasons: { type: 'array', items: { type: 'string' } } },
  required: ['refuted', 'reasons'],
}

// --------------------------------------------------------------------- prompts
const gatePrompt = (mesh, runId, prev, masks) => [
  'Run this command exactly, from the directory that holds the config:',
  `uv run ${GATE_PY} run ${A.config} --stage ${A.stage} --mesh ${mesh} --run ${runId}` +
    (prev ? ` --prev ${prev}` : '') + (A.poseChanged ? ' --pose-changed' : '') +
    masks.map(m => ` --target-mask ${m}`).join(''),
  'Change no file. From the JSON it prints, return verdict, stage_dir, gates as',
  '{gate name: verdict}, and next. Read <stage_dir>/gates/face_tier1.json for',
  'dreamsim_face and noise_floor.dreamsim_face. If the command fails, return verdict',
  '"ERROR" with the error text in next.',
].join('\n')

const planPrompt = (g, refutations) => [
  `A ${A.stage} gate returned ${g.verdict}. Summary: ${g.stage_dir}/summary.json.`,
  'Read it and the character-measurement skill references (gates.md, specialists.md).',
  `This workflow runs the ${A.stage} stage only. Its specialists: ${STAGE_ROLES[A.stage].join(', ')}.`,
  'Map each failing or LOOKALIKE gate to the specialist that owns the fix, in the order',
  'from specialists.md. A face task becomes a tournament of candidate approaches.',
  'For every task, list in `owns` the exact files it will replace. If the asset is a',
  'single file, every task owns that file. Overlapping tasks run one after another;',
  'disjoint ones run in parallel.',
  'Set escalate=true when next says to change the input image or generator, on a',
  'SETUP_ERROR, when the fix belongs to another stage, or when nothing a specialist',
  'here owns can move the failing gate.',
  refutations.length ? `Verifiers refuted the last pass:\n- ${refutations.join('\n- ')}` : '',
].join('\n')

const specialistPrompt = (role, t, mesh, g, outDir, approach) => [
  `You are the ${role} specialist. You own: ${ROLES[role].owns}.`,
  approach ? `Your approach: ${approach}. Other specialists are trying other approaches in parallel.` : '',
  `Target: ${t.target}. Evidence: ${g.stage_dir}. Look at: ${t.look_at.join(', ')}.`,
  `Current asset: ${mesh}. Write every file you produce under ${outDir}/; never modify an existing file.`,
  `Replace only these files: ${t.owns.join(', ') || '(the asset itself)'}.`,
  'Change nothing else: not the shot settings, references, calibration files or tolerances.',
  'Return a complete new asset in `mesh` when you produced one, otherwise null with the',
  'replacement files in `parts`; a target mask per shot you meant to change (SHOT=path,',
  'white = intended region, same size as that render); and what you did not fix.',
  'If your approach cannot work here, say why in not_fixed and return mesh null with no parts.',
  'Do not judge the result; the gate does.',
].filter(Boolean).join('\n')

const assemblePrompt = (mesh, results, outPath) => [
  `Combine these specialist outputs into one asset based on ${mesh}:`,
  ...results.map(r => `- ${r.role}: ${r.fix.mesh ? 'full asset ' + r.fix.mesh : ''} ` +
    r.fix.parts.map(p => `${p.file} replaces ${p.replaces}`).join('; ')),
  `Write the result to ${outPath} (same format as the current asset) and touch nothing else.`,
  'Use the project\'s own build or export scripts when they exist. Return the new asset path.',
].join('\n')

const LENSES = [
  { key: 'shot', ask: 'Shot integrity: compare the render JSON sidecars (renders/*.json) with the previous ' +
    "stage's: lens, resolution, look, camera height and normalisation must match, silhouette " +
    'framing_error_px must be within 2 px, and no config, calibration or tolerance file may have changed.' },
  { key: 'regression', ask: 'Regression confinement: open every overlays/regression_*.png. Change must sit ' +
    'inside the regions the specialists targeted. A face score within its noise floor of a line is not a pass.' },
  { key: 'visual', ask: 'Visual review: look at renders/r_head_*.png and r_fullbody_front.png beside the ' +
    'reference images, and name anything visibly wrong that no gate measures: artifacts, wrong colours, ' +
    'broken hair, distorted features.' },
]
const verifyPrompt = (g, lens) => [
  `A ${A.stage} gate claims ${g.verdict}: ${g.stage_dir}/summary.json.`,
  `Try to refute it through one lens only. ${lens.ask}`,
  'Default to refuted=true when the evidence is ambiguous.',
].join('\n')

// --------------------------------------------------------------------- helpers
const RANK = { PASS: 3, LOOKALIKE: 2, REPORT: 2, NOT_RUN: 1, FAIL: 0 }
const gateRun = (mesh, tag, prev, masks, phase) =>
  agent(gatePrompt(mesh, `${A.run}-${tag}`, prev, masks),
    { phase, label: `gate ${tag}`, schema: GATE, ...tier('gate') })

const overlaps = (a, b) => !a.owns.length || !b.owns.length || a.owns.some(f => b.owns.includes(f))
function toWaves(tasks) {
  // Each task goes in the first wave after the last one it overlaps, so tasks that
  // share files keep the plan's order and disjoint ones run side by side.
  const waves = []
  for (const t of tasks) {
    let last = -1
    waves.forEach((w, i) => { if (w.some(u => overlaps(u, t))) last = i })
    ;(waves[last + 1] = waves[last + 1] || []).push(t)
  }
  return waves
}

// The face tournament: candidates from different approaches in parallel, each gated
// against the current evidence. Keep the best only if it beats the current face by
// more than both runs' noise.
async function faceTournament(t, round, mesh, g) {
  const approaches = (A.faceApproaches || FACE_APPROACHES).slice(0, A.candidates || 3)
  const entries = await parallel(approaches.map((ap, i) => async () => {
    const out = `${WORKDIR}/round${round}/face-${i + 1}`
    const fix = await agent(specialistPrompt('face', t, mesh, g, out, ap),
      { phase: 'Face', label: `face ${i + 1} r${round}`, schema: FIX, ...tier(null, 'face') })
    if (!fix || !fix.mesh) {
      log(`face ${i + 1} produced no asset: ${fix ? fix.not_fixed : 'agent died'}`)
      return null
    }
    const gr = await gateRun(fix.mesh, `r${round}-face${i + 1}`, g.stage_dir, fix.target_masks, 'Face')
    return gr && gr.verdict !== 'ERROR' ? { i, approach: ap, fix, gate: gr } : null
  }))
  const ok = entries.filter(Boolean).filter(e => e.gate.gates.regression !== 'FAIL' &&
    e.gate.face_tier1_dreamsim !== null)
  if (!ok.length) return null
  ok.sort((a, b) => (RANK[b.gate.gates.face_tier1] || 0) - (RANK[a.gate.gates.face_tier1] || 0) ||
    a.gate.face_tier1_dreamsim - b.gate.face_tier1_dreamsim)
  const best = ok[0]
  ok.forEach(e => log(`face ${e.i + 1} (${e.approach.split(':')[0]}): ${e.gate.gates.face_tier1}, ` +
    `dreamsim ${e.gate.face_tier1_dreamsim}`))
  const margin = (best.gate.face_tier1_noise || 0) + (g.face_tier1_noise || 0)
  if (g.face_tier1_dreamsim !== null && best.gate.face_tier1_dreamsim > g.face_tier1_dreamsim - margin) {
    log(`no face candidate beat the current face by more than noise (${margin.toFixed(4)})`)
    return null
  }
  return best
}

// ------------------------------------------------------------------------ loop
let mesh = A.mesh
let g = await gateRun(mesh, 'r0', A.prev || null, [], 'Gate')
if (!g || g.verdict === 'ERROR') return { status: 'ERROR', detail: g ? g.next : 'gate agent died' }
const history = [{ round: 0, verdict: g.verdict, stage_dir: g.stage_dir }]
let refutations = []

for (let round = 1; round <= MAX + 1; round++) {
  log(`round ${round - 1} verdict: ${g.verdict}`)
  if (g.verdict === 'PASS' || g.verdict === 'PENDING_MANUAL') {
    // A pass survives only if no lens refutes it; a dead verifier counts as a refutation.
    const votes = await parallel(LENSES.map(l => () =>
      agent(verifyPrompt(g, l), { phase: 'Verify', label: `verify ${l.key} r${round - 1}`,
                                  schema: VERIFY, ...tier('verify') })))
    refutations = votes.map((v, i) => !v ? `${LENSES[i].key}: verifier died`
      : v.refuted ? `${LENSES[i].key}: ${v.reasons.join('; ')}` : null).filter(Boolean)
    if (!refutations.length) {
      const next = NEXT_STAGE[A.stage]
      return g.verdict === 'PASS'
        ? { status: 'PASS', mesh, history,
            next: next ? { stage: next, mesh, prev: g.stage_dir } : null }
        : { status: 'NEEDS_HUMAN', mesh, history,
            note: `tick ${g.stage_dir}/structural_checklist.md, then run gate.py finalize on it` }
    }
    log(`verifiers refuted the pass: ${refutations.join(' | ')}`)
  }
  if (round > MAX) break

  const p = await agent(planPrompt(g, refutations),
    { phase: 'Plan', label: `plan r${round}`, schema: PLAN, ...tier('plan') })
  if (!p || p.escalate) return { status: 'ESCALATE', reason: p ? p.reason : 'planner died', mesh, history }
  refutations = []

  const faceTasks = p.tasks.filter(t => t.role === 'face')
  if (faceTasks.length) {
    const best = await faceTournament(faceTasks[0], round, mesh, g)
    if (best) {
      mesh = best.fix.mesh
      g = best.gate
      log(`face candidate ${best.i + 1} kept: ${best.approach.split(':')[0]}`)
    }
  }

  const waves = toWaves(p.tasks.filter(t => t.role !== 'face'))
  for (let w = 0; w < waves.length; w++) {
    const results = (await parallel(waves[w].map((t, k) => async () => {
      const out = `${WORKDIR}/round${round}/${t.role}-${w + 1}-${k + 1}`
      const fix = await agent(specialistPrompt(t.role, t, mesh, g, out),
        { phase: 'Fix', label: `${t.role} r${round}w${w + 1}`, schema: FIX, ...tier(null, t.role) })
      if (fix && fix.not_fixed) log(`${t.role} left: ${fix.not_fixed}`)
      return fix && (fix.mesh || fix.parts.length) ? { role: t.role, fix } : null
    }))).filter(Boolean)
    if (!results.length) continue

    let candidate = results.length === 1 && results[0].fix.mesh ? results[0].fix.mesh : null
    if (!candidate) {
      const ext = mesh.replace(/^.*(\.[^.\\/]+)$/, '$1')
      const a = await agent(assemblePrompt(mesh, results, `${WORKDIR}/round${round}/wave${w + 1}${ext}`),
        { phase: 'Assemble', label: `assemble r${round}w${w + 1}`, schema: ASSEMBLE, ...tier('assemble') })
      if (!a) { log(`assembly of wave ${w + 1} failed; wave dropped`); continue }
      candidate = a.mesh
    }
    const masks = results.flatMap(r => r.fix.target_masks)
    const gr = await gateRun(candidate, `r${round}w${w + 1}`, g.stage_dir, masks, 'Fix')
    if (!gr || gr.verdict === 'ERROR' || gr.gates.regression === 'FAIL') {
      log(`wave ${w + 1} reverted: ${gr ? 'regression ' + gr.gates.regression : 'gate failed'}`)
      continue
    }
    mesh = candidate
    g = gr
  }
  history.push({ round, verdict: g.verdict, stage_dir: g.stage_dir })
}
return { status: 'OUT_OF_ROUNDS', mesh, history, refutations }
