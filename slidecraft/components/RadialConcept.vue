<catalog>
use: A mind-map style concept with a central idea and branching sub-topics.
looks: An emphasised central concept with primary branch boxes radiating around it and leaf items in a spaced perimeter lane.
fill: 1st top-level item = the centre; its children = branches; grandchildren = each branch's items.
</catalog>
<!--
RadialConcept.vue

A radial concept / mind-map: an emphasised central concept, primary branch boxes radiating
around it, and each branch's secondary items as small leaf pills in a spaced perimeter lane
(so pills never overlap each other or the branches).

Props:
- center: { label, desc? } — central concept.
- branches: Array<{ label, color?, items?: string[] }> — primary branches + secondary items.
- title?: string — optional heading.
- animate: boolean — default true.

Usage:
<RadialConcept
  :center="{ label: 'Product vision', desc: 'A useful, trusted platform' }"
  :branches="[
    { label: 'Customers', items: ['Needs', 'Research', 'Feedback'] },
    { label: 'Experience', color: '#B07D2B', items: ['Simple', 'Fast'] }
  ]"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

const props = defineProps({
  center: {
    type: Object,
    default: () => ({
      label: 'Product vision',
      desc: 'A shared direction for meaningful growth',
    }),
  },
  branches: {
    type: Array,
    default: () => [
      { label: 'Customer', items: ['Core needs', 'Key journeys', 'Feedback loops'] },
      { label: 'Experience', items: ['Simple flows', 'Clear language'] },
      { label: 'Growth', items: ['Acquisition', 'Activation', 'Retention'] },
      { label: 'Platform', items: ['Reliability', 'Data foundation'] },
      { label: 'Team', items: ['Ownership', 'Capabilities', 'Ways of working'] },
    ],
  },
  title: {
    type: String,
    default: '',
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const d=700; const tick=(now)=>{const t=Math.min(1,(now-start)/d);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: top <li> is the center; its children are branches; grandchildren = items.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  const first = tree[0] || { text: '', children: [] }
  const cp = parseLabel(first.text)
  const center = { label: cp.parts[0] || '' }
  if (cp.parts[1]) center.desc = cp.parts[1]
  const branches = (first.children || []).map(ch => {
    const { color, parts } = parseLabel(ch.text)
    const b = { label: parts[0] || '' }
    if (color) b.color = color
    if (ch.children.length) b.items = ch.children.map(g => g.text)
    return b
  })
  return { center, branches }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : { center: props.center, branches: props.branches }))
const centerData = computed(() => model.value.center)
const branchesData = computed(() => model.value.branches)

const W = 1040
const H = 660
const cx = 520
const cy = 330
const centerW = 210
const centerH = 92
const branchW = 142
const branchH = 54
const pillH = 28
const pillGap = 9
const maxPillW = 132
const minPillW = 76
const colors = ['#28527A', '#B07D2B', '#3F7D74']

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))
const easeWindow = (start, end) => clamp((progress.value - start) / (end - start), 0, 1)

function pillWidth(text) {
  return clamp(28 + String(text).length * 6.5, minPillW, maxPillW)
}

const layout = computed(() => {
  const source = Array.isArray(branchesData.value) ? branchesData.value.slice(0, 8) : []
  const count = source.length
  if (!count) return []

  /*
   * Branches use a broad ellipse. Leaf columns are placed in dedicated
   * perimeter lanes: top/bottom columns stack vertically, side columns
   * stack horizontally. This keeps adjacent groups spatially separated.
   */
  const rx = count <= 5 ? 270 : 250
  const ry = count <= 5 ? 190 : 180
  const titleOffset = props.title ? 18 : 0
  const usableCy = cy + titleOffset
  const marginX = 18
  const marginTop = props.title ? 58 : 18
  const marginBottom = 18

  return source.map((branch, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / count
    const ux = Math.cos(angle)
    const uy = Math.sin(angle)
    const bx = cx + ux * rx
    const by = usableCy + uy * ry
    const items = Array.isArray(branch.items) ? branch.items.slice(0, 3) : []
    const sideward = Math.abs(ux) >= Math.abs(uy)
    const widths = items.map(pillWidth)
    const maxWidth = widths.length ? Math.max(...widths) : minPillW
    const connectorGap = 13
    const columnGap = 12

    let pills = []
    let connector = null

    if (items.length && sideward) {
      const direction = ux >= 0 ? 1 : -1
      const startEdge = bx + direction * branchW / 2
      const firstCenter = startEdge + direction * (connectorGap + widths[0] / 2)
      const totalWidth = widths.reduce((sum, width) => sum + width, 0)
        + columnGap * Math.max(0, widths.length - 1)
      const rawLeft = direction > 0
        ? firstCenter - widths[0] / 2
        : firstCenter + widths[0] / 2 - totalWidth
      const columnLeft = clamp(rawLeft, marginX, W - marginX - totalWidth)

      let cursor = direction > 0 ? columnLeft : columnLeft + totalWidth
      pills = items.map((item, itemIndex) => {
        const width = widths[itemIndex]
        const x = direction > 0 ? cursor : cursor - width
        cursor += direction * (width + columnGap)
        return {
          label: item,
          x,
          y: clamp(by - pillH / 2, marginTop, H - marginBottom - pillH),
          width,
        }
      })

      const first = pills[0]
      const targetX = direction > 0 ? first.x : first.x + first.width
      connector = {
        x1: startEdge,
        y1: by,
        x2: targetX,
        y2: first.y + pillH / 2,
      }
    } else if (items.length) {
      const direction = uy >= 0 ? 1 : -1
      const startEdge = by + direction * branchH / 2
      const totalHeight = items.length * pillH + (items.length - 1) * pillGap
      const rawTop = direction > 0
        ? startEdge + connectorGap
        : startEdge - connectorGap - totalHeight
      const columnTop = clamp(rawTop, marginTop, H - marginBottom - totalHeight)

      pills = items.map((item, itemIndex) => {
        const width = widths[itemIndex]
        return {
          label: item,
          x: clamp(bx - width / 2, marginX, W - marginX - width),
          y: columnTop + itemIndex * (pillH + pillGap),
          width,
        }
      })

      const first = direction > 0 ? pills[0] : pills[pills.length - 1]
      const targetY = direction > 0 ? first.y : first.y + pillH
      connector = {
        x1: bx,
        y1: startEdge,
        x2: clamp(bx, first.x + 8, first.x + first.width - 8),
        y2: targetY,
      }
    }

    const branchStart = 0.18 + index * 0.045
    const branchProgress = easeWindow(branchStart, branchStart + 0.28)
    const itemStart = 0.52 + index * 0.035
    const itemProgress = easeWindow(itemStart, Math.min(1, itemStart + 0.24))

    return {
      ...branch,
      index,
      color: branch.color || colors[index % colors.length],
      bx,
      by,
      ux,
      uy,
      pills,
      connector,
      branchProgress,
      itemProgress,
    }
  })
})

