# -*- coding: utf-8 -*-
"""Generate docs/Slidecraft-Handbook.pdf — onboarding handbook for a new colleague."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, KeepTogether, Preformatted)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon, Group

TEAL = colors.HexColor("#14555C")
TEAL_DARK = colors.HexColor("#0E3F45")
BLUE = colors.HexColor("#D9E2E7")
BLUE_DARK = colors.HexColor("#8FA6B0")
CORAL = colors.HexColor("#FF4757")
INK = colors.HexColor("#1D1D1F")
GREY = colors.HexColor("#575E62")
LIGHT = colors.HexColor("#F2F4F5")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Slidecraft-Handbook.pdf")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold",
                            fontSize=30, leading=34, textColor=TEAL, spaceAfter=16,
                            alignment=TA_LEFT),
    "subtitle": ParagraphStyle("st", parent=ss["Normal"], fontSize=13,
                               textColor=GREY, spaceAfter=18),
    "part": ParagraphStyle("p1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                           fontSize=19, textColor=colors.white, backColor=TEAL,
                           borderPadding=(6, 8, 6, 8), spaceBefore=14, spaceAfter=12),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                         fontSize=13.5, textColor=TEAL, spaceBefore=14, spaceAfter=5),
    "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                         fontSize=11, textColor=INK, spaceBefore=10, spaceAfter=3),
    "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=9.6, leading=13.6,
                           textColor=INK, spaceAfter=5),
    "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.4, leading=11.4,
                            textColor=GREY),
    "cell": ParagraphStyle("c", parent=ss["Normal"], fontSize=8.8, leading=11.8,
                           textColor=INK),
    "cellb": ParagraphStyle("cb", parent=ss["Normal"], fontSize=8.8, leading=11.8,
                            textColor=INK, fontName="Helvetica-Bold"),
    "code": ParagraphStyle("cd", parent=ss["Code"], fontName="Courier", fontSize=8.2,
                           leading=10.6, textColor=INK, backColor=LIGHT,
                           borderPadding=(4, 6, 4, 6), spaceBefore=3, spaceAfter=7),
    "prompt": ParagraphStyle("pr", parent=ss["Code"], fontName="Courier", fontSize=7.4,
                             leading=9.6, textColor=INK, backColor=LIGHT,
                             borderPadding=(4, 6, 4, 6), spaceBefore=2, spaceAfter=8),
}

W = 170 * mm  # content width


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 12 * mm, "Slidecraft Handbook  |  2026-07-15")
    canvas.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(BLUE)
    canvas.setLineWidth(0.6)
    canvas.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)
    canvas.restoreState()


def tbl(data, widths, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, BLUE_DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), TEAL),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                  ("FONTSIZE", (0, 0), (-1, 0), 9)]
    t.setStyle(TableStyle(style))
    return t


# ---------------------------------------------------------------- diagrams

def box(g, x, y, w, h, label, fill=BLUE, text=INK, size=7.6, bold=False,
        stroke=None, dash=False):
    r = Rect(x, y, w, h, rx=3, ry=3)
    r.fillColor = fill
    r.strokeColor = stroke or BLUE_DARK
    r.strokeWidth = 0.8
    if dash:
        r.strokeDashArray = [3, 2]
    g.add(r)
    lines = label.split("\n")
    lh = size + 2.2
    y0 = y + h / 2 + (len(lines) - 1) * lh / 2 - size * 0.36
    for i, ln in enumerate(lines):
        s = String(x + w / 2, y0 - i * lh, ln)
        s.fontName = "Helvetica-Bold" if bold else "Helvetica"
        s.fontSize = size
        s.fillColor = text
        s.textAnchor = "middle"
        g.add(s)


def arrow(g, x1, y1, x2, y2, color=BLUE_DARK, width=1.0):
    g.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=width))
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    a = 4.6
    p = Polygon([x2, y2,
                 x2 - a * math.cos(ang - 0.45), y2 - a * math.sin(ang - 0.45),
                 x2 - a * math.cos(ang + 0.45), y2 - a * math.sin(ang + 0.45)])
    p.fillColor = color
    p.strokeColor = color
    g.add(p)


def label(g, x, y, text, size=6.8, color=GREY, anchor="start", bold=False):
    s = String(x, y, text)
    s.fontName = "Helvetica-Bold" if bold else "Helvetica"
    s.fontSize = size
    s.fillColor = color
    s.textAnchor = anchor
    g.add(s)


def build_pipeline_diagram():
    Wd, Hd = 481, 560
    d = Drawing(Wd, Hd)
    g = Group()
    d.add(g)

    # Row 1 — inputs (top)
    y = Hd - 46
    box(g, 0, y, 130, 40, "resources/\nchapter PDF, template PPTX,\nquestion catalogue", fill=colors.white, size=7.0)
    box(g, 168, y, 140, 40, "extract_chapter.py\nsections, figures,\nSource lines, study goals", fill=colors.white, stroke=TEAL, size=7.0, bold=True)
    box(g, 350, y, 131, 40, "recipe.json\nall per-deck variables\n(sections, toggles, footer)", fill=colors.white, size=7.0)
    arrow(g, 130, y + 20, 168, y + 20)
    arrow(g, 308, y + 20, 350, y + 20)
    label(g, 0, Hd - 2, "DETERMINISTIC PREPARATION (scripts)", bold=True, color=TEAL)

    # Workflow container
    cy0, cy1 = Hd - 330, Hd - 66
    cont = Rect(0, cy0, Wd, cy1 - cy0, rx=5, ry=5)
    cont.fillColor = colors.HexColor("#EDF3F4")
    cont.strokeColor = TEAL
    cont.strokeWidth = 1.4
    g.add(cont)
    arrow(g, 415, y - 6, 415, cy1, color=TEAL, width=1.4)
    label(g, 6, cy1 - 14, "WORKFLOW  sprint_deck.js  (agents, live progress tree in /workflows)", bold=True, color=TEAL, size=7.6)

    # Phase 1 Author
    py = cy1 - 78
    box(g, 10, py, 90, 44, "PHASE 1\nAUTHOR", fill=TEAL, text=colors.white, bold=True, size=8.2)
    box(g, 118, py, 210, 44, "section-author  x N  (parallel)\nreads guide + section text + figure images,\nwrites slides_md + [@key] cites + bib entries", size=6.9)
    box(g, 348, py, 123, 44, "retry x1 per failed\nsection (rate limits),\nelse inline fallback", fill=colors.white, dash=True, size=6.8)
    arrow(g, 100, py + 22, 118, py + 22)
    arrow(g, 328, py + 22, 348, py + 22)

    # Phase 2 Enrich
    ey = py - 66
    box(g, 10, ey, 90, 50, "PHASE 2\nENRICH\n(parallel)", fill=TEAL, text=colors.white, bold=True, size=8.2)
    box(g, 118, ey + 27, 110, 23, "mindmap-smith\noutline from all sections", size=6.6)
    box(g, 240, ey + 27, 110, 23, "gallery-curator\nWikimedia photo queries", size=6.6)
    box(g, 118, ey, 110, 23, "source-researcher\nreferences.bib (BibTeX)", size=6.6)
    box(g, 240, ey, 110, 23, "exam-focus-analyst\nsubtle revision bullets", size=6.6)
    arrow(g, 100, ey + 25, 118, ey + 25)
    arrow(g, 55, py, 55, ey + 50, color=TEAL)

    # Phase 3 Critic
    ky = ey - 60
    box(g, 10, ky, 90, 40, "PHASE 3\nCRITIC", fill=TEAL, text=colors.white, bold=True, size=8.2)
    box(g, 118, ky, 232, 40, "grounding-critic\nevery authored bullet + caption checked against\nthe section texts; verdict clean / needs-fixes", size=6.9)
    box(g, 370, ky, 101, 40, "GATE: findings\nmust be applied\nbefore done", fill=colors.white, stroke=CORAL, size=6.8, bold=True)
    arrow(g, 100, ky + 20, 118, ky + 20)
    arrow(g, 350, ky + 20, 370, ky + 20, color=CORAL)
    arrow(g, 55, ey, 55, ky + 40, color=TEAL)

    # Row 3 — deterministic assembly
    ay = cy0 - 72
    label(g, 0, cy0 - 12, "DETERMINISTIC ASSEMBLY + RENDER (scripts)", bold=True, color=TEAL)
    box(g, 0, ay, 112, 44, "slides/<slug>.md\nper-slide files +\nslides.md manifest", fill=colors.white, size=6.9)
    box(g, 124, ay, 112, 44, "gen_mindmap.py\noutline -> Imagen 3\n(verify labels!)", fill=colors.white, stroke=TEAL, size=6.9)
    box(g, 248, ay, 112, 44, "gallery_search.py\nWikimedia, licence-\nfiltered + attributed", fill=colors.white, stroke=TEAL, size=6.9)
    box(g, 372, ay, 109, 44, "render_references.py\n[@key] -> citations +\nreferences pages", fill=colors.white, stroke=TEAL, size=6.9)
    arrow(g, 240, cy0, 240, ay + 44, color=TEAL, width=1.4)

    # Row 4 — verify
    vy = ay - 66
    label(g, 0, ay - 12, "VERIFY (all must pass)", bold=True, color=CORAL)
    box(g, 0, vy, 112, 40, "lint_slides.py\nL1..L15 = 0 errors", fill=colors.white, stroke=CORAL, size=7.0)
    box(g, 124, vy, 112, 40, "render_references\n--check: keys + credits", fill=colors.white, stroke=CORAL, size=7.0)
    box(g, 248, vy, 112, 40, "npm run build\noutput ends 'built'", fill=colors.white, stroke=CORAL, size=7.0)
    box(g, 372, vy, 109, 40, "image check\nall /figures/ exist", fill=colors.white, stroke=CORAL, size=7.0)
    arrow(g, 240, ay, 240, vy + 40, color=CORAL, width=1.2)

    # Row 5 — outputs
    oy = vy - 62
    box(g, 60, oy, 170, 38, "DONE_REPORT.md\nper-phase status, per-figure sources,\nopen items + the tweak phrase for each", fill=BLUE, size=6.9)
    box(g, 280, oy, 150, 38, "Start_Presentation.bat\nlocalhost:3030  /presenter/  /overview/", fill=BLUE, size=6.9)
    arrow(g, 180, vy, 145, oy + 38, color=BLUE_DARK)
    arrow(g, 300, vy, 355, oy + 38, color=BLUE_DARK)
    return d


def improve_diagram():
    Wd, Hd = 481, 170
    d = Drawing(Wd, Hd)
    g = Group()
    d.add(g)
    box(g, 0, 108, 120, 46, "You:\ntweak phrase or\n/slidecraft:improve-deck", fill=BLUE, size=7.2)
    cont = Rect(140, 62, 210, 100, rx=5, ry=5)
    cont.fillColor = colors.HexColor("#EDF3F4")
    cont.strokeColor = TEAL
    cont.strokeWidth = 1.2
    g.add(cont)
    label(g, 146, 150, "WORKFLOW improve_deck.js (parallel passes)", bold=True, color=TEAL, size=6.8)
    box(g, 148, 118, 94, 22, "grounding-critic", size=6.8)
    box(g, 250, 118, 94, 22, "house-style", size=6.8)
    box(g, 148, 90, 94, 22, "slide-critic", size=6.8)
    box(g, 250, 90, 94, 22, "visual-enrichment", size=6.8)
    box(g, 148, 66, 196, 18, "findings merged, sorted high > med > low", fill=colors.white, size=6.6)
    arrow(g, 120, 131, 140, 131)
    box(g, 370, 108, 111, 46, "APPLY\nhigh/med: edit the one\nslides/<slug>.md file\nlow: ask first", fill=colors.white, stroke=CORAL, size=6.8)
    arrow(g, 350, 112, 370, 124, color=CORAL)
    box(g, 140, 6, 210, 34, "re-verify: lint_slides = 0 errors,\nnpm run build stays 'built'", fill=colors.white, stroke=CORAL, size=7.0)
    arrow(g, 420, 108, 260, 40, color=CORAL)
    box(g, 0, 6, 120, 34, "hot reload: browser\nrefreshes on save", fill=BLUE, size=7.0)
    arrow(g, 140, 22, 122, 22)
    return d


def citation_diagram():
    Wd, Hd = 481, 128
    d = Drawing(Wd, Hd)
    g = Group()
    d.add(g)
    box(g, 0, 76, 132, 44, "slides/*.md\ncarry only markers:\nSource: [@schmid2013]", fill=colors.white, size=7.0)
    box(g, 0, 10, 132, 44, "references.bib\none entry per source,\nimages: keywords={image}", fill=colors.white, size=7.0)
    box(g, 170, 40, 140, 52, "render_references.py\nciteproc-py + CSL style\n(apa-7th, harvard, drop-in)", fill=TEAL, text=colors.white, bold=True, size=7.2)
    arrow(g, 132, 92, 170, 80)
    arrow(g, 132, 36, 170, 52)
    box(g, 348, 88, 133, 32, "inline short forms\nMartin (2022), idempotent", fill=BLUE, size=6.8)
    box(g, 348, 50, 133, 32, "references*.md +\nimage-sources*.md, paginated", fill=BLUE, size=6.8)
    box(g, 348, 12, 133, 32, "warnings: unknown keys,\nuncredited images, orphans", fill=colors.white, stroke=CORAL, size=6.8)
    arrow(g, 310, 78, 348, 100)
    arrow(g, 310, 66, 348, 66)
    arrow(g, 310, 54, 348, 30, color=CORAL)
    return d


# ---------------------------------------------------------------- content

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=18 * mm, bottomMargin=20 * mm,
                        title="Slidecraft Handbook", author="Slidecraft")
E = []

E.append(Paragraph("Slidecraft Handbook", S["title"]))
E.append(Paragraph("Building grounded lecture decks with agents, from course material to presentation. "
                   "Onboarding guide, version 2026-07-15.", S["subtitle"]))

E.append(Paragraph("Part 1 — Using Slidecraft", S["part"]))

E.append(Paragraph("1.1 What Slidecraft is", S["h2"]))
E.append(Paragraph(
    "Slidecraft is a Claude Code plugin that turns raw course material (a chapter PDF, a PowerPoint "
    "template, an exam-question catalogue) into a polished, presentable <b>Slidev</b> deck: HTML slides "
    "rendered in the browser, with presenter notes, driven by plain markdown files. The heavy lifting is "
    "done by a pipeline of AI agents orchestrated in a workflow, wrapped in deterministic scripts that "
    "extract, verify, lint, and build. The governing invariant: <b>nothing appears on a slide that is not "
    "supported by the source material</b> — a dedicated grounding critic checks every build.", S["body"]))

E.append(Paragraph("1.2 The four concepts", S["h2"]))
E.append(tbl([
    [Paragraph("Concept", S["cellb"]), Paragraph("What it is", S["cell"]),
     Paragraph("Where it lives", S["cell"])],
    [Paragraph("Theme", S["cellb"]),
     Paragraph("The visual identity: an npm package (<font face='Courier'>slidev-theme-*</font>) of "
               "layout files (slide1..slide9) with fixed named slots (::body-16::, ::picture-14:: ...), "
               "brand fonts and colors. The IU corporate look is <b>slidev-theme-ilse</b>. Decks may add "
               "local layouts/*.vue (agenda, slidefigure, gallery) that extend or override the theme.", S["cell"]),
     Paragraph("Präsentationen/slidecraft-themes/&lt;name&gt;/ — consumed by each deck via a "
               "<font face='Courier'>file:</font> npm dependency", S["cell"])],
    [Paragraph("Deck", S["cellb"]),
     Paragraph("One presentation: a self-contained npm project. Content is <b>one markdown file per "
               "slide</b> under slides/, ordered by a thin slides.md import manifest. Editing one slide "
               "touches one small file; removing a slide removes one manifest line (the file stays).", S["cell"]),
     Paragraph("Präsentationen/slidecraft-decks/&lt;DECK&gt;/", S["cell"])],
    [Paragraph("Deck type", S["cellb"]),
     Paragraph("The template concept: which pipeline runs, which skeleton slides frame the deck, which "
               "house style the authors follow. Today one type is implemented (the IU 'sprint' lecture "
               "deck: recipe + workflow + author guide). The target design packages types as declarative "
               "folders in type-collection repos (see docs: workflow-design.md, decisions 4, 11).", S["cell"]),
     Paragraph("today: baked into the plugin (workflows/ + references/ilse-author-guide.md)", S["cell"])],
    [Paragraph("Recipe", S["cellb"]),
     Paragraph("Everything variable for one deck: course/module, chapter number and title, the section "
               "list (derived from the PDF), slide targets per section, enrichment toggles (mind map, "
               "galleries, exam focus), footer and date. Hand-editable and re-runnable.", S["cell"]),
     Paragraph("&lt;deck&gt;/resources/recipe.json (template: slidecraft/recipe.example.json)", S["cell"])],
], [23 * mm, 92 * mm, 55 * mm]))

E.append(Paragraph("1.3 Where everything is stored", S["h2"]))
E.append(Preformatted(
"""Tools/Slidecraft/                          the PLUGIN (git repo)
  slidecraft/commands/     sprint-deck.md, improve-deck.md, new-deck.md, ...
  slidecraft/workflows/    sprint_deck.js (build), improve_deck.js (polish)
  slidecraft/scripts/      extract_chapter, gen_mindmap, gallery_search,
                           render_references, import_ris, lint_slides, split_deck
  slidecraft/references/   ilse-author-guide.md, bibtex-guide.md, csl/ styles,
                           workflow-design.md (the 15 design decisions)

