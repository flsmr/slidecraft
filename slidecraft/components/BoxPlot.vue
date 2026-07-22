<catalog>
use: Comparing the distribution (median, quartiles, spread, outliers) of a value across groups.
looks: A box-and-whisker per group showing quartiles, median line, whiskers, and outlier dots.
fill: prop-only; :groups=[{label, values:[…]}] or {label, min, q1, median, q3, max, outliers}.
</catalog>
<!--
BoxPlot.vue

Props:
- groups: Array of either:
  { label, min, q1, median, q3, max, outliers?: number[] }
  or { label, values: number[] }. Raw values use Tukey quartiles and 1.5×IQR whiskers.
- unit: Unit appended to value-axis tick labels.
- title: Accessible/chart title.
- yLabel: Vertical value-axis label.
- min / max: Optional shared scale bounds.
- animate: Enables the subtle enter animation.

Usage:
<BoxPlot
  title="Response time by region"
  y-label="Response time"
  unit=" ms"
  :groups="[
    { label: 'North', values: [42, 45, 47, 49, 51, 54, 58, 63] },
    { label: 'South', values: [38, 41, 44, 46, 48, 52, 57, 72] },
    { label: 'East', min: 35, q1: 43, median: 49, q3: 56, max: 65, outliers: [76] }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type SummaryGroup = {
  label: string
  min: number
  q1: number
  median: number
  q3: number
  max: number
  outliers?: number[]
}

type ValuesGroup = {
  label: string
  values: number[]
}

type Group = SummaryGroup | ValuesGroup

