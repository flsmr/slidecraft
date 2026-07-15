// gebhardt_augment.js — author + verify AUGMENTING slides grounded in an EXTERNAL academic
// source (a book chapter), for a deck that has been reduced to its lecture-note core.
// Parallel cluster-authors produce English ILSE slides with [@<sourcekey>, p. NN] markers;
// a grounding-critic verifies every fact against the same source cluster text. Figure-
// recreation proposals come back for the figure generator.
//
// Invoke: Workflow({ scriptPath: ".../gebhardt_augment.js", args: {
//   deck_location, deck_name,           // OR: deck (a full path)
//   source_dir,                          // sub-dir of <deck>/resources holding the extracted
//                                        //   cluster_*.txt + figures/ (default "gebhardt")
//   source_key,                          // bib key for citations (default "gebhardt2025")
//   page_offset,                         // printed_page = pdf_page + page_offset (default 0)
//   footer, date, course, module,
//   clusters: [{ name, covers, target, figures:[...] }, ...]
// }})

export const meta = {
  name: 'gebhardt-augment',
  description: 'Author + fact-verify augmenting slides grounded in an external academic source (book chapter)',
  phases: [
    { title: 'Author', detail: 'one author per source topic cluster, in parallel' },
    { title: 'Verify', detail: 'grounding-critic checks every fact against the source text' },
  ],
}

let r = args || {}
if (typeof r === 'string') { try { r = JSON.parse(r) } catch (e) { throw new Error('args not JSON: ' + e.message) } }
const CLUSTERS = r.clusters
if (!Array.isArray(CLUSTERS) || !CLUSTERS.length) throw new Error('args.clusters is empty')

const DECK = (r.deck || `${r.deck_location || ''}/${r.deck_name || ''}`).replace(/\\/g, '/').replace(/\/+$/, '')
if (!DECK || DECK === '/') throw new Error('gebhardt-augment: pass args.deck OR args.deck_location + args.deck_name')
const RES = `${DECK}/resources`
const SRC = r.source_dir || 'gebhardt'
const GEB = `${RES}/${SRC}`
const FIGS = `${GEB}/figures`
const GUIDE = `${RES}/author-guide.md`
const SOURCE_KEY = r.source_key || 'gebhardt2025'
const PAGE_OFFSET = Number.isFinite(r.page_offset) ? r.page_offset : 0
const FOOTER = r.footer || `${r.course || ''}, ${r.module || ''}`.replace(/^, |, $/g, '')
const DATE = r.date || ''

const SLIDE_SCHEMA = {
  type: 'object',
  properties: {
    cluster: { type: 'string' },
    slides_md: { type: 'string' },
    slide_count: { type: 'number' },
    facts: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, book_page: { type: 'number' } }, required: ['claim', 'book_page'] } },
    figure_proposals: { type: 'array', items: { type: 'object', properties: {
      slug: { type: 'string' }, kind: { type: 'string' },
      teaching_caption: { type: 'string' }, imagegen_description: { type: 'string' },
      based_on_book_page: { type: 'number' } }, required: ['slug', 'kind', 'imagegen_description'] } },
    bib_entries: { type: 'string' },
    evidence: { type: 'array', items: { type: 'object', properties: {
      slide_title: { type: 'string' },
      claims: { type: 'array', items: { type: 'object', properties: {
        statement: { type: 'string' }, locator: { type: 'string' }, excerpt: { type: 'string' } },
        required: ['statement', 'locator'] } },
      figures: { type: 'array', items: { type: 'object', properties: {
        file: { type: 'string' }, intended_relationships: { type: 'string' },
        must_not: { type: 'array', items: { type: 'string' } } }, required: ['file'] } },
    }, required: ['slide_title', 'claims'] } },
    flags: { type: 'string' },
  },
  required: ['cluster', 'slides_md', 'slide_count', 'facts'],
}
const CRITIC_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string' },
  findings: { type: 'array', items: { type: 'object', properties: {
    claim: { type: 'string' }, issue: { type: 'string' }, severity: { type: 'string' },
    fix: { type: 'string' } }, required: ['claim', 'issue', 'severity'] } } }, required: ['verdict', 'findings'] }

const HOUSE = `HOUSE STYLE (non-negotiable): NO centre dot, NO em-dash ANYWHERE (incl. alt text + notes); use colon/comma; en-dash only for numeric ranges. HTML attribute values (alt="...") contain no double quotes. Every content slide body opens with ONE ~10-word intro sentence, blank line, THEN <=5 telegraphic bullets. Title = 1-5 word concept name. Footer exactly "${FOOTER}"; date exactly "${DATE}". Presenter notes on every slide: 3-5 say-bullets, then "- Example to tell: ..." and "- Memory hook: ...".`

