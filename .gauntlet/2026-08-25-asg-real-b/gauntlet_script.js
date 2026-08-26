export const meta = {
  name: 'operador-b3-asg-real-gauntlet',
  description: 'Rebuild OPERADOR B3 workspace regions against real A.S.G video frames, blind builder/critic loop',
  phases: [
    { title: 'Build', detail: 'one builder per owned region file' },
    { title: 'Critic', detail: 'blind static-visual critic per part' },
    { title: 'Whole panel', model: 'opus', detail: '5 blind judges, full retrato vs bar frame' },
    { title: 'Delta panel', model: 'opus', detail: '5 blind judges, this round vs last round' },
    { title: 'Close', detail: 'compliance grep + report' },
  ],
}

const RUN = args.runDir
const REPO = args.repoRoot
const BAR = args.barDir
const MAX_ROUNDS = args.maxRounds
const HC = args.hardConstraints
const PARTS = args.parts // 12 parts, each {key, dimension, probe, ownedFiles, defectClass, barFrames, regionHint, retratoOverride?}

const RETRATO_CMD = `python scripts/painel.py --fonte simulador --simbolo WDOV26 --seed 42 --duracao 2 --workspace "OPERADOR B3" --retrato`

const BUILDER_SCHEMA = {
  type: 'object',
  required: ['part', 'changed_files', 'evidence', 'weak_spots', 'unresolved', 'screenshot_path'],
  properties: {
    part: { type: 'string' },
    changed_files: { type: 'array', items: { type: 'string' } },
    screenshot_path: { type: 'string', description: 'absolute path to the full 1480x900 --retrato PNG produced after your change' },
    evidence: { type: 'array', minItems: 1, items: { type: 'object', required: ['claim', 'probe', 'output_excerpt'],
      properties: { claim: { type: 'string' }, probe: { type: 'string' }, output_excerpt: { type: 'string' } } } },
    weak_spots: { type: 'array', minItems: 1, items: { type: 'string' } },
    unresolved: { type: 'array', items: { type: 'string' } },
  },
}

const CRITIC_SCHEMA = {
  type: 'object',
  required: ['dimension', 'modality', 'parity', 'choice', 'margin', 'blind_integrity'],
  properties: {
    dimension: { type: 'string' },
    modality: { enum: ['executed', 'interacted', 'measured', 'independent_reader', 'called_api', 'viewed', 'other'] },
    parity: { enum: ['matched', 'proxy-biased'] },
    choice: { enum: ['A', 'B', 'indistinguishable', null] },
    blocker: { type: ['string', 'null'] },
    margin: { enum: ['decisive', 'slight', 'equal'] },
    probes_run: { type: 'array', items: { type: 'string' } },
    observations: { type: 'array', items: { type: 'object', required: ['artifact', 'probe_step', 'observed'],
      properties: { artifact: { enum: ['A', 'B'] }, probe_step: { type: 'string' }, observed: { type: 'string' } } } },
    largest_gap: { type: ['object', 'null'], properties: { artifact: { enum: ['A', 'B'] }, gap: { type: 'string' }, evidence: { type: 'string' } } },
    not_probed: { type: 'array', items: { type: 'string' } },
    human_gate: { type: ['string', 'null'] },
    blind_integrity: { enum: ['intact', 'compromised'] },
  },
}

const COMPLIANCE_SCHEMA = {
  type: 'object',
  required: ['violations', 'report_written'],
  properties: {
    violations: { type: 'array', items: { type: 'string' } },
    report_written: { type: 'boolean' },
  },
}

function builderPrompt(part, r, gap, priorScreenshot) {
  const retrato = part.retratoOverride || `${RETRATO_CMD} ${RUN}\\r${r}\\evidence\\${part.key}.png`
  return `You own exactly one file (or file set) in a Gauntlet Loop rebuilding the OPERADOR B3 workspace's visuals in the FluxoPro/OPERADOR-B3 repo at ${REPO}, at the level of the real A.S.G — Algorithmic System Generation product (bar frames frozen at ${BAR}, never edit anything there).

Round ${r}. Your part: ${part.key} — dimension "${part.dimension}".
Owned files, and ONLY these — do not read, edit, or reason about any other builder's file: ${part.ownedFiles.join(', ')}
Defect class you are fixing: ${part.defectClass}
Region hint (fraction of the 1480x900 frame this part occupies): ${part.regionHint}
Reference bar frames for this part: ${part.barFrames.map(f => BAR + '\\\\' + f).join(', ')}

${gap ? `A fresh critic who never saw your code found this gap last round. Fix exactly this, do not relitigate it, do not fix twelve other things instead:\n${gap}\n` : 'This is round 1 for your part: no prior gap yet, build your best attempt at the artifact described above.'}

HARD CONSTRAINTS — inherited verbatim, non-negotiable, checked by a compliance grep after you return:
${HC}

Work only inside your owned files. If your part needs a change outside them, do not make it — return it in unresolved instead.
You do not grade your own work. No score field, no "production-ready"/"polished"/"perfect" about your own output. Every claim ships with the exact probe/command and its literal output excerpt.

When done, generate the full-workspace screenshot yourself: \`${retrato} <path>\` (or the override command given above for parts with a different evidence command) and report its absolute path in screenshot_path. Also run \`python -m pytest tests/test_ui_asg_paineis.py tests/test_app_asg_integration.py tests/test_sem_execucao.py -q\` and include the result as evidence. Then run \`grep -rn "enviar_ordem\\|executar_ordem\\|corretora\\|OrderClient\\|colocar_ordem" ${part.ownedFiles.join(' ')}\` and include the (expected-empty) output.

Name your own weak spots: where would a hostile inspection break this, what did you skip or fake.
Return only the JSON object in the schema you were given.`
}

