---
description: Initialize a new presentation workspace — choose a location, pick a theme, scaffold the directory structure, and prepare for authoring
argument-hint: [workspace-path or "here"]
---

# Start New Presentation

Follow these steps in order. Complete each step before moving to the next.

---

## Step 1 — Choose Workspace Directory

If the user passed an argument (e.g. `/slidecraft:start my-talk`), use that as the workspace name relative to the current directory.

Otherwise ask:
> Where should I create the presentation workspace? You can give me a path, a folder name, or just say "here" to use the current directory.

- If the user says "here", use the current working directory as the workspace root.
- If the user provides a relative or absolute path, use that. Create the directory if it does not exist.
- Remember the resolved absolute path as `WORKSPACE_DIR` for all subsequent steps.

---

## Step 2 — Set Presentation Title

Ask:
> What is the working title for this presentation?

Store the answer as `PRESENTATION_TITLE`.

---

## Step 3 — Select Theme

Search for available themes by scanning for directories named `slidev-theme-*` in these locations (in order):
1. Sibling directories of `WORKSPACE_DIR` (i.e. `parent(WORKSPACE_DIR)/slidev-theme-*`)
2. The parent directory itself (in case the workspace is inside a project root)
3. Any path referenced as `theme.path` in a `.slidecraft.json` found in the same parent directory

For each candidate directory found, verify it contains a `package.json` with a `"slidev"` key — that confirms it is a valid Slidev theme. Read the `"name"` field from `package.json` as the display name.

Then present the results:

**If one or more themes are found**, list them and ask:
> I found these themes:
>   1. `<name>` at `<relative-path>`
>   2. ...
>
> Which one would you like to use? You can also enter a custom path to a theme directory, or press Enter to use Slidev's built-in default theme.

**If no themes are found**, ask:
> I didn't find any custom themes nearby. You can:
>   1. Enter the path to a `slidev-theme-*` directory
>   2. Press Enter to use Slidev's default theme

Store the selected theme as:
- `THEME_NAME`: the short name (e.g. `iu` from `slidev-theme-iu`), or `"default"` if no custom theme
- `THEME_PATH`: the path to the theme directory relative to `WORKSPACE_DIR`, or `null` if using default

---

## Step 4 — Create Workspace Structure

Create the following directories inside `WORKSPACE_DIR`:

```
assets/
.slidecraft/
.slidecraft/history/
```

Write `.slidecraft.json` at `WORKSPACE_DIR/.slidecraft.json` with this exact structure (substitute values from previous steps):

```json
{
  "version": "1.0",
  "title": "<PRESENTATION_TITLE>",
  "author": "<user's name if known, otherwise leave as empty string>",
  "date": "<today's date in YYYY-MM-DD format>",
  "theme": {
    "name": "<THEME_NAME>",
    "path": "<THEME_PATH or null>"
  },
  "settings": {
    "aspectRatio": "16/9",
    "canvasWidth": 980,
    "highlighter": "shiki"
  }
}
```

Write `.slidecraft/cif.json` at `WORKSPACE_DIR/.slidecraft/cif.json` with this exact structure:

```json
{
  "meta": {
    "title": "<PRESENTATION_TITLE>",
    "subtitle": "",
    "author": "<user's name if known, otherwise empty string>",
    "date": "<today's date in YYYY-MM-DD format>",
    "theme": "<THEME_NAME>",
    "themePath": "<THEME_PATH or null>"
  },
  "slides": []
}
```

Do not create `slides.md` yet — it is generated later by the authoring pipeline.

### Install theme dependencies

If a custom theme was selected (`THEME_PATH` is not null), check whether `node_modules/` exists inside the theme directory. If not, run:

```bash
cd <resolved THEME_PATH>
npm install
```

This installs the theme's dependencies (e.g., `unocss`) so Slidev can load the theme without errors. Also create a `package.json` in the workspace itself if one doesn't exist:

```bash
cd <WORKSPACE_DIR>
npm init -y
```

---

## Step 5 — Prompt for Raw Material

Tell the user:

> Your workspace is ready at `<WORKSPACE_DIR>`.
>
> **Next: drop your raw material into the `assets/` folder.**
>
> This can include anything you want to turn into slides:
> - Markdown or text files with outlines, notes, or talking points
> - Images, diagrams, or screenshots you want to include
> - PDFs or documents to reference
> - A bullet list pasted directly into the chat
>
> Once you've added your material (or if you'd rather start from scratch), let me know and I'll begin drafting the presentation.

---

## Step 6 — Hand Off to Authoring

When the user confirms they've added material or wants to start from scratch, tell them:

> To begin drafting, just say something like:
> - "Draft the presentation"
> - "Build slides from the assets"
> - Or describe what you want on each slide and I'll structure it for you.
>
> I'll analyze the `assets/` folder, build the slide structure in `cif.json`, and render `slides.md` ready for Slidev.
