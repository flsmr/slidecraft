<catalog>
use: Showing part-to-whole composition weighted by size, when there are too many categories for a pie chart.
looks: Nested rectangular tiles sized proportionally to value, each labelled with its name and value.
fill: prop-only; :data=[{label, value}, …].
</catalog>
<!--
Treemap.vue

Props:
- data: Array<{ label: string; value: number; color?: string }> — tile data.
- unit: String — suffix appended to formatted values.
- title: String — accessible chart title.
- showValues: Boolean — show values inside tiles (default true).
- animate: Boolean — enable the subtle enter animation (default true).

Usage:
<Treemap
  title="Revenue by segment"
  unit="M"
  :data="[
    { label: 'Enterprise', value: 42 },
    { label: 'Mid-market', value: 27 },
    { label: 'Small business', value: 16 },
    { label: 'Public sector', value: 9 },
    { label: 'Partners', value: 5 },
    { label: 'Other', value: 3 }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type TreemapItem = {
  label: string
  value: number
  color?: string
}

type LayoutItem = TreemapItem & {
  key: string
  x: number
  y: number
  width: number
  height: number
  color: string
  lines: string[]
  showLabel: boolean
  showValue: boolean
}

const props = defineProps({
  data: {
    type: Array as () => TreemapItem[],
    default: () => [
      { label: 'Enterprise', value: 42 },
      { label: 'Mid-market', value: 27 },
      { label: 'Small business', value: 16 },
      { label: 'Public sector', value: 9 },
      { label: 'Partners', value: 5 },
      { label: 'Other', value: 3 },
    ],
  },
  unit: {
    type: String,
    default: 'M',
  },
  title: {
    type: String,
    default: 'Revenue by segment',
  },
  showValues: {
    type: Boolean,
    default: true,
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const viewWidth = 960
const viewHeight = 500
const plot = { x: 2, y: 2, width: 956, height: 496 }
const gap = 2
const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

function worstRatio(row: Array<TreemapItem & { area: number }>, side: number) {
  if (!row.length || side <= 0) return Infinity
  const sum = row.reduce((total, item) => total + item.area, 0)
  const max = Math.max(...row.map(item => item.area))
  const min = Math.min(...row.map(item => item.area))
  return Math.max(
    (side * side * max) / (sum * sum),
    (sum * sum) / (side * side * min),
  )
}

function placeRow(
  row: Array<TreemapItem & { area: number; sourceIndex: number }>,
  rect: { x: number; y: number; width: number; height: number },
) {
  const result: Array<TreemapItem & {
    area: number
    sourceIndex: number
    x: number
    y: number
    width: number
    height: number
  }> = []
  const area = row.reduce((total, item) => total + item.area, 0)

  if (rect.width >= rect.height) {
    const rowWidth = rect.height > 0 ? area / rect.height : 0
    let y = rect.y
    row.forEach((item, index) => {
      const height = rowWidth > 0
        ? (index === row.length - 1 ? rect.y + rect.height - y : item.area / rowWidth)
        : 0
      result.push({ ...item, x: rect.x, y, width: rowWidth, height })
      y += height
    })
    rect.x += rowWidth
    rect.width = Math.max(0, rect.width - rowWidth)
  } else {
    const rowHeight = rect.width > 0 ? area / rect.width : 0
    let x = rect.x
    row.forEach((item, index) => {
      const width = rowHeight > 0
        ? (index === row.length - 1 ? rect.x + rect.width - x : item.area / rowHeight)
        : 0
      result.push({ ...item, x, y: rect.y, width, height: rowHeight })
      x += width
    })
    rect.y += rowHeight
    rect.height = Math.max(0, rect.height - rowHeight)
  }

  return result
}

function wrapLabel(label: string, width: number, maxLines: number) {
  const maxChars = Math.max(3, Math.floor((width - 20) / 7.2))
  if (maxLines <= 0 || maxChars < 3) return []

  const words = label.trim().split(/\s+/)
  const lines: string[] = []
  let current = ''

  for (const word of words) {
    if (word.length > maxChars && !current) {
      lines.push(`${word.slice(0, Math.max(1, maxChars - 1))}…`)
    } else if (!current || `${current} ${word}`.length <= maxChars) {
      current = current ? `${current} ${word}` : word
    } else {
      lines.push(current)
      current = word
    }
    if (lines.length === maxLines) break
  }

  if (current && lines.length < maxLines) lines.push(current)

  const represented = lines.join(' ').replace(/…$/, '')
  if (represented.length < label.length && lines.length) {
    const last = lines.length - 1
    lines[last] = `${lines[last].slice(0, Math.max(1, maxChars - 1)).trimEnd()}…`
  }

  return lines
}

const tiles = computed<LayoutItem[]>(() => {
  const valid = props.data
    .map((item, sourceIndex) => ({
      ...item,
      sourceIndex,
      value: Number(item.value),
    }))
    .filter(item => Number.isFinite(item.value) && item.value > 0)
    .sort((a, b) => b.value - a.value)

  const total = valid.reduce((sum, item) => sum + item.value, 0)
  if (!total) return []

  const availableArea = plot.width * plot.height
  const remaining = valid.map(item => ({
    ...item,
    area: (item.value / total) * availableArea,
  }))
  const rect = { ...plot }
  const positioned: ReturnType<typeof placeRow> = []
  let row: typeof remaining = []

  while (remaining.length) {
    const candidate = remaining[0]
    const side = Math.min(rect.width, rect.height)
    if (!row.length || worstRatio([...row, candidate], side) <= worstRatio(row, side)) {
      row.push(remaining.shift()!)
    } else {
      positioned.push(...placeRow(row, rect))
      row = []
    }
  }
  if (row.length) positioned.push(...placeRow(row, rect))

  return positioned.map((item, layoutIndex) => {
    const x = item.x + gap / 2
    const y = item.y + gap / 2
    const width = Math.max(0, item.width - gap)
    const height = Math.max(0, item.height - gap)
    const showLabel = width >= 62 && height >= 38
    const showValue = props.showValues && width >= 54 && height >= 58
    const maxLines = showValue
      ? Math.min(2, Math.floor((height - 42) / 17))
      : Math.min(3, Math.floor((height - 20) / 17))

    return {
      ...item,
      key: `${item.label}-${item.sourceIndex}`,
      x,
      y,
      width,
      height,
      color: item.color || palette[layoutIndex % palette.length],
      showLabel,
      showValue,
      lines: showLabel ? wrapLabel(item.label, width, maxLines) : [],
    }
  })
})

const animatedTiles = computed(() => tiles.value.map(tile => {
  const scale = 0.86 + progress.value * 0.14
  const width = tile.width * scale
  const height = tile.height * scale
  return {
    ...tile,
    animatedX: tile.x + (tile.width - width) / 2,
    animatedY: tile.y + (tile.height - height) / 2,
    animatedWidth: width,
    animatedHeight: height,
  }
}))

const textOpacity = computed(() => Math.max(0, Math.min(1, (progress.value - 0.38) / 0.62)))

function formatValue(value: number) {
  return `${new Intl.NumberFormat(undefined, {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value)}${props.unit}`
}
</script>

<template>
  <div class="treemap">
    <svg
      :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
      role="img"
      :aria-labelledby="`${ctx.$page}-treemap-title ${ctx.$page}-treemap-desc`"
      preserveAspectRatio="xMidYMid meet"
    >
      <title :id="`${ctx.$page}-treemap-title`">{{ title }}</title>
      <desc :id="`${ctx.$page}-treemap-desc`">
        A proportional treemap containing {{ tiles.length }} categories.
      </desc>

      <g v-for="tile in animatedTiles" :key="tile.key">
        <rect
          :x="tile.animatedX"
          :y="tile.animatedY"
          :width="tile.animatedWidth"
          :height="tile.animatedHeight"
          :fill="tile.color"
          rx="3"
          ry="3"
        />

        <g
          v-if="tile.showLabel && tile.lines.length"
          class="tile-text"
          :opacity="textOpacity"
          :transform="`translate(${tile.x + 12} ${tile.y + 12})`"
        >
          <text class="label" x="0" y="0" dominant-baseline="hanging">
            <tspan
              v-for="(line, lineIndex) in tile.lines"
              :key="lineIndex"
              x="0"
              :dy="lineIndex === 0 ? 0 : 17"
            >{{ line }}</tspan>
          </text>
          <text
            v-if="tile.showValue"
            class="value"
            x="0"
            :y="Math.max(31, tile.height - 25)"
            dominant-baseline="hanging"
          >{{ formatValue(tile.value) }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.treemap {
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

rect {
  stroke: #FFFFFF;
  stroke-width: 0;
}

.tile-text {
  pointer-events: none;
}

.label,
.value {
  fill: #FFFFFF;
  paint-order: stroke;
  stroke: rgb(0 0 0 / 0.12);
  stroke-width: 1.5;
  stroke-linejoin: round;
}

.label {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.value {
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
</style>
