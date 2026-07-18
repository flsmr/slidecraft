// sprint_deck.js — the BUILD workflow for an ILSE sprint deck.
//
// Runs the parallel AGENT work (author sections, mind-map structure, gallery queries,
// sources, exam-focus) + a grounding critic, and returns structured content. The
// deterministic spine (scaffold, extract, assemble slides.md, render mind map, build,
// DONE report) is driven by commands/sprint-deck.md around this workflow.
//
// Invoke:  Workflow({ scriptPath: "slidecraft/workflows/sprint_deck.js", args: recipe })
//   where `recipe` is <deck>/resources/recipe.json with `sections` filled from
//   extract_chapter.py (each: {key,title,text_file,figs,target,hint}).

export const meta = {
  name: 'sprint-deck',
  description: 'Author + enrich an ILSE lecture deck from a chapter, grounded in the notes (no CIF, no SVG-gen)',
  phases: [
    { title: 'Author', detail: 'one section-author per chapter section, in parallel' },
    { title: 'Enrich', detail: 'mind-map structure, gallery queries, sources, exam-focus' },
    { title: 'Critic', detail: 'grounding-critic checks nothing was invented' },
  ],
}

// args may arrive as an object or a JSON string depending on the caller — accept both.
let r = args || {}
if (typeof r === 'string') { try { r = JSON.parse(r) } catch (e) { throw new Error('sprint-deck: args is a string but not valid JSON: ' + e.message) } }
if (!r.deck_location || !r.deck_name) throw new Error('sprint-deck: recipe must set deck_location and deck_name (got: ' + JSON.stringify(Object.keys(r)) + ')')
if (!Array.isArray(r.sections) || r.sections.length === 0) throw new Error('sprint-deck: recipe.sections is empty — fill it from extract_chapter.py output before launching')
const DECK = `${r.deck_location}/${r.deck_name}`.replace(/\\/g, '/')
const RES = `${DECK}/resources`
const FIGS = `${DECK}/public/figures`
const GUIDE = 'slidecraft/references/ilse-author-guide.md'
const FOOTER = r.footer || `${r.course}, ${r.module}`
const DATE = r.date || ''
const PREFIX = (r.sources && r.sources.prefix) || 'ch'
const SECTIONS = Array.isArray(r.sections) ? r.sections : []

const SLIDE_SCHEMA = {
  type: 'object',
  properties: {
    section: { type: 'string' },
    slides_md: { type: 'string' },
    slide_count: { type: 'number' },
    figures_used: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string' }, caption: { type: 'string' }, source: { type: 'string' } }, required: ['file', 'source'] } },
    bib_entries: { type: 'string' },
    evidence: { type: 'array', items: { type: 'object', properties: {
      slide_title: { type: 'string' },
      claims: { type: 'array', items: { type: 'object', properties: {
        statement: { type: 'string' }, locator: { type: 'string' }, excerpt: { type: 'string' } },
        required: ['statement'] } },
      figures: { type: 'array', items: { type: 'object', properties: {
        file: { type: 'string' }, intended_relationships: { type: 'string' },
        must_not: { type: 'array', items: { type: 'string' } } }, required: ['file'] } },
    }, required: ['slide_title', 'claims'] } },
    flags: { type: 'string' },
  },
  required: ['section', 'slides_md', 'slide_count', 'bib_entries'],
}
const MINDMAP_SCHEMA = { type: 'object', properties: {
  outline_md: { type: 'string' }, central: { type: 'string' } }, required: ['outline_md', 'central'] }
const GALLERY_SCHEMA = { type: 'object', properties: {
  groups: { type: 'array', items: { type: 'object', properties: {
    section: { type: 'string' },
    queries: { type: 'array', items: { type: 'object', properties: {
      label: { type: 'string' }, query: { type: 'string' } }, required: ['label', 'query'] } },
  }, required: ['section', 'queries'] } } }, required: ['groups'] }
const REFS_SCHEMA = { type: 'object', properties: {
  bibtex: { type: 'string' }, keys: { type: 'array', items: { type: 'string' } },
  notes: { type: 'string' } }, required: ['bibtex', 'keys'] }
const EXAM_SCHEMA = { type: 'object', properties: {
  focus_bullets: { type: 'array', items: { type: 'string' } }, presenter_notes: { type: 'string' } }, required: ['focus_bullets'] }
