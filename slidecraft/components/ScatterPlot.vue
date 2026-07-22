<catalog>
use: Relating two numeric variables across individual points, optionally across series.
looks: Plotted points (optionally sized bubbles) on x/y axes, with an optional trend line per series.
fill: prop-only; :series=[{name, points:[{x, y, r, label}]}].
</catalog>
<!--
ScatterPlot.vue

Props:
- series: Array<{ name: string, color?: string, points: Array<{ x: number, y: number, r?: number, label?: string }> }>
- xLabel / yLabel: axis titles
- xUnit / yUnit: units appended to tick values
- title: accessible chart title
- xMin / xMax / yMin / yMax: optional fixed domain bounds; otherwise nice-auto
- trend: draw a least-squares trend line for each series
- animate: enable the subtle enter animation

Example:
<ScatterPlot
  title="Efficiency vs. throughput"
  x-label="Throughput"
  y-label="Efficiency"
  x-unit="k"
  y-unit="%"
  :trend="true"
  :series="[
    { name: 'Current', points: [{ x: 12, y: 58 }, { x: 24, y: 66, r: 18 }] },
    { name: 'Proposed', points: [{ x: 16, y: 68 }, { x: 30, y: 82, r: 28 }] }
  ]"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const props = defineProps({
  series: {
    type: Array,
    default: () => [
      {
        name: 'Current',
        points: [
          { x: 12, y: 48, r: 12, label: 'A' },
          { x: 18, y: 57, r: 18 },
          { x: 25, y: 54, r: 10 },
          { x: 31, y: 66, r: 24 },
          { x: 39, y: 63, r: 16 },
          { x: 47, y: 72, r: 28 },
          { x: 56, y: 75, r: 20 },
          { x: 65, y: 82, r: 32, label: 'H' },
        ],
      },
      {
        name: 'Proposed',
        points: [
          { x: 14, y: 61, r: 14 },
          { x: 22, y: 65, r: 20 },
          { x: 29, y: 72, r: 12 },
          { x: 37, y: 76, r: 26 },
          { x: 44, y: 79, r: 18 },
          { x: 52, y: 86, r: 30 },
          { x: 61, y: 88, r: 22 },
          { x: 70, y: 94, r: 34, label: 'P' },
        ],
      },
    ],
  },
  xLabel: { type: String, default: 'Throughput' },
  yLabel: { type: String, default: 'Efficiency' },
  xUnit: { type: String, default: 'k' },
  yUnit: { type: String, default: '%' },
  title: { type: String, default: 'Performance landscape' },
  xMax: { type: Number, default: undefined },
  yMax: { type: Number, default: undefined },
  xMin: { type: Number, default: undefined },
  yMin: { type: Number, default: undefined },
  trend: { type: Boolean, default: false },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const frame=(now)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const W = 960
const H = 520
const margin = computed(() => ({
  top: props.title ? 58 : 30,
  right: 34,
  bottom: 76,
  left: 88,
}))
const plot = computed(() => ({
  x: margin.value.left,
  y: margin.value.top,
  w: W - margin.value.left - margin.value.right,
  h: H - margin.value.top - margin.value.bottom,
}))

const colors = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const cleanSeries = computed(() =>
  props.series.map((s, si) => ({
    name: String(s?.name ?? `Series ${si + 1}`),
    color: s?.color || colors[si % colors.length],
    points: Array.isArray(s?.points)
      ? s.points
          .filter(p => Number.isFinite(Number(p?.x)) && Number.isFinite(Number(p?.y)))
          .map(p => ({
            x: Number(p.x),
            y: Number(p.y),
            r: Number.isFinite(Number(p.r)) ? Math.max(0, Number(p.r)) : undefined,
            label: p.label == null ? '' : String(p.label),
          }))
      : [],
  })),
)

const allPoints = computed(() => cleanSeries.value.flatMap(s => s.points))

function niceStep(span, target = 6) {
  if (!Number.isFinite(span) || span <= 0) return 1
  const rough = span / target
  const power = 10 ** Math.floor(Math.log10(rough))
  const fraction = rough / power
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return nice * power
}

