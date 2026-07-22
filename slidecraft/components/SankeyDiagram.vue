<catalog>
use: Showing how a quantity flows and splits between stages (e.g. energy or budget flow).
looks: Coloured node bars connected by proportionally-wide flow ribbons, left to right.
fill: prop-only; :nodes=[{id, label, column}], :links=[{source, target, value}].
</catalog>
<!--
SankeyDiagram.vue

Props:
- nodes: Array<{ id: string, label: string, column?: number, color?: string }>
- links: Array<{ source: string, target: string, value: number }>
- unit: String appended to displayed values.
- title: Accessible chart title.
- nodeWidth: Width of each node rectangle in SVG units (default 16).
- animate: Enables the subtle enter animation (default true).

Usage:
<SankeyDiagram
  title="Annual energy flow"
  unit=" GWh"
  :node-width="18"
  :nodes="[
    { id: 'solar', label: 'Solar' },
    { id: 'wind', label: 'Wind' },
    { id: 'grid', label: 'Grid' },
    { id: 'storage', label: 'Storage' },
    { id: 'homes', label: 'Homes' },
    { id: 'industry', label: 'Industry' }
  ]"
  :links="[
    { source: 'solar', target: 'grid', value: 42 },
    { source: 'solar', target: 'storage', value: 18 },
    { source: 'wind', target: 'grid', value: 34 },
    { source: 'wind', target: 'storage', value: 12 },
    { source: 'grid', target: 'homes', value: 45 },
    { source: 'grid', target: 'industry', value: 31 },
    { source: 'storage', target: 'homes', value: 30 }
  ]"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const props = defineProps({
  nodes: {
    type: Array,
    default: () => [
      { id: 'solar', label: 'Solar' },
      { id: 'wind', label: 'Wind' },
      { id: 'grid', label: 'Grid' },
      { id: 'storage', label: 'Storage' },
      { id: 'homes', label: 'Homes' },
      { id: 'industry', label: 'Industry' },
    ],
  },
  links: {
    type: Array,
    default: () => [
      { source: 'solar', target: 'grid', value: 42 },
      { source: 'solar', target: 'storage', value: 18 },
      { source: 'wind', target: 'grid', value: 34 },
      { source: 'wind', target: 'storage', value: 12 },
      { source: 'grid', target: 'homes', value: 45 },
      { source: 'grid', target: 'industry', value: 31 },
    ],
  },
  unit: { type: String, default: ' GWh' },
  title: { type: String, default: 'Energy flow' },
  nodeWidth: { type: Number, default: 16 },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const tick=(now)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const W = 960