function criticPrompt(part, aPath, bPath) {
  return `FRESH CONTEXT. You have no history with this task. Nothing you have seen before applies here.

You are judging two static screenshots of a trading-terminal UI region on ONE dimension: ${part.dimension}.

  Artifact A: ${aPath}
  Artifact B: ${bPath}
  Intended user: an operador de fluxo B3 who stares at this screen all trading session and must find each reading without hunting
  Inspection procedure: open both PNGs at real size (Read the file) and look at the region described as a fraction of the frame: ${part.regionHint}. This is a still-image comparison only — do not judge hover/focus/pressed states, motion, dark-mode variants, or any window width you were not given; those are outside what this inspection can see.

You have NOT been told which artifact is which. Do not try to work it out. Do not reason from filenames, directory names, timestamps, file extension, or which one "feels machine-made" — if you catch yourself forming a theory about where an artifact came from, drop it and return to the probe. One of the two artifacts may carry a small yellow disclaimer strip along its very top edge — that is a synthetic-data watermark this specific test harness requires and is NOT a defect of either artifact; ignore that strip entirely when judging composition, do not penalize it, do not reward its absence.

Then answer exactly one question — which artifact would that operator prefer, on ${part.dimension}, after looking at both? Pick A or B. Under uncertainty, name the weaker one; "indistinguishable" is permitted only if you inspected both fully and can name something you checked that came out equal. If you could not open one of the two files, return choice: null and name the blocker in blocker.

Every observation carries the probe step (the exact thing you did, e.g. "Read <path>, inspected fraction x 0.00-0.06 y 0.00-0.56") and the literal thing you saw. Set parity to "proxy-biased" (this whole run compares a live screenshot against a frozen video-frame capture of a real commercial product, never the live product itself) and set human_gate to "a human should confirm neither artifact copies A.S.G's logo, wordmark, or literal proprietary text, since a still-image critic can be fooled by a close paraphrase."

Then name THE SINGLE LARGEST GAP in the losing artifact: the one defect that, if fixed, would most move your answer. One gap, not a list, stated so a stranger could go fix it.

Return only the JSON object in the schema you were given.`
}

function panelPrompt(kind, aPath, bPath) {
  const dim = kind === 'whole' ? 'overall macro composition, density and visual language of the whole OPERADOR B3 workspace frame, next to the real A.S.G product' : 'whether this round\'s whole-frame candidate is a visible improvement over last round\'s whole-frame candidate'
  return `FRESH CONTEXT. You have no history with this task.

Judge two full 1480x900 screenshots of a trading-terminal UI workspace on ONE dimension: ${dim}.

  Artifact A: ${aPath}
  Artifact B: ${bPath}
  Intended user: an operador de fluxo B3 who stares at this screen all trading session.
  Inspection procedure: Read both full images at real size, look at the whole frame, compare region-by-region composition, density, and coherence of visual language (not glyph-level typography — the bar frames are only 640x270 source resolution and cannot sustain that judgment).

You have NOT been told which artifact is which; do not infer from filenames or paths. One artifact may carry a small yellow disclaimer strip along its very top edge — a synthetic-data watermark required by this test harness, NOT a defect; ignore it entirely.

Pick A or B (or indistinguishable only if you genuinely cannot tell after full inspection, naming what you checked that came out equal). If one file would not open, choice: null with blocker set.
Set parity to "proxy-biased" (screenshot vs a frozen video-frame capture, never the live product). Set human_gate to "confirm no ASG logo/wordmark/proprietary text was copied."
Name the single largest gap in the losing artifact, one gap, reproducible by a stranger.
Return only the JSON object in the schema you were given.`
}