const CRITIC_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string' },
  findings: { type: 'array', items: { type: 'object', properties: {
    section: { type: 'string' }, issue: { type: 'string' }, severity: { type: 'string' }, fix: { type: 'string' } },
    required: ['issue', 'severity'] } } }, required: ['verdict', 'findings'] }

const GROUND = `HARD RULES: ground every word in the section text; invent nothing (no process, number, or class not in the notes). No centre dot, no em-dash ANYWHERE, including alt texts and notes (colon/comma; en-dash only for numeric ranges). HTML attribute values (alt="...") must contain no double quotes. Footer exactly "${FOOTER}"; date exactly "${DATE}".`

const CITE = `CITATIONS: never hand-format a citation. In ::body-13:: write "Source: [@key]" (key = surnameYEAR
derived from the printed Source line, e.g. "Source: Schmid, D. (2013)" -> [@schmid2013]; standards -> [@din8580]).
Also return bib_entries: one BibTeX entry per key you cited, fields copied from the printed Source lines /
the notes, per slidecraft/references/bibtex-guide.md (read it). Unsure about a field: leave it out.`

const DIDACTIC = `DIDACTIC CONTRACT (teach, do not just list — as important as grounding): every content slide
carries ONE clear message a first-time student grasps from the title + lead + any figure ALONE (assume NO audio).
(1) The lead sentence STATES the point, not a generic topic sentence. (2) TRANSFORM the section notes into a
TEACHING structure; do NOT mirror a source's list of examples as a slide of bullets. Prefer ONE example explained
in depth (a memorable anchor) over several name-drops; extra names/dates/proper nouns go in PRESENTER NOTES, not
on the slide face. (3) Every bullet is self-explanatory to a newcomer and passes "so what?" (a concept or
capability learned), never a cryptic proper-noun telegram. (4) Each slide serves at least one study goal. (5) If
the content is a process, sequence, comparison, hierarchy, or quantity, use a FIGURE, not a bullet list.`

// ---------- Phase 1: author every section in parallel ----------
phase('Author')
log(`Authoring ${SECTIONS.length} sections in parallel, grounded in ${PREFIX} notes + figures.`)

const authorPrompt = (s) => `You author the slides for ONE section of an IU "ILSE" Slidev lecture deck
(course "${r.course}", module ${r.module}, chapter ${r.chapter_number}: ${r.chapter_title}).

YOUR SECTION: "${s.title}"

STEP 1 read: the author guide ${GUIDE} (templates + house style + the image-sourcing ladder,
portrait-figure rule, and honest-reuse rule) and your section text
${RES}/${s.text_file} (THE source of truth: facts, figure captions, printed Source lines).
STEP 2 look at your figures at ${FIGS}/${PREFIX}_fig_NN.jpeg (your files: ${PREFIX}_fig_${s.figs || 'NN'}).
Open each with Read and match it to the caption in your section text BY CONTENT (book Figure numbers drift).
A portrait figure (taller than wide) must NOT go on a full-width slidefigure slide: use slide5 or flag it.
STEP 3 author ${s.target || '2 to 4'} slides. Focus: ${s.hint || 'the core teaching content of this section.'}

${GROUND}
${CITE}
${DIDACTIC}
Presenter notes on every slide: 3-5 say-bullets, then "- Example to tell: ..." and "- Memory hook: ...".

OUTPUT: section="${s.title}"; slides_md=the slide blocks concatenated, each starting with its
"---\\nlayout: ...\\n---" frontmatter and ending with its "<!-- ... -->" notes, dropping straight into slides.md;
slide_count; figures_used [{file,caption,source}]; bib_entries (BibTeX for every cited key);
evidence[] = ONE entry per slide you produced, {slide_title, claims:[{statement, locator, excerpt:"the verbatim
source sentence the claim came from"}], figures:[{file, intended_relationships:"the correct mapping/flow in words",
must_not:[...]}]} so a per-slide evidence sidecar can be written; flags (anything unverified or skipped).`

let authored = await parallel(SECTIONS.map((s) => () =>
  agent(authorPrompt(s), { schema: SLIDE_SCHEMA, phase: 'Author', label: `author:${s.key || s.title}` })
))

// Fan-outs must expect partial failure (rate limits, dropped agents): retry
// each failed/empty section ONCE, sequentially, before reporting it as
// failed. The DONE report shows per-section status either way.
const failedIdx = authored
  .map((a, i) => (!a || !a.slides_md || !a.slides_md.trim() ? i : -1))
  .filter((i) => i >= 0)
