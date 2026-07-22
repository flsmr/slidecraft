<catalog>
use: A containment hierarchy where concepts sit inside other concepts.
looks: Nested labelled boxes, each parent enclosing its children, drawn outer to inner.
fill: nested bullet list is the containment tree itself, recursing through children.
</catalog>
<!--
NestedBox.vue

A nested-box / containment diagram: concepts contained within concepts. Implemented as a
self-recursive component (references itself by name), so it renders any depth without a
runtime template compiler.

Props:
- root: nested Node object: { label, desc?, color?, children?: Node[] }.
  Each node becomes a labelled container enclosing its children.
- title: optional heading above the diagram.
- layout: currently supports "nested" (default), children wrap inside parents.
- animate: enables a subtle outer-to-inner reveal.
- node / depth / order: INTERNAL — used by the recursion; do not set these yourself.

Usage:
<NestedBox
  title="Operating model"
  :root="{
    label: 'Enterprise',
    desc: 'Shared direction and governance',
    children: [
      { label: 'Product', children: [ { label: 'Discovery' }, { label: 'Delivery' } ] },
      { label: 'Operations', desc: 'Run reliably' },
      { label: 'Enablement', desc: 'Build capability' }
    ]
  }"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

defineOptions({ name: 'NestedBox' })

const props = defineProps({
  root: {
    type: Object,
    default: () => ({
      label: 'Organisation',
      desc: 'A connected system of capabilities',
      children: [
        {
          label: 'Product',
          desc: 'Create customer value',
          children: [
            { label: 'Discovery', desc: 'Understand needs' },
            { label: 'Delivery', desc: 'Turn insight into outcomes' },
          ],
        },
        { label: 'Operations', desc: 'Run services reliably' },
        { label: 'Enablement', desc: 'Grow shared capability' },
      ],
    }),
  },
  title: { type: String, default: '' },
  layout: { type: String, default: 'nested' },
  animate: { type: Boolean, default: true },
  // internal recursion props
  node: { type: Object, default: null },
  depth: { type: Number, default: 0 },
  order: { type: Number, default: 0 },
})

// Nested-list authoring: the nested list defines containment (recurse). Only the root
// instance carries the slot; child instances receive their node via :node.
const { src, parsed } = useSlotTree()
function toNode(n) {
  const { color, parts } = parseLabel(n.text)
  const out = { label: parts[0] || '' }
  if (parts[1]) out.desc = parts[1]
  if (color) out.color = color
  if (n.children.length) out.children = n.children.map(toNode)
  return out
}
function mapToShape(tree) {
  return tree.length === 1 ? toNode(tree[0]) : { label: props.title || 'System', children: tree.map(toNode) }
}
const rootData = computed(() => (parsed.value ? mapToShape(parsed.value) : props.root))

const isRoot = computed(() => props.node === null)
const current = computed(() => props.node || props.root)
const children = computed(() => Array.isArray(current.value?.children) ? current.value.children : [])

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const tick=(now)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const palette = [
  '#28527A',
  '#3F7D74',
  '#B07D2B',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

function nodeColor(node, depth) {
  return node?.color || palette[Math.min(depth, palette.length - 1)]
}

const styleVars = computed(() => {
  const delay = Math.min(0.6, props.depth * 0.14)
  const local = Math.max(0, Math.min(1, (progress.value - delay) / Math.max(0.2, 1 - delay)))
  return {
    '--node-color': nodeColor(current.value, props.depth),
    '--depth-tint': `${Math.min(0.055, props.depth * 0.012)}`,
    opacity: local,
    transform: `translateY(${(1 - local) * 6}px) scale(${0.985 + local * 0.015})`,
  }
})
</script>

<template>
  <div v-if="isRoot" class="nested-box" :class="`layout-${layout}`">
    <div ref="src" style="display:none"><slot /></div>
    <h3 v-if="title" class="diagram-title">{{ title }}</h3>
    <div class="diagram-frame">
      <NestedBox :node="rootData" :depth="0" :order="0" :animate="props.animate" />
    </div>
  </div>

  <section
    v-else
    class="nested-node"
    :class="{ leaf: !children.length, 'is-root': depth === 0 }"
    :style="styleVars"
  >
    <header class="node-heading">
      <span class="node-chip">{{ current.label }}</span>
      <p v-if="current.desc" class="node-desc">{{ current.desc }}</p>
    </header>

    <div v-if="children.length" class="node-children">
      <NestedBox
        v-for="(child, index) in children"
        :key="(child.label || 'node') + '-' + index"
        :node="child"
        :depth="depth + 1"
        :order="order + index + 1"
        :animate="props.animate"
      />
    </div>
  </section>
</template>

<style scoped>
.nested-box {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.diagram-title {
  margin: 0 0 0.7rem;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: clamp(16px, 1.65vw, 21px);
  font-weight: 650;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.diagram-frame {
  width: 100%;
  max-width: 100%;
}

.nested-node {
  --node-color: #28527A;
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  padding: 0.8rem;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-left: 3px solid var(--node-color);
  border-radius: 8px;
  background:
    linear-gradient(
      rgba(28, 37, 48, var(--depth-tint)),
      rgba(28, 37, 48, var(--depth-tint))
    ),
    #F5F6F8;
  transform-origin: top left;
  will-change: opacity, transform;
}

.nested-node.is-root {
  padding: 0.95rem;
  background: #FFFFFF;
  box-shadow: 0 1px 0 rgba(28, 37, 48, 0.03);
}

.node-heading {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 0.65rem;
}

.node-chip {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  max-width: 100%;
  padding: 0.22rem 0.55rem;
  border: 1px solid color-mix(in srgb, var(--node-color) 42%, #DFE3E8);
  border-radius: 5px;
  background: #FFFFFF;
  color: #1C2530;
  font-size: clamp(13px, 1.15vw, 15px);
  font-weight: 650;
  line-height: 1.25;
}

.is-root > .node-heading > .node-chip {
  border-color: #28527A;
  box-shadow: inset 3px 0 0 #28527A;
}

.node-desc {
  min-width: 0;
  margin: 0;
  color: #5A6472;
  font-size: clamp(12px, 1.05vw, 14px);
  line-height: 1.35;
}

.node-children {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0.65rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #DFE3E8;
}

.node-children > .nested-node {
  flex: 1 1 min(12rem, 100%);
}

.nested-node.leaf {
  min-height: 4.5rem;
}

@media (max-width: 640px) {
  .node-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.35rem;
  }

  .node-children > .nested-node {
    flex-basis: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .nested-node {
    will-change: auto;
  }
}
</style>