function compliancePrompt(r, changedFiles) {
  return `Round ${r} compliance + report for a Gauntlet Loop run at ${RUN}. Repo: ${REPO}.

Run this exact grep across these files, changed this round, and report every match verbatim (there must be none):
grep -rn "enviar_ordem\\|executar_ordem\\|colocar_ordem\\|OrderClient\\|corretora\\|def executar\\|callback_execucao" ${changedFiles.join(' ')}

Also confirm no new float() cast was introduced on anything named preco/price/tick in the changed files (grep -n "float(" on them and eyeball each hit's context), and confirm none of the changed files import or call anything from fluxopro/dados or the live bus directly (panels must stay snapshot-only) — grep -n "barramento\\|Barramento\\|assinar(" on them.

Write a short round report to ${RUN}\\r${r}\\report.md: list the parts built this round, one line each, and note any compliance finding. If you find ANY violation of the grep above, list it in violations and still write the report noting it as a BLOCKER.

Return only the JSON object: {"violations": [...], "report_written": true}`
}

const candAt = (r, i) => ((r + i) % 2 === 0 ? 'A' : 'B')

let lastRoundScreenshots = {} // part.key -> path, from previous round (for delta panel baseline is the extraction retrato)
let priorGaps = {} // part.key -> gap string
let dry = 0

phase('Build')
log(`Gauntlet run ${RUN} — ${PARTS.length} parts, MAX_ROUNDS=${MAX_ROUNDS}. Part 0 (extraction) already landed at gauntlet-r0-ext.`)

