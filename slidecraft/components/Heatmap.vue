<!--
Heatmap.vue
Props:
- rows: string[] — row labels.
- cols: string[] — column labels.
- data: number[][] — values addressed as data[row][column].
- unit: string — suffix shown with values and legend bounds.
- title: string — accessible/chart title.
- min / max: number | undefined — optional colour-scale bounds; otherwise data-derived.
- showValues: boolean — print values inside cells (default true).
- colorScale: 'navy' | 'ochre' | 'teal' — single-hue colour ramp.
- animate: boolean — enable the subtle enter animation.

Usage:
<Heatmap
  title="Support demand by team and weekday"
  :rows="['Platform', 'Growth', 'Core']"
  :cols="['Mon', 'Tue', 'Wed', 'Thu', 'Fri']"
  :data="[[18, 24, 31, 27, 20], [12, 17, 22, 29, 25], [9, 14, 19, 16, 11]]"
  unit=" tickets"
  color-scale="teal"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type ScaleName = 'navy' | 'ochre' | 'teal'

const props = defineProps({
  rows: {
    type: Array as () => string[],
    default: () => ['North', 'South', 'East', 'West', 'Central'],
  },
  cols: {
    type: Array as () => string[],
    default: () => ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
  },
  data: {
    type: Array as () => number[][],
    default: () => [
      [18, 26, 34, 48, 61, 72],
      [12, 21, 39, 55, 68, 81],
      [28, 36, 44, 52, 63, 76],
      [9, 17, 31, 46, 58, 69],
      [22, 33, 47, 64, 79, 92],
    ],
  },
  unit: { type: String, default: '%' },
  title: { type: String, default: 'Regional performance heatmap' },
  min: { type: Number, default: undefined },
  max: { type: Number, default: undefined },
  showValues: { type: Boolean, default: true },
  colorScale: {
    type: String as () => ScaleName,
    default: 'navy',
    validator: (value: string) => ['navy', 'ochre', 'teal'].includes(value),
  },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const frame=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const width = 960
const left = 132
const top = 72
const right = 34
const cellGap = 2
const maxGridHeight = 350
const availableWidth = width - left - right

const rowCount = computed(() => props.rows.length)
const colCount = computed(() => props.cols.length)
const cellSize = computed(() => {
  if (!rowCount.value || !colCount.value) return 0
  return Math.min(
    availableWidth / colCount.value,
    maxGridHeight / rowCount.value,
    72,
  )
})
const gridWidth = computed(() => cellSize.value * colCount.value)
const gridHeight = computed(() => cellSize.value * rowCount.value)
const legendY = computed(() => top + gridHeight.value + 54)
const viewHeight = computed(() => Math.max(260, legendY.value + 58))

const finiteValues = computed(() =>
  props.data.flat().filter((value): value is number => Number.isFinite(value)),
)
const derivedMin = computed(() =>
  finiteValues.value.length ? Math.min(...finiteValues.value) : 0,
)
const derivedMax = computed(() =>
  finiteValues.value.length ? Math.max(...finiteValues.value) : 1,
)
const scaleMin = computed(() =>
  Number.isFinite(props.min) ? props.min as number : derivedMin.value,
)
const scaleMax = computed(() => {
  const value = Number.isFinite(props.max) ? props.max as number : derivedMax.value
  return value === scaleMin.value ? scaleMin.value + 1 : value
})

const scale = computed<ScaleName>(() =>
  ['navy', 'ochre', 'teal'].includes(props.colorScale)
    ? props.colorScale as ScaleName
    : 'navy',
)
const gradientId = computed(() => `heatmap-gradient-${scale.value}`)

const cells = computed(() => {
  const totalSteps = Math.max(1, rowCount.value + colCount.value - 2)
  return props.rows.flatMap((_, row) =>
    props.cols.map((__, col) => {
      const raw = props.data[row]?.[col]
      const valid = Number.isFinite(raw)
      const value = valid ? raw : scaleMin.value
      const normalized = Math.max(
        0,
        Math.min(1, (value - scaleMin.value) / (scaleMax.value - scaleMin.value)),
      )
      const delay = ((row + col) / totalSteps) * 0.24
      const local = Math.max(0, Math.min(1, (progress.value - delay) / (1 - delay)))
      const eased = 1 - Math.pow(1 - local, 3)
      const size = Math.max(0, cellSize.value - cellGap)
      const cx = left + col * cellSize.value + cellSize.value / 2
      const cy = top + row * cellSize.value + cellSize.value / 2

      return {
        key: `${row}-${col}`,
        x: cx - (size * eased) / 2,
        y: cy - (size * eased) / 2,
        size: size * eased,
        cx,
        cy,
        value,
        valid,
        normalized,
        opacity: eased,
      }
    }),
  )
})

function fillFor(normalized: number) {
  const stop = Math.round(Math.max(0, Math.min(1, normalized)) * 100)
  const scaleColor = scale.value === 'navy' ? '#1D3E5E' : scale.value === 'ochre' ? '#B07D2B' : '#3F7D74'
  return `color-mix(in srgb, #F5F6F8 ${100 - stop}%, ${scaleColor} ${stop}%)`
}

function textFill(normalized: number) {
  return normalized >= 0.58 ? '#FFFFFF' : '#1C2530'
}

function formatValue(value: number) {
  const rounded = Math.abs(value) >= 100 || Number.isInteger(value)
    ? value.toFixed(0)
    : value.toFixed(1)
  return `${rounded}${props.unit}`
}
</script>

<template>
  <div class="heatmap">
    <svg
      :viewBox="`0 0 ${width} ${viewHeight}`"
      role="img"
      :aria-labelledby="'heatmap-title heatmap-desc'"
    >
      <title id="heatmap-title">{{ title }}</title>
      <desc id="heatmap-desc">
        Matrix heatmap with {{ rowCount }} rows and {{ colCount }} columns.
        Values range from {{ formatValue(scaleMin) }} to {{ formatValue(scaleMax) }}.
      </desc>

      <text class="chart-title" x="0" y="22">{{ title }}</text>

      <g class="column-labels">
        <text
          v-for="(col, index) in cols"
          :key="col"
          class="label"
          :x="left + index * cellSize + cellSize / 2"
          :y="top - 14"
          text-anchor="middle"
        >
          {{ col }}
        </text>
      </g>

      <g class="row-labels">
        <text
          v-for="(row, index) in rows"
          :key="row"
          class="label"
          :x="left - 14"
          :y="top + index * cellSize + cellSize / 2"
          text-anchor="end"
          dominant-baseline="middle"
        >
          {{ row }}
        </text>
      </g>

      <g class="cells">
        <g v-for="cell in cells" :key="cell.key">
          <rect
            :x="cell.x"
            :y="cell.y"
            :width="cell.size"
            :height="cell.size"
            :rx="Math.min(4, cell.size * 0.08)"
            :fill="cell.valid ? fillFor(cell.normalized) : '#F5F6F8'"
            :opacity="cell.opacity"
          />
          <text
            v-if="showValues && cell.valid"
            class="cell-value"
            :x="cell.cx"
            :y="cell.cy"
            :fill="textFill(cell.normalized)"
            :opacity="cell.opacity"
            text-anchor="middle"
            dominant-baseline="middle"
          >
            {{ formatValue(cell.value) }}
          </text>
        </g>
      </g>

      <defs>
        <linearGradient :id="gradientId" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#F5F6F8" />
          <stop
            offset="100%"
            :stop-color="scale === 'navy'
              ? '#1D3E5E'
              : scale === 'ochre'
                ? '#B07D2B'
                : '#3F7D74'"
          />
        </linearGradient>
      </defs>

      <g class="legend" :transform="`translate(${left}, ${legendY})`">
        <text class="legend-label" x="0" y="-10">Value</text>
        <rect
          x="0"
          y="0"
          :width="Math.min(250, gridWidth)"
          height="12"
          rx="3"
          :fill="`url(#${gradientId})`"
        />
        <line x1="0" y1="14" x2="0" y2="20" />
        <line
          :x1="Math.min(250, gridWidth)"
          y1="14"
          :x2="Math.min(250, gridWidth)"
          y2="20"
        />
        <text class="legend-value" x="0" y="36" text-anchor="start">
          {{ formatValue(scaleMin) }}
        </text>
        <text
          class="legend-value"
          :x="Math.min(250, gridWidth)"
          y="36"
          text-anchor="end"
        >
          {{ formatValue(scaleMax) }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.heatmap {
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

.label,
.legend-label {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 500;
}

.cell-value,
.legend-value {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.legend-value {
  fill: #1C2530;
}

.legend line {
  stroke: #DFE3E8;
  stroke-width: 1;
}
</style>