Praesentationen/slidecraft-themes/<name>/  THEMES (one folder per theme)
Praesentationen/slidecraft-decks/<DECK>/   DECKS, each self-contained:
  slides/<slug>.md        one file per slide          slides.md   import manifest
  public/figures/         served images               resources/  sources + recipe
  references.bib          citation database           layouts/    deck-local layouts
  Start_Presentation.bat  one-click presenting        .slidecraft/history/  backups

Per machine (never in a repo): ~/.claude/skills/owui/ + .env  (image generation,
IU OpenWebUI URL + token)   and   ~/.slidecraft/csl/  (extra citation styles)""",
    S["code"]))

E.append(Paragraph("1.4 Building a deck, start to finish", S["h2"]))
E.append(tbl([
    [Paragraph("Step", S["cellb"]), Paragraph("Who", S["cellb"]), Paragraph("What happens", S["cell"])],
    [Paragraph("1. Prepare sources", S["cellb"]), Paragraph("you", S["cell"]),
     Paragraph("Create the deck folder (copy an existing deck's scaffold, run npm install) and drop the "
               "chapter PDF, the session TEMPLATE .pptx, and the question catalogue into resources/. "
               "If no standalone chapter PDF exists, split it from the full course book by page range.", S["cell"])],
    [Paragraph("2. Extract", S["cellb"]), Paragraph("script", S["cell"]),
     Paragraph("<font face='Courier' size='8'>python -m slidecraft.scripts.extract_chapter --deck &lt;deck&gt; "
               "--pdf &lt;chapter.pdf&gt; --prefix chN</font><br/>TOC becomes the section list; figures are "
               "extracted with their printed Source lines; study goals are captured.", S["cell"])],
    [Paragraph("3. Confirm recipe", S["cellb"]), Paragraph("you", S["cell"]),
     Paragraph("Copy recipe.example.json, paste in the extracted sections, set slide targets and "
               "enrichment toggles. This is the only mandatory checkpoint (about 10 lines of judgment).", S["cell"])],
    [Paragraph("4. Autonomous build", S["cellb"]), Paragraph("agents", S["cell"]),
     Paragraph("Say <b>/slidecraft:sprint-deck</b> (or ask Claude to run the sprint pipeline). The "
               "workflow authors all sections in parallel, enriches (mind map, galleries, citations, exam "
               "focus), and runs the grounding critic — watch live in /workflows. Scripts then assemble "
               "per-slide files, render images and citations, lint, and build. Around 15-30 min unattended.", S["cell"])],
    [Paragraph("5. Review", S["cellb"]), Paragraph("you", S["cell"]),
     Paragraph("Read DONE_REPORT.md (per-phase status, every figure's source, open items with a ready-made "
               "tweak phrase each). Flip through localhost:3030/overview/.", S["cell"])],
    [Paragraph("6. Improve", S["cellb"]), Paragraph("you + agents", S["cell"]),
     Paragraph("Fire tweak phrases in chat: 'tighten the riveting slide', 'replace the forming overview "
               "image with Figure 30', 'remove the galleries', 'regenerate the mind map', 'fix the sources "
               "on slide 9'. Each is a clean single-file edit; the browser hot-reloads.", S["cell"])],
    [Paragraph("7. Present", S["cellb"]), Paragraph("you", S["cell"]),
     Paragraph("Double-click Start_Presentation.bat: audience screen on localhost:3030/, presenter notes "
               "on /presenter/ (second screen).", S["cell"])],
], [26 * mm, 18 * mm, 126 * mm]))

E.append(Paragraph("1.5 One-time machine setup", S["h2"]))
E.append(Paragraph(
    "1. Claude Code with the Slidecraft plugin (clone Tools/Slidecraft). &nbsp;2. Node.js + npm. "
    "&nbsp;3. <font face='Courier'>pip install -r slidecraft/requirements.txt</font> (pymupdf, "
    "citeproc-py, pillow, rispy). &nbsp;4. The theme folder available at the expected sibling path. "
    "&nbsp;5. Optional image generation: the machine-local owui skill with your OpenWebUI URL + token "
    "in its .env — without it, mind-map/diagram steps skip gracefully and the DONE report says so.",
    S["body"]))

E.append(PageBreak())
E.append(Paragraph("Part 2 — Under the hood", S["part"]))

E.append(Paragraph("2.1 The build pipeline (sprint_deck)", S["h2"]))
E.append(Paragraph(
    "Teal boxes are workflow phases run by agents; white boxes with teal borders are deterministic "
    "Python scripts; coral-bordered boxes are hard gates. Agents propose; scripts verify and persist.",
    S["small"]))
E.append(Spacer(1, 4))
E.append(build_pipeline_diagram())

E.append(PageBreak())
E.append(Paragraph("2.2 The polish loop (improve_deck) and tweaks", S["h2"]))
E.append(improve_diagram())
E.append(Spacer(1, 6))
E.append(Paragraph(
    "Single-slide tweak phrases skip the workflow and fire one agent or script directly with the same "
    "rules. Editing conventions (proven in practice): assets are never overwritten (new versions get "
    "_v2 filenames), 'remove slide X' only removes the manifest line (the file stays restorable), "
    "subtractive image edits prefer pixel surgery over regeneration, and every reused or AI-derived "
    "figure is explained on the slide itself. Full catalog: commands/improve-deck.md.", S["body"]))

E.append(Paragraph("2.3 The agents", S["h2"]))
E.append(tbl([
    [Paragraph("Agent (role)", S["cellb"]), Paragraph("Workflow / phase", S["cell"]),
     Paragraph("Purpose and grounding", S["cell"]), Paragraph("Returns", S["cell"])],
    [Paragraph("section-author (xN)", S["cellb"]), Paragraph("sprint / Author", S["cell"]),
     Paragraph("Writes the slides for ONE chapter section. Reads the author guide (house style, image "
               "ladder), its section text (sole source of truth) and the figure images (matches captions "
               "by content). Cites via [@key] markers only.", S["cell"]),
     Paragraph("slides_md, slide_count, figures_used, bib_entries, flags", S["cell"])],
    [Paragraph("mindmap-smith", S["cellb"]), Paragraph("sprint / Enrich", S["cell"]),
     Paragraph("Distils all section texts into a complete nested outline (one branch per section); the "
               "image itself is rendered later by gen_mindmap.py and verified label-by-label.", S["cell"]),
     Paragraph("central, outline_md", S["cell"])],
    [Paragraph("gallery-curator", S["cellb"]), Paragraph("sprint / Enrich", S["cell"]),
     Paragraph("Proposes real-world example photos per section as Wikimedia search queries (photos only; "
               "the licence filter and download are gallery_search.py's job).", S["cell"]),
     Paragraph("groups[{section, queries}]", S["cell"])],
    [Paragraph("source-researcher", S["cellb"]), Paragraph("sprint / Enrich", S["cell"]),
     Paragraph("Compiles the citation DATABASE as BibTeX (never formatted text), verified against the "
               "printed Source lines and the book's own reference list. Style is applied later by "
               "render_references.py.", S["cell"]),
     Paragraph("bibtex, keys, notes", S["cell"])],
    [Paragraph("exam-focus-analyst", S["cellb"]), Paragraph("sprint / Enrich", S["cell"]),
     Paragraph("Writes the subtle, concept-level 'Where to focus your revision' content. Never reveals "
               "questions or scores (those stay in presenter notes at most).", S["cell"]),
     Paragraph("focus_bullets, presenter_notes", S["cell"])],
    [Paragraph("grounding-critic", S["cellb"]), Paragraph("sprint / Critic + improve pass", S["cell"]),
     Paragraph("The backstop: checks every authored bullet, number, and figure attribution against the "
               "section texts. Its findings are a gate — applied before the deck is 'done'.", S["cell"]),
     Paragraph("verdict, findings[]", S["cell"])],
    [Paragraph("house-style / slide-critic / visual-enrichment", S["cellb"]),
     Paragraph("improve / Review", S["cell"]),
     Paragraph("Polish passes over a finished deck: style violations with exact fixes; title/evidence "
               "quality and monotony; text-heavy slides that deserve a visual (suggestions only).", S["cell"]),
     Paragraph("findings[{slide, issue, severity, fix}]", S["cell"])],
    [Paragraph("image-critic", S["cellb"]), Paragraph("improve / Review", S["cell"]),
     Paragraph("Devil's-advocate reviewer for non-photographic figures: reads what is ACTUALLY rendered "
               "and checks text, colour/accent, shape/layout, logical structure, figure-slide coherence, "
               "and visual hygiene against the slide + its evidence sidecar. Runs on a SINGLE vision model "
               "(GPT-5.6 sol via OWUI) through scripts/image_critic.py. Report-only.", S["cell"]),
     Paragraph("findings + verdict per figure", S["cell"])],
], [34 * mm, 22 * mm, 79 * mm, 35 * mm]))

E.append(Paragraph("2.4 The deterministic scripts", S["h2"]))
E.append(tbl([
    [Paragraph("Script", S["cellb"]), Paragraph("Job", S["cell"])],
    [Paragraph("extract_chapter.py", S["cellb"]),
     Paragraph("Chapter PDF to sections (UTF-8 text by TOC), deduplicated figures, printed Source lines, study goals; writes chN_extract.json.", S["cell"])],
    [Paragraph("gen_mindmap.py", S["cellb"]),
     Paragraph("Nested outline to GPT-5.5 image prompt to Imagen 3 render (via the machine-local owui skill). Output is verified against the outline before use.", S["cell"])],
    [Paragraph("gallery_search.py", S["cellb"]),
     Paragraph("Wikimedia Commons search with commercial-licence filter (PD/CC0/CC BY/CC BY-SA, never NC), polite pacing + 429 backoff, download + downscale + attribution JSON.", S["cell"])],
    [Paragraph("render_references.py", S["cellb"]),
     Paragraph("The citation renderer: [@key] markers to styled inline citations (idempotent), paginated references*/image-sources* pages, manifest sync, and credit cross-checks. Style via CSL (--style).", S["cell"])],
    [Paragraph("import_ris.py", S["cellb"]),
     Paragraph("Publisher RIS export appended to references.bib with correct type/field mapping — academic metadata is imported, never transcribed.", S["cell"])],
    [Paragraph("lint_slides.py", S["cellb"]),
     Paragraph("Pre-flight gate, L1-L15: layout/slot names (incl. deck-local layouts), relative-image-path errors, YAML, formula-in-title, cite keys exist in bib, notes present, word counts, monotony, house-style characters (L13), broken attribute quoting (L14), portrait image on full-width layout (L15).", S["cell"])],
    [Paragraph("split_deck.py", S["cellb"]),
     Paragraph("Migration tool: monolithic slides.md to per-slide files + manifest, byte-verified round trip, backup kept.", S["cell"])],
    [Paragraph("format_citations.py", S["cellb"]),
     Paragraph("The citeproc-py/CSL core used by render_references (inline + bibliography rendering; styles bundled: apa-7th, harvard; drop new .csl into ~/.slidecraft/csl/).", S["cell"])],
    [Paragraph("gen_figure.py", S["cellb"]),
     Paragraph("Reusable figure generator: --source vision-recreates a book diagram (GPT-5.5 vision to Imagen), --spec renders a label-controlled synthesized figure. Reads the skeleton's diagram-style.md STYLE block + consistency contract and pastes them into every prompt, so generation follows the same rules the image-critic enforces.", S["cell"])],
    [Paragraph("write_evidence.py", S["cellb"]),
     Paragraph("Persists/merges the per-slide evidence sidecars (resources/evidence/<slug>.json) from the authoring workflows' evidence[] output: each claim's source key+locator+verbatim excerpt, each figure's intended labels/relationships/must_not. Merges, so enrichment passes append over time.", S["cell"])],
    [Paragraph("image_critic.py", S["cellb"]),
     Paragraph("Runs the image-critic checklist over a deck's non-photographic figures on GPT-5.6 sol via OWUI, injecting each slide's evidence sidecar so text/relationship claims are checked against a written spec. Writes image_critic_report.md + findings.json. A multi-model panel was rejected as too costly.", S["cell"])],
], [38 * mm, 132 * mm]))

E.append(Paragraph("2.5 The citation system", S["h2"]))
E.append(citation_diagram())
E.append(Spacer(1, 4))
E.append(Paragraph(
    "Slides never contain hand-written citations. Agents (and you) write LaTeX-style markers; the "
    "renderer owns the text between its invisible comment anchors, so re-running with another CSL style "
    "restyles the whole deck. Image credits are bib entries tagged keywords={image} with a mandatory "
    "licence; the renderer routes them to the Image-sources pages and warns about uncredited images and "
    "orphaned credits. Rules for filling the bib correctly (entry types, required fields, n.a. for "
    "authorless web pages, RIS import for academic sources): references/bibtex-guide.md.", S["body"]))

E.append(Paragraph("2.6 Grounding: evidence sidecars &amp; the figure-review loop", S["h2"]))
E.append(Paragraph(
    "Beyond citing sources, each slide carries an <b>evidence sidecar</b> "
    "(<font face='Courier'>resources/evidence/&lt;slug&gt;.json</font>): a machine-readable record of what "
    "the slide was built from — every claim's source key, locator and <i>verbatim excerpt</i>, and every "
    "figure's intended labels, relationships and <font face='Courier'>must_not</font> traps. The authoring "
    "workflows emit it and write_evidence.py persists it; it means a reviewer checks a slide (or a diagram) "
    "against a written spec instead of re-deriving the truth. AI-generated figures are the weak point of any "
    "such pipeline, so a dedicated <b>image-critic</b> (a devil's advocate, run on a single vision model, "
    "GPT-5.6 sol via OWUI) reads what is <i>actually rendered</i> in every non-photographic figure and checks "
    "it against the slide and its sidecar — catching garbled labels, wrong arrows/groupings, off-palette "
    "accents, and untidy composition. Both the generator and the critic obey one <b>consistency contract</b> "
    "in the skeleton's diagram-style.md (one shape per role, one arrow style, one justified accent, no "
    "decorative marks, fill the canvas, scope fidelity), so what a figure is told to be is exactly what it is "
    "reviewed against. See CONTEXT.md (glossary), references/evidence-sidecars.md, and agents/image-critic.md.",
    S["body"]))

E.append(PageBreak())
E.append(Paragraph("Appendix — Agent prompts", S["part"]))
E.append(Paragraph(
    "Verbatim from the workflow sources (placeholders in ${...} are filled from the recipe at run time). "
    "sprint_deck.js prompts first, then the improve_deck.js pass prompts.", S["small"]))

prompts = [
    ("Shared hard rules (GROUND, appended to every author prompt)",
     'HARD RULES: ground every word in the section text; invent nothing (no process, number, or class\n'
     'not in the notes). No centre dot, no em-dash ANYWHERE, including alt texts and notes (colon/comma;\n'
     'en-dash only for numeric ranges). HTML attribute values (alt="...") must contain no double quotes.\n'
     'Footer exactly "${FOOTER}"; date exactly "${DATE}".'),
    ("Shared citation rules (CITE, appended to every author prompt)",
     'CITATIONS: never hand-format a citation. In ::body-13:: write "Source: [@key]" (key = surnameYEAR\n'
     'derived from the printed Source line, e.g. "Source: Schmid, D. (2013)" -> [@schmid2013];\n'
     'standards -> [@din8580]). Also return bib_entries: one BibTeX entry per key you cited, fields\n'
     'copied from the printed Source lines / the notes, per slidecraft/references/bibtex-guide.md\n'
     '(read it). Unsure about a field: leave it out.'),
    ("section-author (one per chapter section, parallel; retried once on failure)",
     'You author the slides for ONE section of an IU "ILSE" Slidev lecture deck\n'
     '(course "${course}", module ${module}, chapter ${chapter_number}: ${chapter_title}).\n\n'
     'YOUR SECTION: "${section.title}"\n\n'
     'STEP 1 read: the author guide slidecraft/references/ilse-author-guide.md (templates + house style\n'
     '+ the image-sourcing ladder, portrait-figure rule, and honest-reuse rule) and your section text\n'
     '${RES}/${section.text_file} (THE source of truth: facts, figure captions, printed Source lines).\n'
     'STEP 2 look at your figures at ${FIGS}/${PREFIX}_fig_NN.jpeg (your files: ${section.figs}).\n'
     'Open each with Read and match it to the caption in your section text BY CONTENT (book Figure\n'
     'numbers drift). A portrait figure (taller than wide) must NOT go on a full-width slidefigure\n'
     'slide: use slide5 or flag it.\n'
     'STEP 3 author ${section.target} slides. Focus: ${section.hint}\n\n'
     '${GROUND}\n${CITE}\n'
     'Presenter notes on every slide: 3-5 say-bullets, then "- Example to tell: ..." and\n'
     '"- Memory hook: ...".\n\n'
     'OUTPUT: section; slides_md (slide blocks that drop straight into slides.md); slide_count;\n'
     'figures_used [{file,caption,source}]; bib_entries (BibTeX for every cited key); flags.'),
    ("mindmap-smith",
     'Read every section text listed below and distil a COMPLETE nested-markdown outline for a radial\n'
     'mind map of chapter ${chapter_number} "${chapter_title}". Central node = a short chapter label.\n'
     'One main branch per section; under each, 3-4 KEY sub-nodes taken from the notes (short labels).\n'
     'Invent nothing.\nSections: <list of section text files>\n'
     'OUTPUT: central (the centre label) and outline_md (the nested markdown).'),
    ("gallery-curator (only when recipe.enrich.galleries == 'search')",
     'For each section below propose up to 6 REAL example processes/parts to illustrate it, each as a\n'
     'Wikimedia Commons search query likely to return a free-licensed photo. Ground the examples in the\n'
     'section notes.\nSections: <list>\nOUTPUT: groups[{section, queries[{label, query}]}].'),
    ("source-researcher",
     "Compile the deck's citation DATABASE as BibTeX (NOT formatted text: rendering is a deterministic\n"
     "script's job; the style is a render-time choice). Read slidecraft/references/bibtex-guide.md\n"
     'first (entry types, required fields, standards need author = {{DIN}}, web pages need urldate +\n'
     'n.a. rule). Then read the printed Source lines in ${RES}/${PREFIX}_extract.json\n'
     "(source_lines_found) and the section texts, and verify bibliographic details against the course\n"
     "book's own reference list where available. One entry per distinct source, keys = surnameYEAR\n"
     '(e.g. schmid2013, martin2022, din8580). NEVER fabricate DOIs/publishers/pages: omit unverifiable\n'
     'fields, or cite the course book as the fallback entry.\n'
     'OUTPUT: bibtex (the complete entries, valid BibTeX); keys (every key defined); notes.'),
    ("exam-focus-analyst (only when recipe.enrich.exam_focus)",
     'Write a SUBTLE, concept-level "Where to Focus Your Revision" slide for chapter ${chapter_number}.\n'
     'Ground it in the section texts (<list>). Never reveal exam questions or quote scores. 5-6 bullets\n'
     'naming the concepts to master (the logic, not lists).\n'
     'OUTPUT: focus_bullets[] and presenter_notes.'),
    ("grounding-critic (build gate)",
     'You are a GROUNDING critic. For each authored section below, check its bullets and figure captions\n'
     'against the section text at ${RES}/section_*.txt. Flag anything not supported by the notes\n'
     '(invented processes, numbers, a wrong figure source, a centre-dot or em-dash, an added\n'
     'class/group). Be specific.\n<all authored sections embedded>\n'
     'OUTPUT: verdict ("clean" | "needs-fixes") and findings[{section, issue, severity, fix}].'),
    ("improve pass: grounding-critic",
     'Read ${SLIDES} and the grounding notes in ${RES}/section_*.txt. For ${SCOPE}, flag any claim,\n'
     'number, or figure source on a slide that is NOT supported by the notes (invented facts, wrong\n'
     'attribution, an added class/group). This is the highest-severity pass.'),
    ("improve pass: house-style",
     'Read ${SLIDES}. For ${SCOPE}, flag house-style violations: any centre dot, any em-dash, a content\n'
     'slide whose body lacks the ~10-word intro + blank line before bullets, field labels used as\n'
     'bullets, or a caption with author initials. Each finding must give the exact fix.'),
    ("improve pass: slide-critic",
     'Read ${SLIDES}. For ${SCOPE}, judge each content slide: is the title a concept name and the body\n'
     'evidence (not filler paraphrasing the title)? Flag topic-label titles, >5 bullets, monotony (too\n'
     'many identical layouts in a row), and any slide carrying two ideas.'),
    ("improve pass: visual-enrichment",
     'Read ${SLIDES}. For ${SCOPE}, name slides that are text-heavy and would teach better as a diagram,\n'
     'a split image slide, or a real-photo gallery. Suggest the specific visual per slide. Suggestions\n'
     'only, no invented content.'),
    ("improve pass: image-critic (devil's advocate, single model)",
     'Read agents/image-critic.md and follow it. PRIMARY runner: python -m slidecraft.scripts.image_critic\n'
     '--deck ${DECK} -- it inspects every NON-photographic figure on GPT-5.6 sol via OWUI and writes\n'
     'resources/image_critic_report.md + image_critic_findings.json. Reconcile each finding against the\n'
     "slide's evidence sidecar (${RES}/evidence/<slug>.json): drop text/label claims the sidecar confirms,\n"
     'raise to high if it hits a must_not. Fall back to direct vision if OWUI is unavailable.'),
]
for title, body in prompts:
    E.append(KeepTogether([Paragraph(title, S["h3"]), Preformatted(body, S["prompt"])]))

doc.build(E, onFirstPage=header_footer, onLaterPages=header_footer)
print("WROTE", OUT)
