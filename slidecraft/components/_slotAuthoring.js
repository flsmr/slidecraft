// _slotAuthoring.js
//
// Shared helper that lets the structural diagram components in this theme be
// authored from the slide as a nested markdown bullet list (the ".vue is a smart
// template, the data lives in slides.md" model), while keeping their props as a
// fallback. Leading `_` + `.js` extension => Slidev does NOT register this as a
// component; it is imported by the diagram components via a relative path.
//
// Convention (see AUTHORING-HANDOFF.md):
//   <Component>
//
//   - 🔎 Label | badge   [navy]
//     - child item
//     - child item
//   - 🎯 Label | badge
//
//   </Component>
//
// Each `<li>`:
//   - label       = the li's DIRECT text (everything before any nested <ul>/<ol>)
//   - children    = a nested <ul>/<ol>, recursed into { text, children }[]
// Inline encodings in the label text (decoded by parseLabel):
//   - leading emoji            -> icon
//   - " | " segments           -> parts[] (label | badge, label | desc, ...)
//   - trailing [navy|ochre|teal|#hex|var(--x)] -> per-item color token

import { ref, onMounted, onBeforeUnmount } from 'vue'

// Monotonic id generator for per-instance SVG ids (clipPath, marker, …).
let _seq = 0
export function nextId(prefix = 'gen') {
  _seq += 1
  return `${prefix}-${_seq}`
}

// ---- label decoding --------------------------------------------------------

export function colorToken(raw) {
  const k = String(raw).trim().toLowerCase()
  if (k === 'navy') return '#28527A'
  if (k === 'ochre') return '#B07D2B'
  if (k === 'teal') return '#3F7D74'
  return String(raw).trim()
}

// Decode one label string into { icon, color, text, parts }.
// `text` is the label with the icon + [color] stripped; `parts` = text split on "|".
export function parseLabel(raw) {
  let text = (raw == null ? '' : String(raw)).replace(/\s+/g, ' ').trim()

  let color = null
  const cm = text.match(/\[\s*(navy|ochre|teal|#[0-9a-fA-F]{3,8}|var\([^)]+\))\s*\]\s*$/i)
  if (cm) {
    color = colorToken(cm[1])
    text = text.slice(0, cm.index).trim()
  }

  let icon = null
  const im = text.match(/^(\p{Extended_Pictographic}(?:️|‍\p{Extended_Pictographic})*)\s+/u)
  if (im) {
    icon = im[1]
    text = text.slice(im[0].length).trim()
  }

  const parts = text.split('|').map(s => s.trim())
  return { icon, color, text, parts }
}

// ---- shared geometry -------------------------------------------------------

// Path `d` for the LEFT border of a rounded rect (top-left corner → down the left
// edge → bottom-left corner), so an SVG accent bar hugs the box's rounded corners
// exactly like FlowDiagram's CSS `border-left` does. Stroke it (fill:none) at the
// desired width. x = box left edge, y = box top, h = box height, r = corner radius.
export function leftBorderPath(x, y, h, r) {
  return `M ${x + r} ${y} A ${r} ${r} 0 0 0 ${x} ${y + r} L ${x} ${y + h - r} A ${r} ${r} 0 0 0 ${x + r} ${y + h}`
}

// ---- DOM -> { text, children }[] tree --------------------------------------

function directText(li) {
  let out = ''
  li.childNodes.forEach(node => {
    if (node.nodeType === 3) {
      out += node.textContent
    } else if (node.nodeType === 1 && !/^(ul|ol)$/i.test(node.tagName)) {
      out += node.textContent
    }
  })
  return out.replace(/\s+/g, ' ').trim()
}

function walk(listEl) {
  const items = []
  listEl.querySelectorAll(':scope > li').forEach(li => {
    const nested = li.querySelector(':scope > ul, :scope > ol')
    items.push({ text: directText(li), children: nested ? walk(nested) : [] })
  })
  return items
}

// Hook: returns { src, parsed }. Put `<div ref="src" style="display:none"><slot/></div>`
// in the template; `parsed` is the top-level { text, children }[] (or null when the
// slot has no list, so the component should fall back to its props/defaults).
export function useSlotTree() {
  const src = ref(null)
  const parsed = ref(null)
  let observer = null

  function parse() {
    const el = src.value
    if (!el) { parsed.value = null; return }
    const top = el.querySelector(':scope > ul, :scope > ol') || el.querySelector('ul, ol')
    const tree = top ? walk(top) : null
    parsed.value = tree && tree.length ? tree : null
  }

  onMounted(() => {
    parse()
    observer = new MutationObserver(() => parse())
    if (src.value) {
      observer.observe(src.value, { childList: true, subtree: true, characterData: true })
    }
  })
  onBeforeUnmount(() => observer && observer.disconnect())

  return { src, parsed }
}
