// improve_deck.js — the POLISH workflow: agents that pass OVER an existing deck.
//
// Each pass is an independent reviewer that reads the built slides.md (+ the grounding
// notes) and returns findings. They run in PARALLEL by default (independent review, then
// the command applies fixes) — set r.mode="sequential" to chain them instead. This is the
// same machinery behind the per-slide "tweak" phrases.
//
// Invoke:  Workflow({ scriptPath: "slidecraft/workflows/improve_deck.js",
//                     args: { deck: "<deck dir>", passes: [...], mode: "parallel", scope: "all" } })

export const meta = {
  name: 'improve-deck',
  description: 'Run review/polish passes over an existing ILSE deck and return prioritized findings',
  phases: [{ title: 'Review', detail: 'grounding, house-style, critic, visual — over the whole deck' }],
}

// args may arrive as an object or a JSON string depending on the caller — accept both.
let r = args || {}
if (typeof r === 'string') { try { r = JSON.parse(r) } catch (e) { throw new Error('improve-deck: args is a string but not valid JSON: ' + e.message) } }
if (!r.deck) throw new Error('improve-deck: args.deck (the deck directory) is required')
const DECK = String(r.deck || '').replace(/\\/g, '/')
// Decks are per-slide files: slides/<name>.md hold the content, slides.md is
// only the ordered import manifest (read it first for presentation order).
const SLIDES = `${DECK}/slides/*.md (presentation order in ${DECK}/slides.md)`
const RES = `${DECK}/resources`
const SCOPE = r.scope || 'all slides'
const MODE = r.mode || 'parallel'
const PASSES = Array.isArray(r.passes) && r.passes.length
  ? r.passes
  : ['grounding-critic', 'house-style', 'slide-critic', 'didactic-critic', 'image-critic', 'visual-enrichment']

const FIND_SCHEMA = {
  type: 'object',
  properties: {
    pass: { type: 'string' },
    summary: { type: 'string' },
    findings: { type: 'array', items: { type: 'object', properties: {
      slide: { type: 'string' }, issue: { type: 'string' }, severity: { type: 'string' },
      current: { type: 'string' }, fix: { type: 'string' } }, required: ['issue', 'severity', 'fix'] } },
  },
  required: ['pass', 'findings'],
}

const PROMPTS = {
  'grounding-critic': `Read ${SLIDES} and the grounding notes in ${RES}/section_*.txt. For ${SCOPE}, flag any
claim, number, or figure source on a slide that is NOT supported by the notes (invented facts, wrong attribution,
an added class/group). This is the highest-severity pass.`,
  'house-style': `Read ${SLIDES}. For ${SCOPE}, flag house-style violations: any centre dot, any em-dash, a content
slide whose body lacks the ~10-word intro + blank line before bullets, field labels used as bullets, or a caption
with author initials. Each finding must give the exact fix (colon/comma, add intro, etc.).`,
  'slide-critic': `Read ${SLIDES}. For ${SCOPE}, judge each content slide: is the title a concept name and the body
evidence (not filler paraphrasing the title)? Flag topic-label titles, >5 bullets, monotony (too many identical
layouts in a row), and any slide carrying two ideas.`,
  'didactic-critic': `Read slidecraft/agents/didactic-critic.md and follow it as a devil's-advocate TEACHING
reviewer of ${SLIDES}. First read the deck's study-goals slide (hold the goals in memory). For ${SCOPE}, judge
whether each content slide carries ONE clear, self-explanatory message a first-time student could grasp from the
title + lead + visual ALONE (mute the presenter). Apply the full test set, especially the name-drop rule: a slide
that names 3+ examples/people/works with no stated organizing concept is a high-severity 'name-drop-list' even if
every name is grounded (do NOT pass a slide just because its bullets contain named entities — that heuristic
rewards the exact failure). Reconcile against the slide's evidence sidecar (${RES}/evidence/<slug>.json) to see the
intended message. For each finding give the extractable message (or null), the code + a concrete sentence, and a
fix (the message-first lead, the ONE anchor example to keep, what to move to notes, and any visual to add). This
pass is about teaching clarity, NOT fact-grounding (grounding-critic owns that) or figure hygiene (image-critic).`,
  'image-critic': `Read slidecraft/agents/image-critic.md and follow it as a devil's advocate. PRIMARY runner:
run \`python -m slidecraft.scripts.image_critic --deck ${DECK}\` — it inspects every NON-photographic figure on the
single vision model GPT-5.6 sol via OWUI and writes resources/image_critic_report.md + image_critic_findings.json.
Read those findings and RECONCILE each against the slide's evidence sidecar (${RES}/evidence/<slug>.json): drop any
text/label claim the sidecar's intended_labels/relationships confirm, and raise a finding to high if it hits a
\`must_not\`. If OWUI is unavailable (script errors), inspect the figures yourself with vision using the A–H
checklist. Quote the exact rendered text as evidence for every text finding.`,
  'visual-enrichment': `Read ${SLIDES}. For ${SCOPE}, name slides that are text-heavy and would teach better as a
diagram, a split image slide, or a real-photo gallery. Suggest the specific visual per slide. Suggestions only, no
invented content.`,
}

phase('Review')
log(`Running ${PASSES.length} polish passes (${MODE}) over the deck at ${DECK}.`)

const run = (name) => agent(
  `${PROMPTS[name] || `Review ${SLIDES} for ${SCOPE}.`}\n\nOUTPUT: pass="${name}", a one-line summary, and
findings[{slide, issue, severity (high|med|low), current, fix}]. Empty findings if the deck is clean on this pass.`,
  { schema: FIND_SCHEMA, phase: 'Review', label: `improve:${name}` })

let results
if (MODE === 'sequential') {
  results = []
  for (const name of PASSES) results.push(await run(name))   // one after another
} else {
  results = await parallel(PASSES.map((name) => () => run(name)))  // in parallel
}

const merged = results.filter(Boolean).flatMap((r2) => (r2.findings || []).map((f) => ({ pass: r2.pass, ...f })))
const order = { high: 0, med: 1, medium: 1, low: 2 }
merged.sort((a, b) => (order[(a.severity || 'low').toLowerCase()] ?? 3) - (order[(b.severity || 'low').toLowerCase()] ?? 3))

return { deck: DECK, mode: MODE, passes: PASSES, total_findings: merged.length, findings: merged }