const CITE = `CITATIONS: the source is an academic book chapter (bib key "${SOURCE_KEY}"), which MAY be in another
language. Ground EVERY fact ONLY in your cluster text; translate faithfully to English; invent nothing. On each
content slide put "Source: [@${SOURCE_KEY}, p. NN]" where NN = the printed BOOK page = ${PAGE_OFFSET} + (the
"===== PAGE k =====" number the fact came from). Return facts[] listing each claim with its book_page so a critic
can verify it. bib_entries = the single ${SOURCE_KEY} BibTeX @incollection/@book entry (title, eds./publisher as
printed; leave unverifiable fields out).`

// ---------- Phase 1: author each cluster ----------
phase('Author')
log(`Authoring ${CLUSTERS.length} source clusters in parallel, grounded in the extracted source text.`)

const authorPrompt = (c) => `You author AUGMENTING slides for an IU "ILSE" Slidev lecture deck
(footer "${FOOTER}"). The base deck was reduced to only the thin lecture-note content; your job is to ADD depth
from a richer academic source.

YOUR SOURCE (the ONLY ground truth): ${GEB}/cluster_${c.name}.txt  (may be in another language). Covers: ${c.covers}

STEP 1 read the author guide ${GUIDE} (slot templates slide4/slide5/slidefigure + house style) and your cluster text (read ALL of it).
STEP 2 look at the diagram/photo figures for your pages in ${FIGS}/ : ${c.figures.join(', ') || '(none listed; you may Read any figure in your page range)'}. Open the ones that look like teaching DIAGRAMS with Read.
STEP 3 author ${c.target} English slides that teach ${c.covers}. Prefer clear teaching structure. Use layout slide4 for text-only, slide5 when a figure adds value, slidefigure for a full diagram. Where a book DIAGRAM genuinely teaches, DO NOT embed the book image (copyright); instead add a figure_proposal so it can be re-created: give a faithful imagegen_description of what the diagram shows (boxes, axes, flow, labels) grounded in the book, and reference it on the slide with an <img src="/figures/<slug>.png" ...> placeholder in ::picture-14::. Also propose grounded INFOGRAPHICS (kind:"infographic") where a concept (e.g. a process/curve/hierarchy) is better shown than listed.

${HOUSE}
${CITE}

OUTPUT: cluster="${c.name}"; slides_md = the slide blocks concatenated, each starting with its "---\\nlayout:...\\n---" frontmatter and ending with its "<!-- notes -->", dropping straight into slides.md (use /figures/<slug>.png for any proposed figure); slide_count; facts[{claim, book_page}]; figure_proposals[{slug, kind, teaching_caption, imagegen_description, based_on_book_page}]; bib_entries (the ${SOURCE_KEY} entry); evidence[] = ONE entry per slide you produced, {slide_title, claims:[{statement, locator:"p. NN", excerpt:"the verbatim source sentence the claim came from"}], figures:[{file:"<slug>.png", intended_relationships:"the correct mapping/flow/grouping in words", must_not:["traps a wrong render would fall into"]}]} — this becomes the slide's evidence sidecar; flags.`

let authored = await parallel(CLUSTERS.map((c) => () =>
  agent(authorPrompt(c), { schema: SLIDE_SCHEMA, phase: 'Author', label: `author:${c.name}` })
))

// retry empties once
const failed = authored.map((a, i) => (!a || !a.slides_md || !a.slides_md.trim() ? i : -1)).filter((i) => i >= 0)
if (failed.length) {
  log(`retrying ${failed.length} failed author(s)`)
  for (const i of failed) {
    const again = await agent(authorPrompt(CLUSTERS[i]), { schema: SLIDE_SCHEMA, phase: 'Author', label: `author-retry:${CLUSTERS[i].name}` })
    if (again && again.slides_md && again.slides_md.trim()) authored[i] = again
  }
}

// ---------- Phase 2: grounding-critic per cluster (verify every fact) ----------
phase('Verify')
log('Grounding-critic: verifying every authored fact against the source text.')

const verified = await parallel(authored.map((a, i) => () => {
  if (!a || !a.facts) return Promise.resolve(null)
  const c = CLUSTERS[i]
  const factList = a.facts.map((f, k) => `${k + 1}. (book p.${f.book_page}) ${f.claim}`).join('\n')
  return agent(`You are a strict GROUNDING critic. The source of truth is the text at
${GEB}/cluster_${c.name}.txt (page markers "===== PAGE k =====" where printed book page = ${PAGE_OFFSET} + k; the
source may be in another language). Read it. Below are facts an author put on English slides, each with the book
page it claims. For EACH fact, check it is genuinely stated in the source near that page (allow faithful
translation/paraphrase). Flag any fact that is NOT supported, is on the wrong page, exaggerates, or adds
numbers/claims the text does not contain. Be specific.
FACTS:\n${factList}
OUTPUT: verdict ("clean" | "needs-fixes") and findings[{claim, issue, severity, fix}].`,
    { schema: CRITIC_SCHEMA, phase: 'Verify', label: `verify:${c.name}` })
}))

return {
  authored: authored.map((a, i) => a || { cluster: (CLUSTERS[i] || {}).name, error: 'null' }),
  verified,
}