const centerProgress = computed(() => easeWindow(0, 0.28))
</script>

<template>
  <div class="radial-concept-wrap">
    <div ref="src" style="display:none"><slot /></div>
    <svg
      class="radial-concept"
      viewBox="0 0 1040 660"
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      :aria-label="title || `${centerData.label} concept map`"
    >
    <text v-if="title" class="diagram-title" x="520" y="31" text-anchor="middle">
      {{ title }}
    </text>

    <g v-for="branch in layout" :key="`${branch.index}-${branch.label}`">
      <line
        class="spoke"
        :x1="cx + branch.ux * centerW / 2"
        :y1="cy + branch.uy * centerH / 2"
        :x2="cx + (branch.bx - cx) * branch.branchProgress"
        :y2="cy + (branch.by - cy) * branch.branchProgress"
        :style="{ stroke: branch.color, opacity: branch.branchProgress }"
      />

      <g
        :style="{
          opacity: branch.branchProgress,
          transform: `translate(${cx + (branch.bx - cx) * branch.branchProgress}px, ${cy + (branch.by - cy) * branch.branchProgress}px) scale(${0.88 + branch.branchProgress * 0.12})`,
        }"
      >
        <GenBox
          :x="-branchW / 2 + 5"
          :y="-branchH / 2"
          :w="branchW - 5"
          :h="branchH"
          :accent="branch.color"
        />
        <text class="branch-label" x="3" y="1" text-anchor="middle" dominant-baseline="middle">
          {{ branch.label }}
        </text>
      </g>

      <g
        v-if="branch.connector"
        :style="{ opacity: branch.itemProgress }"
      >
        <line
          class="item-connector"
          :x1="branch.connector.x1"
          :y1="branch.connector.y1"
          :x2="branch.connector.x2"
          :y2="branch.connector.y2"
          :style="{ stroke: branch.color }"
        />

        <g
          v-for="(pill, itemIndex) in branch.pills"
          :key="`${branch.index}-${itemIndex}-${pill.label}`"
          :style="{
            opacity: branch.itemProgress,
            transform: `translate(0px, ${(1 - branch.itemProgress) * -branch.uy * 8}px)`,
          }"
        >
          <rect
            class="item-pill"
            :x="pill.x"
            :y="pill.y"
            :width="pill.width"
            :height="pillH"
            rx="14"
          />
          <text
            class="item-label"
            :x="pill.x + pill.width / 2"
            :y="pill.y + pillH / 2 + 0.5"
            text-anchor="middle"
            dominant-baseline="middle"
          >
            {{ pill.label }}
          </text>
        </g>
      </g>
    </g>

    <g
      class="center-node"
      :style="{
        opacity: centerProgress,
        transform: `translate(${cx}px, ${cy}px) scale(${0.82 + centerProgress * 0.18})`,
      }"
    >
      <rect
        :x="-centerW / 2"
        :y="-centerH / 2"
        :width="centerW"
        :height="centerH"
        rx="18"
      />
      <text
        class="center-label"
        x="0"
        :y="center.desc ? -10 : 1"
        text-anchor="middle"
        dominant-baseline="middle"
      >
        {{ centerData.label }}
      </text>
      <text
        v-if="centerData.desc"
        class="center-desc"
        x="0"
        y="18"
        text-anchor="middle"
        dominant-baseline="middle"
      >
        {{ centerData.desc }}
      </text>
    </g>
    </svg>
  </div>
</template>

<style scoped>
.radial-concept {
  display: block;
  max-width: 100%;
  max-height: 100%;
  overflow: hidden;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.diagram-title {
  fill: #1C2530;
  font-size: 18px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.spoke {
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
}

.branch-box {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.branch-accent {
  fill: none;
  stroke-width: 3;
}

.branch-label {
  fill: #1C2530;
  font-size: 14px;
  font-weight: 650;
}

.item-connector {
  fill: none;
  stroke-width: 1;
  stroke-linecap: round;
  opacity: 0.55;
}

.item-pill {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.item-label {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 500;
}

.center-node {
  transform-box: fill-box;
  transform-origin: center;
}

.center-node rect {
  fill: #28527A;
  stroke: #1D3E5E;
  stroke-width: 1;
}

.center-label {
  fill: #FFFFFF;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.center-desc {
  fill: #FFFFFF;
  font-size: 13px;
  font-weight: 450;
  opacity: 0.82;
}
</style>