function makeDomain(values, explicitMin, explicitMax) {
  let rawMin = values.length ? Math.min(...values) : 0
  let rawMax = values.length ? Math.max(...values) : 10
  if (rawMin === rawMax) {
    const pad = Math.abs(rawMin || 1) * 0.1
    rawMin -= pad
    rawMax += pad
  }

  const initialStep = niceStep(rawMax - rawMin)
  let min = explicitMin ?? Math.floor(rawMin / initialStep) * initialStep
  let max = explicitMax ?? Math.ceil(rawMax / initialStep) * initialStep

  if (min === max) max = min + initialStep
  if (min > max) [min, max] = [max, min]

  const step = niceStep(max - min)
  if (explicitMin == null) min = Math.floor(min / step) * step
  if (explicitMax == null) max = Math.ceil(max / step) * step
  return { min, max, step }
}

const xDomain = computed(() =>
  makeDomain(allPoints.value.map(p => p.x), props.xMin, props.xMax),
)
const yDomain = computed(() =>
  makeDomain(allPoints.value.map(p => p.y), props.yMin, props.yMax),
)

function ticksFor(domain) {
  const ticks = []
  const epsilon = domain.step * 1e-6
  const start = Math.ceil((domain.min - epsilon) / domain.step) * domain.step
  for (let value = start, i = 0; value <= domain.max + epsilon && i < 20; value += domain.step, i++)
    ticks.push(Number(value.toPrecision(12)))
  return ticks
}

const xTicks = computed(() => ticksFor(xDomain.value))
const yTicks = computed(() => ticksFor(yDomain.value))

function xScale(value) {
  const d = xDomain.value
  return plot.value.x + ((value - d.min) / (d.max - d.min)) * plot.value.w
}
function yScale(value) {
  const d = yDomain.value
  return plot.value.y + plot.value.h - ((value - d.min) / (d.max - d.min)) * plot.value.h
}