const props = defineProps({
  groups: {
    type: Array as () => Group[],
    default: () => [
      { label: 'Alpha', values: [42, 45, 47, 49, 51, 53, 55, 58, 61, 74] },
      { label: 'Beta', values: [35, 39, 43, 46, 48, 50, 52, 56, 60, 63] },
      { label: 'Gamma', values: [44, 48, 51, 54, 57, 59, 62, 66, 70, 84] },
      { label: 'Delta', values: [31, 37, 40, 44, 47, 49, 53, 58, 64, 68] },
    ],
  },
  unit: { type: String, default: '' },
  title: { type: String, default: 'Distribution by group' },
  yLabel: { type: String, default: 'Value' },
  max: { type: Number, default: undefined },
  min: { type: Number, default: undefined },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const frame=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const W = 900
const H = 470
const margin = { top: 48, right: 34, bottom: 72, left: 92 }
const plotLeft = margin.left
const plotRight = W - margin.right
const plotTop = margin.top
const plotBottom = H - margin.bottom
const plotWidth = plotRight - plotLeft
const plotHeight = plotBottom - plotTop

function median(sorted: number[]) {
  if (!sorted.length) return 0
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2
}

function tukeySummary(group: ValuesGroup): SummaryGroup {
  const values = group.values.filter(Number.isFinite).slice().sort((a, b) => a - b)
  if (!values.length)
    return { label: group.label, min: 0, q1: 0, median: 0, q3: 0, max: 0, outliers: [] }

  const middle = Math.floor(values.length / 2)
  const lower = values.slice(0, middle)
  const upper = values.slice(values.length % 2 ? middle + 1 : middle)
  const q1 = median(lower.length ? lower : values)
  const q2 = median(values)
  const q3 = median(upper.length ? upper : values)
  const iqr = q3 - q1
  const lowFence = q1 - 1.5 * iqr
  const highFence = q3 + 1.5 * iqr
  const inliers = values.filter(value => value >= lowFence && value <= highFence)

  return {
    label: group.label,
    min: inliers[0] ?? values[0],
    q1,
    median: q2,
    q3,
    max: inliers[inliers.length - 1] ?? values[values.length - 1],
    outliers: values.filter(value => value < lowFence || value > highFence),
  }
}

const summaries = computed<SummaryGroup[]>(() =>
  props.groups.map(group =>
    'values' in group
      ? tukeySummary(group)
      : {
          ...group,
          outliers: group.outliers ?? [],
        },
  ),
)

const dataExtent = computed(() => {
  const values = summaries.value.flatMap(group => [
    group.min,
    group.q1,
    group.median,
    group.q3,
    group.max,
    ...(group.outliers ?? []),
  ]).filter(Number.isFinite)

  return {
    min: values.length ? Math.min(...values) : 0,
    max: values.length ? Math.max(...values) : 1,
  }
})

function niceStep(span: number, target = 6) {
  const rough = Math.max(span, Number.EPSILON) / target
  const power = 10 ** Math.floor(Math.log10(rough))
  const fraction = rough / power
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return niceFraction * power
}

const scale = computed(() => {
  let low = props.min ?? dataExtent.value.min
  let high = props.max ?? dataExtent.value.max
  if (low === high) {
    low -= 1
    high += 1
  }

  const step = niceStep(high - low)
  if (props.min === undefined) low = Math.floor(low / step) * step
  if (props.max === undefined) high = Math.ceil(high / step) * step
  if (high <= low) high = low + step

  return { min: low, max: high, step }
})

const ticks = computed(() => {
  const { min, max, step } = scale.value
  const result: number[] = []
  const first = Math.ceil(min / step) * step
  for (let value = first; value <= max + step * 0.001; value += step)
    result.push(Number(value.toPrecision(12)))
  if (!result.length || Math.abs(result[0] - min) > step * 0.001) result.unshift(min)
  if (Math.abs(result[result.length - 1] - max) > step * 0.001) result.push(max)
  return result
})

function y(value: number) {
  const { min, max } = scale.value
  return plotBottom - ((value - min) / (max - min)) * plotHeight
}

const bandWidth = computed(() => plotWidth / Math.max(1, summaries.value.length))
const boxWidth = computed(() => Math.min(92, bandWidth.value * 0.48))
const capWidth = computed(() => Math.min(34, boxWidth.value * 0.48))

function x(index: number) {
  return plotLeft + bandWidth.value * (index + 0.5)
}

function animatedY(value: number, center: number) {
  return y(center) + (y(value) - y(center)) * progress.value
}

function formatTick(value: number) {
  const step = scale.value.step
  const decimals = step >= 1 ? 0 : Math.min(3, Math.max(0, Math.ceil(-Math.log10(step))))
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${props.unit}`
}

const titleId = `boxplot-title-${Math.random().toString(36).slice(2, 9)}`
const descId = `boxplot-desc-${Math.random().toString(36).slice(2, 9)}`
</script>

<template>
  <div class="box-plot">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-labelledby="`${titleId} ${descId}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <title :id="titleId">{{ title }}</title>
      <desc :id="descId">
        Box-and-whisker plot comparing {{ summaries.length }} groups on a shared value axis.
      </desc>

      <text class="chart-title" :x="plotLeft" y="25">{{ title }}</text>

      <g aria-hidden="true">
        <g v-for="tick in ticks" :key="tick">
          <line
            class="grid"
            :x1="plotLeft"
            :x2="plotRight"
            :y1="y(tick)"
            :y2="y(tick)"
          />
          <text
            class="tick numeric"
            :x="plotLeft - 12"
            :y="y(tick) + 4"
            text-anchor="end"
          >{{ formatTick(tick) }}</text>
        </g>

        <line class="axis" :x1="plotLeft" :x2="plotLeft" :y1="plotTop" :y2="plotBottom" />

        <text
          class="axis-label"
          :transform="`translate(24 ${(plotTop + plotBottom) / 2}) rotate(-90)`"
          text-anchor="middle"
        >{{ yLabel }}</text>
      </g>

      <g
        v-for="(group, index) in summaries"
        :key="`${group.label}-${index}`"
        class="group"
      >
        <line
          class="whisker"
          :x1="x(index)"
          :x2="x(index)"
          :y1="animatedY(group.max, group.median)"
          :y2="animatedY(group.q3, group.median)"
        />
        <line
          class="whisker"
          :x1="x(index)"
          :x2="x(index)"
          :y1="animatedY(group.q1, group.median)"
          :y2="animatedY(group.min, group.median)"
        />
        <line
          class="whisker"
          :x1="x(index) - capWidth / 2"
          :x2="x(index) + capWidth / 2"
          :y1="animatedY(group.min, group.median)"
          :y2="animatedY(group.min, group.median)"
        />
        <line
          class="whisker"
          :x1="x(index) - capWidth / 2"
          :x2="x(index) + capWidth / 2"
          :y1="animatedY(group.max, group.median)"
          :y2="animatedY(group.max, group.median)"
        />

        <rect
          class="box"
          :x="x(index) - boxWidth / 2"
          :y="Math.min(animatedY(group.q1, group.median), animatedY(group.q3, group.median))"
          :width="boxWidth"
          :height="Math.max(1, Math.abs(animatedY(group.q1, group.median) - animatedY(group.q3, group.median)))"
          rx="2"
        />
        <line
          class="median"
          :x1="x(index) - boxWidth / 2"
          :x2="x(index) + boxWidth / 2"
          :y1="y(group.median)"
          :y2="y(group.median)"
          :style="{ opacity: progress }"
        />

        <circle
          v-for="(outlier, outlierIndex) in group.outliers"
          :key="`${outlier}-${outlierIndex}`"
          class="outlier"
          :cx="x(index)"
          :cy="animatedY(outlier, group.median)"
          r="3.5"
          :style="{ opacity: progress }"
        />

        <text
          class="group-label"
          :x="x(index)"
          :y="plotBottom + 28"
          text-anchor="middle"
        >{{ group.label }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.box-plot {
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
  font-size: 15px;
  font-weight: 650;
}

.grid {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.axis {
  stroke: #5A6472;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.tick,
.axis-label,
.group-label {
  fill: #5A6472;
  font-size: 13px;
}

.axis-label {
  font-weight: 600;
}

.group-label {
  fill: #1C2530;
  font-size: 14px;
  font-weight: 600;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.whisker {
  stroke: #1D3E5E;
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.box {
  fill: #28527A;
  fill-opacity: 0.85;
  stroke: #1D3E5E;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.median {
  stroke: #FFFFFF;
  stroke-width: 2.5;
  vector-effect: non-scaling-stroke;
}

.outlier {
  fill: #28527A;
  stroke: #FFFFFF;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
</style>