const H = 500
const margin = { top: 54, right: 132, bottom: 30, left: 132 }
const gap = 22
const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const layout = computed(() => {
  const inputNodes = props.nodes
    .filter(n => n && n.id != null)
    .map((n, index) => ({
      ...n,
      id: String(n.id),
      index,
      inflow: 0,
      outflow: 0,
      incoming: [],
      outgoing: [],
    }))

  const byId = new Map(inputNodes.map(n => [n.id, n]))
  const validLinks = props.links
    .map((link, index) => ({
      ...link,
      index,
      source: String(link.source),
      target: String(link.target),
      value: Math.max(0, Number(link.value) || 0),
    }))
    .filter(link =>
      link.value > 0 &&
      link.source !== link.target &&
      byId.has(link.source) &&
      byId.has(link.target)
    )

  validLinks.forEach(link => {
    const source = byId.get(link.source)
    const target = byId.get(link.target)
    source.outflow += link.value
    target.inflow += link.value
    source.outgoing.push(link)
    target.incoming.push(link)
  })

  const inferred = new Map(inputNodes.map(n => [n.id, 0]))
  for (let pass = 0; pass < inputNodes.length; pass++) {
    let changed = false
    validLinks.forEach(link => {
      const next = (inferred.get(link.source) || 0) + 1
      if (next > (inferred.get(link.target) || 0) && next < inputNodes.length) {
        inferred.set(link.target, next)
        changed = true
      }
    })
    if (!changed) break
  }

  inputNodes.forEach(node => {
    const explicit = Number(node.column)
    node.column = Number.isFinite(explicit)
      ? Math.max(0, Math.floor(explicit))
      : inferred.get(node.id) || 0
    node.total = Math.max(node.inflow, node.outflow, 0)
  })

  const rawColumns = [...new Set(inputNodes.map(n => n.column))].sort((a, b) => a - b)
  const normalizedColumn = new Map(rawColumns.map((column, index) => [column, index]))
  inputNodes.forEach(node => { node.column = normalizedColumn.get(node.column) })

  const columnCount = Math.max(1, rawColumns.length)
  const columns = Array.from({ length: columnCount }, () => [])
  inputNodes.forEach(node => columns[node.column].push(node))
  columns.forEach(column => column.sort((a, b) => a.index - b.index))

  const plotHeight = H - margin.top - margin.bottom
  const scaleCandidates = columns.map(column => {
    const total = column.reduce((sum, node) => sum + node.total, 0)
    const available = plotHeight - Math.max(0, column.length - 1) * gap
    return total > 0 ? available / total : Infinity
  })
  const scale = Math.max(0, Math.min(...scaleCandidates.filter(Number.isFinite), 8))
  const xStep = columnCount > 1
    ? (W - margin.left - margin.right - props.nodeWidth) / (columnCount - 1)
    : 0

  columns.forEach((column, columnIndex) => {
    const used = column.reduce((sum, node) => sum + node.total * scale, 0)
      + Math.max(0, column.length - 1) * gap
    let y = margin.top + Math.max(0, (plotHeight - used) / 2)

    column.forEach(node => {
      node.x = columnCount === 1
        ? (W - props.nodeWidth) / 2
        : margin.left + columnIndex * xStep
      node.y = y
      node.height = Math.max(2, node.total * scale)
      node.color = node.color || palette[columnIndex % palette.length]
      node.sourceOffset = 0
      node.targetOffset = 0
      y += node.height + gap
    })
  })

  const orderedLinks = [...validLinks].sort((a, b) => {
    const sa = byId.get(a.source)
    const sb = byId.get(b.source)
    const ta = byId.get(a.target)
    const tb = byId.get(b.target)
    return sa.column - sb.column || sa.index - sb.index || ta.index - tb.index || a.index - b.index
  })

  const ribbons = orderedLinks.map(link => {
    const source = byId.get(link.source)
    const target = byId.get(link.target)
    const thickness = link.value * scale
    const sy0 = source.y + source.sourceOffset
    const ty0 = target.y + target.targetOffset
    source.sourceOffset += thickness
    target.targetOffset += thickness

    const x0 = source.x + props.nodeWidth
    const x1 = target.x
    const curve = Math.max(20, (x1 - x0) * 0.48)
    const sy1 = sy0 + thickness
    const ty1 = ty0 + thickness
    const path = [
      `M ${x0} ${sy0}`,
      `C ${x0 + curve} ${sy0}, ${x1 - curve} ${ty0}, ${x1} ${ty0}`,
      `L ${x1} ${ty1}`,
      `C ${x1 - curve} ${ty1}, ${x0 + curve} ${sy1}, ${x0} ${sy1}`,
      'Z',
    ].join(' ')

    return {
      ...link,
      path,
      color: source.color,
      title: `${source.label} → ${target.label}: ${formatValue(link.value)}`,
    }
  })

  return { nodes: inputNodes, ribbons, columnCount }
})

function formatValue(value) {
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)}${props.unit}`
}

function labelX(node) {
  return node.column === 0 ? node.x - 10 : node.x + props.nodeWidth + 10
}

function labelAnchor(node) {
  return node.column === 0 ? 'end' : 'start'
}

function labelY(node) {
  return node.y + node.height / 2 - 2
}
</script>

<template>
  <div class="sankey-diagram">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="title"
      preserveAspectRatio="xMidYMid meet"
    >
      <title>{{ title }}</title>

      <text class="chart-title" x="24" y="29">{{ title }}</text>
      <line class="title-rule" x1="24" y1="40" :x2="W - 24" y2="40" />

      <g class="ribbons" :style="{ opacity: 0.45 * progress }">
        <path
          v-for="link in layout.ribbons"
          :key="`${link.source}-${link.target}-${link.index}`"
          :d="link.path"
          :fill="link.color"
        >
          <title>{{ link.title }}</title>
        </path>
      </g>

      <g
        v-for="node in layout.nodes"
        :key="node.id"
        class="node"
        :style="{ opacity: progress }"
      >
        <rect
          :x="node.x"
          :y="node.y"
          :width="nodeWidth"
          :height="node.height"
          :fill="node.color"
          rx="2"
        >
          <title>{{ `${node.label}: ${formatValue(node.total)}` }}</title>
        </rect>

        <text
          class="node-label"
          :x="labelX(node)"
          :y="labelY(node)"
          :text-anchor="labelAnchor(node)"
        >
          {{ node.label }}
        </text>
        <text
          class="node-value"
          :x="labelX(node)"
          :y="labelY(node) + 16"
          :text-anchor="labelAnchor(node)"
        >
          {{ formatValue(node.total) }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.sankey-diagram {
  width: 100%;
  height: auto;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.chart-title {
  fill: #1C2530;
  font-size: 17px;
  font-weight: 650;
}

.title-rule {
  stroke: #DFE3E8;
  stroke-width: 1;
}

.ribbons {
  pointer-events: visiblePainted;
}

.node-label {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 600;
  dominant-baseline: middle;
}

.node-value {
  fill: #5A6472;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  dominant-baseline: middle;
}

.node rect {
  stroke: #FFFFFF;
  stroke-width: 1;
}
</style>