function decimals(step) {
  if (step >= 1) return 0
  return Math.min(4, Math.max(0, Math.ceil(-Math.log10(step))))
}
function formatTick(value, domain, unit) {
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: decimals(domain.step),
    maximumFractionDigits: decimals(domain.step),
  })}${unit}`
}

const radiusDomain = computed(() => {
  const values = allPoints.value.map(p => p.r).filter(Number.isFinite)
  if (!values.length) return null
  return { min: Math.min(...values), max: Math.max(...values) }
})
function radius(point) {
  if (!Number.isFinite(point.r) || !radiusDomain.value) return 6
  const d = radiusDomain.value
  if (d.min === d.max) return 9
  return 4.5 + Math.sqrt((point.r - d.min) / (d.max - d.min)) * 9
}

const renderedSeries = computed(() => {
  let globalIndex = 0
  const total = Math.max(1, allPoints.value.length)
  return cleanSeries.value.map(series => ({
    ...series,
    points: series.points.map(point => {
      const index = globalIndex++
      const start = (index / total) * 0.3
      const local = Math.max(0, Math.min(1, (progress.value - start) / (1 - start)))
      return {
        ...point,
        cx: xScale(point.x),
        cy: yScale(point.y),
        radius: radius(point),
        reveal: local,
      }
    }),
  }))
})

function regression(points) {
  if (points.length < 2) return null
  const n = points.length
  const meanX = points.reduce((sum, p) => sum + p.x, 0) / n
  const meanY = points.reduce((sum, p) => sum + p.y, 0) / n
  const denominator = points.reduce((sum, p) => sum + (p.x - meanX) ** 2, 0)
  if (!denominator) return null
  const slope = points.reduce((sum, p) => sum + (p.x - meanX) * (p.y - meanY), 0) / denominator
  const intercept = meanY - slope * meanX
  const xs = points.map(p => p.x)
  const x1 = Math.max(xDomain.value.min, Math.min(...xs))
  const x2 = Math.min(xDomain.value.max, Math.max(...xs))
  return {
    x1: xScale(x1),
    y1: yScale(slope * x1 + intercept),
    x2: xScale(x2),
    y2: yScale(slope * x2 + intercept),
  }
}

const trendLines = computed(() =>
  cleanSeries.value.map(series => ({
    color: series.color,
    line: regression(series.points),
  })).filter(item => item.line),
)

const trendLength = line => Math.hypot(line.x2 - line.x1, line.y2 - line.y1)
const legendX = computed(() => plot.value.x + plot.value.w)
</script>

<template>
  <div class="scatter-plot">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-labelledby="'scatter-title scatter-desc'"
      preserveAspectRatio="xMidYMid meet"
    >
      <title id="scatter-title">{{ title || 'Scatter plot' }}</title>
      <desc id="scatter-desc">
        Scatter plot with {{ cleanSeries.length }} series and {{ allPoints.length }} points.
      </desc>

      <text v-if="title" class="chart-title" :x="plot.x" y="28">{{ title }}</text>

      <g v-if="cleanSeries.length > 1" class="legend" :transform="`translate(${legendX}, 27)`">
        <g
          v-for="(item, index) in cleanSeries"
          :key="`legend-${index}`"
          :transform="`translate(${-index * 132}, 0)`"
        >
          <circle cx="-112" cy="-4" r="5" :fill="item.color" fill-opacity=".8" />
          <text x="-101" y="0" text-anchor="start">{{ item.name }}</text>
        </g>
      </g>

      <g class="grid">
        <line
          v-for="tick in yTicks"
          :key="`yg-${tick}`"
          :x1="plot.x"
          :x2="plot.x + plot.w"
          :y1="yScale(tick)"
          :y2="yScale(tick)"
        />
        <line
          v-for="tick in xTicks"
          :key="`xg-${tick}`"
          :x1="xScale(tick)"
          :x2="xScale(tick)"
          :y1="plot.y"
          :y2="plot.y + plot.h"
        />
      </g>

      <g class="axes">
        <line :x1="plot.x" :x2="plot.x" :y1="plot.y" :y2="plot.y + plot.h" />
        <line :x1="plot.x" :x2="plot.x + plot.w" :y1="plot.y + plot.h" :y2="plot.y + plot.h" />
      </g>

      <g class="tick-labels">
        <text
          v-for="tick in xTicks"
          :key="`xl-${tick}`"
          :x="xScale(tick)"
          :y="plot.y + plot.h + 24"
          text-anchor="middle"
        >{{ formatTick(tick, xDomain, xUnit) }}</text>
        <text
          v-for="tick in yTicks"
          :key="`yl-${tick}`"
          :x="plot.x - 14"
          :y="yScale(tick) + 4"
          text-anchor="end"
        >{{ formatTick(tick, yDomain, yUnit) }}</text>
      </g>

      <text
        v-if="xLabel"
        class="axis-title"
        :x="plot.x + plot.w / 2"
        :y="H - 18"
        text-anchor="middle"
      >{{ xLabel }}</text>
      <text
        v-if="yLabel"
        class="axis-title"
        :transform="`translate(24 ${plot.y + plot.h / 2}) rotate(-90)`"
        text-anchor="middle"
      >{{ yLabel }}</text>

      <g v-if="trend" class="trends">
        <line
          v-for="(item, index) in trendLines"
          :key="`trend-${index}`"
          :x1="item.line.x1"
          :y1="item.line.y1"
          :x2="item.line.x2"
          :y2="item.line.y2"
          :stroke="item.color"
          :stroke-dasharray="trendLength(item.line)"
          :stroke-dashoffset="trendLength(item.line) * (1 - progress)"
        />
      </g>

      <g v-for="(group, si) in renderedSeries" :key="`series-${si}`">
        <g v-for="(point, pi) in group.points" :key="`point-${si}-${pi}`">
          <circle
            :cx="point.cx"
            :cy="point.cy"
            :r="point.radius * point.reveal"
            :fill="group.color"
            :fill-opacity=".8 * point.reveal"
          >
            <title>
              {{ point.label || group.name }}: {{ point.x }}{{ xUnit }}, {{ point.y }}{{ yUnit }}
            </title>
          </circle>
          <text
            v-if="point.label"
            class="point-label"
            :x="point.cx"
            :y="point.cy - point.radius - 7"
            text-anchor="middle"
            :opacity="point.reveal"
          >{{ point.label }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.scatter-plot {
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
  font-size: 18px;
  font-weight: 650;
}

.legend text,
.tick-labels,
.point-label {
  fill: #5A6472;
  font-size: 12px;
}

.tick-labels {
  font-variant-numeric: tabular-nums;
}

.axis-title {
  fill: #5A6472;
  font-size: 14px;
  font-weight: 550;
}

.grid line {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.axes line {
  stroke: #5A6472;
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.trends line {
  fill: none;
  stroke-width: 2.25;
  stroke-linecap: round;
  opacity: .82;
  vector-effect: non-scaling-stroke;
}

.point-label {
  font-weight: 600;
  paint-order: stroke;
  stroke: #FFFFFF;
  stroke-width: 3px;
  stroke-linejoin: round;
}

circle {
  vector-effect: non-scaling-stroke;
}
</style>