if (failedIdx.length) {
  log(`retrying ${failedIdx.length} failed section author(s): ${failedIdx.map((i) => SECTIONS[i].title).join(', ')}`)
  for (const i of failedIdx) {
    const again = await agent(authorPrompt(SECTIONS[i]),
      { schema: SLIDE_SCHEMA, phase: 'Author', label: `author-retry:${SECTIONS[i].key || SECTIONS[i].title}` })
    if (again && again.slides_md && again.slides_md.trim()) authored[i] = again
  }
}

// ---------- Phase 2: enrich (mind map, galleries, sources, exam) in parallel ----------
phase('Enrich')
log('Distilling the mind-map structure, gallery queries, APA references, and a concept-level exam focus.')

const sectionList = SECTIONS.map((s) => `- ${s.title} (${RES}/${s.text_file})`).join('\n')

const [mindmap, galleries, refs, exam] = await parallel([
  () => agent(`Read every section text listed below and distil a COMPLETE nested-markdown outline for a
radial mind map of chapter ${r.chapter_number} "${r.chapter_title}". Central node = a short chapter label.
One main branch per section; under each, 3-4 KEY sub-nodes taken from the notes (short labels). Invent nothing.
Sections:\n${sectionList}\nOUTPUT: central (the centre label) and outline_md (the nested markdown).`,
    { schema: MINDMAP_SCHEMA, phase: 'Enrich', label: 'mindmap-smith' }),

  () => (r.enrich && r.enrich.galleries === 'search')
    ? agent(`For each section below propose up to 6 REAL example processes/parts to illustrate it, each as a
Wikimedia Commons search query likely to return a free-licensed photo. Ground the examples in the section notes.
Sections:\n${sectionList}\nOUTPUT: groups[{section, queries[{label, query}]}].`,
        { schema: GALLERY_SCHEMA, phase: 'Enrich', label: 'gallery-curator' })
    : Promise.resolve({ groups: [] }),

  () => agent(`Compile the deck's citation DATABASE as BibTeX (NOT formatted text: rendering is a
deterministic script's job; the style is a render-time choice). Read slidecraft/references/bibtex-guide.md
first (entry types, required fields, standards need author = {{DIN}}, web pages need urldate + n.a. rule).
Then read the printed Source lines in ${RES}/${PREFIX}_extract.json (source_lines_found) and the section
texts, and verify bibliographic details against the course book's own reference list where available.
One entry per distinct source, keys = surnameYEAR (e.g. schmid2013, martin2022, din8580). NEVER fabricate
DOIs/publishers/pages: omit unverifiable fields, or cite the course book as the fallback entry.
OUTPUT: bibtex (the complete entries, valid BibTeX); keys (every key defined); notes (any uncertainty).`,
    { schema: REFS_SCHEMA, phase: 'Enrich', label: 'source-researcher' }),

  () => (r.enrich && r.enrich.exam_focus)
    ? agent(`Write a SUBTLE, concept-level "Where to Focus Your Revision" slide for chapter ${r.chapter_number}.
Ground it in the section texts (${sectionList}). Never reveal exam questions or quote scores. 5-6 bullets naming
the concepts to master (the logic, not lists). OUTPUT: focus_bullets[] and presenter_notes.`,
        { schema: EXAM_SCHEMA, phase: 'Enrich', label: 'exam-focus-analyst' })
    : Promise.resolve({ focus_bullets: [] }),
])

// ---------- Phase 3: grounding critic ----------
phase('Critic')
log('Grounding-critic: checking every authored section against its source text.')

const authoredJoined = authored.filter(Boolean).map((a) =>
  `## ${a.section} (${a.slide_count} slides)\n${a.slides_md}`).join('\n\n').slice(0, 60000)

const critic = await agent(`You are a GROUNDING critic. For each authored section below, check its bullets and
figure captions against the section text at ${RES}/section_*.txt. Flag anything not supported by the notes
(invented processes, numbers, a wrong figure source, a centre-dot or em-dash, an added class/group). Be specific.
${authoredJoined}
OUTPUT: verdict ("clean" | "needs-fixes") and findings[{section, issue, severity, fix}].`,
  { schema: CRITIC_SCHEMA, phase: 'Critic', label: 'grounding-critic' })

return {
  deck: DECK,
  sections: authored.map((a, i) => a || { section: (SECTIONS[i] || {}).title, error: 'agent returned null' }),
  mindmap, galleries, references: refs, exam_focus: exam, critic,
}
