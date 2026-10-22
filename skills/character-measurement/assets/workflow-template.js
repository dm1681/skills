export const meta = {
  name: 'character-stage-loop',
  description: 'Gate a 3D character stage, send specialists at what fails, re-gate until it passes or escalates',
  whenToUse: 'A character pipeline stage must reach PASS against its reference art and the user asked for a workflow',
  phases: [
    { title: 'Gate', detail: 'run gate.py and read summary.json' },
    { title: 'Plan', detail: 'map failing gates to specialists' },
    { title: 'Fix', detail: 'one specialist at a time on the shared asset' },
    { title: 'Verify', detail: 'adversarial review of a claimed PASS' },
  ],
}

// args: { config, stage, mesh, run, prev, skillDir, maxRounds }
const A = args || {}
for (const k of ['config', 'stage', 'mesh', 'run', 'skillDir']) {
  if (!A[k]) throw new Error(`args.${k} is required`)
}
const MAX = A.maxRounds || 3
const GATE_PY = `${A.skillDir}/scripts/gate.py`

// Model and effort by difficulty: mechanical stages cheap, judging stages strongest.
const TIER = {
  gate: { model: 'haiku', effort: 'low' },
  plan: { model: 'opus', effort: 'high' },
  verify: { model: 'opus', effort: 'high' },
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

const GATE = {
  type: 'object',
  properties: {
    verdict: { type: 'string' },
    stage_dir: { type: 'string' },
    gates: { type: 'object', description: 'gate name -> verdict' },
    next: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'stage_dir', 'gates', 'next'],
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
          role: { type: 'string', enum: Object.keys(ROLES) },
          target: { type: 'string', description: 'gate.metric = value, with its calibrated line' },
          look_at: { type: 'array', items: { type: 'string' } },
        },
        required: ['role', 'target', 'look_at'],
      },
    },
  },
  required: ['escalate', 'reason', 'tasks'],
}
const FIX = {
  type: 'object',
  properties: {
    mesh: { type: 'string', description: 'path of the asset after this change' },
    changed: { type: 'array', items: { type: 'string' } },
    target_masks: { type: 'array', items: { type: 'string' }, description: 'SHOT=mask.png per shot meant to change' },
    not_fixed: { type: 'string' },
  },
  required: ['mesh', 'changed', 'target_masks', 'not_fixed'],
}
const VERIFY = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reasons: { type: 'array', items: { type: 'string' } } },
  required: ['refuted', 'reasons'],
}

const gatePrompt = (mesh, prev, round, masks) => [
  'Run this command exactly, from the directory that holds the config:',
  `uv run ${GATE_PY} run ${A.config} --stage ${A.stage} --mesh ${mesh} --run ${A.run}-r${round}` +
    (prev ? ` --prev ${prev}` : '') + masks.map(m => ` --target-mask ${m}`).join(''),
  'Change no file. From the JSON it prints, return verdict, stage_dir, gates as',
  '{gate name: verdict}, and next. If the command fails, return verdict "ERROR"',
  'with the error text in next.',
].join('\n')

const planPrompt = g => [
  `A ${A.stage} gate returned ${g.verdict}. Summary: ${g.stage_dir}/summary.json.`,
  'Read it and the character-measurement skill references (gates.md, specialists.md).',
  'Map each failing or LOOKALIKE gate to the specialist that owns the fix, in the',
  'order from specialists.md. A FAIL upstream means no downstream task this round.',
  'Set escalate=true when next says to change the input image or generator, on a',
  'SETUP_ERROR, or when nothing a specialist owns can move the failing gate.',
].join('\n')

const specialistPrompt = (t, mesh, g) => [
  `You are the ${t.role} specialist. You own: ${ROLES[t.role].owns}.`,
  `Target: ${t.target}. Evidence: ${g.stage_dir}. Look at: ${t.look_at.join(', ')}.`,
  `Current asset: ${mesh}. Write your result as a new file beside it; never overwrite it.`,
  'Change nothing you do not own: not the shot settings, references, calibration files or tolerances.',
  'Return the new asset path, the files changed, a target mask per shot you meant to change',
  '(SHOT=path, white = intended region, same size as that render), and what you did not fix.',
  'Do not judge the result; the gate does.',
].join('\n')

const verifyPrompt = g => [
  `A ${A.stage} gate claims ${g.verdict}: ${g.stage_dir}/summary.json.`,
  'Try to refute it. Check: the renders match the reference framing (overlays),',
  'every regression heatmap lights only the targeted regions, no face score sits on',
  'its line within noise, nothing in the shot, calibration or tolerances changed',
  'between runs, and the renders show nothing a gate cannot measure. Default to',
  'refuted=true when the evidence is ambiguous.',
].join('\n')

let mesh = A.mesh
let prev = A.prev || null
let masks = []
const history = []
for (let round = 1; round <= MAX; round++) {
  const g = await agent(gatePrompt(mesh, prev, round, masks),
    { phase: 'Gate', label: `gate r${round}`, schema: GATE, ...TIER.gate })
  if (!g || g.verdict === 'ERROR') return { status: 'ERROR', round, detail: g ? g.next : 'gate agent died', history }
  history.push({ round, verdict: g.verdict, stage_dir: g.stage_dir })
  log(`round ${round}: ${g.verdict}`)

  if (g.verdict === 'PASS' || g.verdict === 'PENDING_MANUAL') {
    const v = await agent(verifyPrompt(g), { phase: 'Verify', label: `verify r${round}`, schema: VERIFY, ...TIER.verify })
    if (v && !v.refuted) {
      return g.verdict === 'PASS'
        ? { status: 'PASS', mesh, history }
        : { status: 'NEEDS_HUMAN', mesh, history, note: `tick ${g.stage_dir}/structural_checklist.md, then gate.py finalize` }
    }
    log(`verifier refuted the pass: ${v ? v.reasons.join('; ') : 'verifier died'}`)
  }

  const p = await agent(planPrompt(g), { phase: 'Plan', label: `plan r${round}`, schema: PLAN, ...TIER.plan })
  if (!p || p.escalate) return { status: 'ESCALATE', reason: p ? p.reason : 'planner died', mesh, history }

  const nextMasks = []
  // Specialists share one asset, so they run one at a time.
  for (const t of p.tasks) {
    const role = ROLES[t.role]
    const r = await agent(specialistPrompt(t, mesh, g),
      { phase: 'Fix', label: `${t.role} r${round}`, schema: FIX, model: role.model, effort: role.effort })
    if (!r) { log(`${t.role} specialist died; re-gating what exists`); break }
    mesh = r.mesh
    nextMasks.push(...r.target_masks)
    if (r.not_fixed) log(`${t.role} left: ${r.not_fixed}`)
  }
  prev = g.stage_dir
  masks = nextMasks
}
return { status: 'OUT_OF_ROUNDS', mesh, history }