for (let r = 1; r <= MAX_ROUNDS; r++) {
  if (budget.total && budget.remaining() < 400_000) {
    log(`ABORT at round ${r}: ${Math.round(budget.remaining() / 1000)}k output tokens left, a round costs ~600k. Reporting abort.`)
    break
  }
  log(`=== ROUND ${r} ===`)

  // BUILD + PART-CRITIC per part, pipelined (no barrier between parts)
  const builds = await pipeline(
    PARTS,
    (part) => agent(builderPrompt(part, r, priorGaps[part.key], lastRoundScreenshots[part.key]), {
      label: `build:${part.key}-r${r}`, phase: 'Build', model: 'sonnet', effort: 'high', schema: BUILDER_SCHEMA,
    }),
    (build, part) => {
      if (!build) return { part, build: null, critic: null }
      const i = PARTS.indexOf(part) + 1 // arena index, 1-based, never 0 (reserve 0 for nothing, WHOLE/DELTA use length+1/+2 below)
      const side = candAt(r, i)
      const barFrame = `${BAR}\\${part.barFrames[0]}`
      const aPath = side === 'A' ? build.screenshot_path : barFrame
      const bPath = side === 'A' ? barFrame : build.screenshot_path
      return parallel([() => agent(criticPrompt(part, aPath, bPath), {
        label: `critic:${part.key}-r${r}`, phase: 'Critic', model: 'opus', effort: 'high', schema: CRITIC_SCHEMA,
      })]).then(([verdict]) => ({ part, build, critic: verdict, side }))
    },
  )

  const validBuilds = builds.filter(Boolean)
  const changedFiles = validBuilds.flatMap(b => b.build ? b.build.changed_files : [])
  const newGaps = {}
  let gapsOpened = 0
  for (const b of validBuilds) {
    if (!b.critic) continue
    const ourChoice = b.critic.choice === b.side ? 'ours' : (b.critic.choice === 'indistinguishable' ? 'tie' : 'theirs')
    log(`part ${b.part.key} r${r}: critic picked ${ourChoice} (margin ${b.critic.margin || 'n/a'})`)
    if (b.critic.largest_gap && b.critic.largest_gap.gap) {
      const gap = b.critic.largest_gap.gap
      if (gap !== priorGaps[b.part.key]) gapsOpened++
      newGaps[b.part.key] = gap
    }
    if (b.build && b.build.screenshot_path) lastRoundScreenshots[b.part.key] = b.build.screenshot_path
  }
  priorGaps = newGaps

  // COMPLIANCE gate — hard veto, not advisory
  phase('Close')
  const compliance = await agent(compliancePrompt(r, changedFiles.length ? changedFiles : ['(no files changed this round)']), {
    label: `compliance-r${r}`, phase: 'Close', model: 'sonnet', effort: 'medium', schema: COMPLIANCE_SCHEMA,
  })
  const vetoed = compliance && compliance.violations && compliance.violations.length > 0
  if (vetoed) {
    log(`round ${r} VETO: compliance grep found violations: ${JSON.stringify(compliance.violations)}. No stop may be declared this round. These MUST be fixed next round regardless of critic verdicts.`)
    for (const part of PARTS) priorGaps[part.key] = priorGaps[part.key]
      ? `${priorGaps[part.key]} ALSO: compliance violation this round: ${compliance.violations.join('; ')} — fix if it touches your file.`
      : `Compliance violation somewhere this round: ${compliance.violations.join('; ')} — check if it touches your file and fix if so.`
  }

  // WHOLE + DELTA panels — need one integrated full-frame screenshot for "ours" this round.
  // Use the composicao-macro region's part builder output if present, else the last successfully
  // regenerated full retrato from any part (all parts render the FULL workspace, just differ in
  // which region changed), so pick any valid build's screenshot as "this round's whole".
  const anyShot = validBuilds.find(b => b.build && b.build.screenshot_path)
  let panelResults = null
  if (anyShot) {
    const wholeShot = anyShot.build.screenshot_path
    const iWhole = PARTS.length + 1
    const iDelta = PARTS.length + 2
    const barRef = `${BAR}\\destaque_5007_referencia_alvo.jpg`
    const prevWhole = r > 1 ? Object.values(lastRoundScreenshots)[0] : null // best-effort: previous round's shot

    const wholePanel = parallel(Array.from({ length: 5 }, (_, j) => () => {
      const side = candAt(r, iWhole)
      const a = side === 'A' ? wholeShot : barRef
      const b = side === 'A' ? barRef : wholeShot
      return agent(panelPrompt('whole', a, b), { label: `whole-r${r}-j${j + 1}`, phase: 'Whole panel', model: 'opus', effort: 'high', schema: CRITIC_SCHEMA })
        .then(v => ({ v, side }))
    }))
    const deltaPanel = (r > 1 && prevWhole) ? parallel(Array.from({ length: 5 }, (_, j) => () => {
      const side = candAt(r, iDelta)
      const a = side === 'A' ? wholeShot : prevWhole
      const b = side === 'A' ? prevWhole : wholeShot
      return agent(panelPrompt('delta', a, b), { label: `delta-r${r}-j${j + 1}`, phase: 'Delta panel', model: 'opus', effort: 'high', schema: CRITIC_SCHEMA })
        .then(v => ({ v, side }))
    })) : Promise.resolve(null)

    const [wp, dp] = await Promise.all([wholePanel, deltaPanel])
    panelResults = { wp, dp }
  } else {
    log(`round ${r}: no valid build produced a screenshot; skipping whole/delta panels this round.`)
  }

  // C2 STOP RULE — script is sole authority.
  if (panelResults) {
    const X = panelResults.wp.filter(Boolean).filter(x => x.v && x.v.choice !== null && x.v.parity === 'matched')
    const kX = X.filter(x => x.v.choice === x.side).length
    if (X.length !== 5) log(`round ${r}: no crossing available (${X.length}/5 matched verdicts, all proxy-biased by design this run — crossing can never fire; expected, see run.json).`)
    else if (!vetoed && kX >= 4) { log(`STOP: bar crossing ${kX}/5. Rare by design.`); break }

    let isDry = false
    if (panelResults.dp) {
      const D = panelResults.dp.filter(Boolean).filter(x => x.v && x.v.choice !== null)
      const kD = D.filter(x => x.v.choice === x.side).length
      if (D.length !== 5) log(`round ${r}: delta panel is ${D.length}/5 after nulls — cannot be dry`)
      isDry = r > 1 && D.length === 5 && kD <= 3 && gapsOpened === 0
      dry = isDry ? dry + 1 : 0
      log(`round ${r} delta: ${kD}/5 preferred this round's candidate. gapsOpened=${gapsOpened}. dry streak=${dry}`)
      if (!vetoed && dry >= 2) { log(`STOP: marginal-gain collapse, two consecutive dry rounds. The normal exit. Standing gaps: ${JSON.stringify(priorGaps)}`); break }
      const kPrev = D.filter(x => x.v.choice !== 'indistinguishable' && x.v.choice !== x.side).length
      if (!vetoed && isDry && kPrev >= 4) { log(`STOP: REGRESSION, previous round preferred ${kPrev}/5. Roll back to gauntlet-r${r - 1}.`); break }
    } else {
      log(`round ${r}: round 1, delta panel not applicable (never dry by definition).`)
    }
  }

  log(`round ${r} close. spend so far: ${Math.round(budget.spent() / 1000)}k output tokens.`)
}

log(`Gauntlet loop finished. Final standing gaps: ${JSON.stringify(priorGaps)}`)
return { priorGaps, lastRoundScreenshots, finalSpend: budget.spent() }
