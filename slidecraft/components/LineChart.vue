<catalog>
use: Trends over an ordered axis (typically time), for one or more series.
looks: One or more connected lines across shared x-labels, with optional filled area and point markers.
fill: prop-only; :series=[{name, points:[[x,y], …]}] or :data=[[label,value], …] for a single series.
</catalog>
<!--
LineChart.vue

Props:
- series: Array<{ name: string; color?: string; points: [x: string | number, y: number][] }>
- data: Single-series shorthand as [label: string | number, value: number][]
- xLabels: Optional categorical x-axis labels
- unit: Suffix appended to y-axis values
- title: Optional chart title
- max / min: Optional y-axis bounds; otherwise calculated as nice bounds
- area: Draw subtle filled areas beneath lines (default false)
- dots: Draw point markers (default true)
- animate: Enable the subtle enter animation (default true)

Usage:
<LineChart
  title="Monthly recurring revenue"
  unit="k"
  :series="[
    { name: 'Actual', points: [['Jan', 18], ['Feb', 24], ['Mar', 27], ['Apr', 35]] },
    { name: 'Plan', points: [['Jan', 20], ['Feb', 22], ['Mar', 30], ['Apr', 32]] }
  ]"
  area
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type XValue = string | number
type Point = [XValue, number]
type Series = {
  name: string
  color?: string
  points: Point[]
}

const props = defineProps({
  series: {
    type: Array as () => Series[],
    default: () => [
      {
        name: 'Actual',
        points: [
          ['Jan', 18], ['Feb', 24], ['Mar', 22],
          ['Apr', 31], ['May', 36], ['Jun', 43],
        ],
      },
      {
        name: 'Plan',
        points: [
          ['Jan', 16], ['Feb', 20], ['Mar', 25],
          ['Apr', 28], ['May', 34], ['Jun', 38],
        ],
      },
    ],
  },
  data: {
    type: Array as () => Point[],
    default: () => [],
  },
  xLabels: {
    type: Array as () => XValue[],
    default: () => [],
  },
  unit: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  max: {
    type: Number,
    default: undefined,
  },
  min: {
    type: Number,
    default: undefined,
  },
  area: {
    type: Boolean,
    default: false,
  },
  dots: {
    type: Boolean,
    default: true,
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const width = 900
const height = 430
const margin = computed(() => ({
  top: props.title || normalizedSeries.value.length > 1 ? 62 : 30,
  right: 28,
  bottom: 58,
  left: 72,
}))
const plot = computed(() => ({
  x: margin.value.left,
  y: margin.value.top,
  width: width - margin.value.left - margin.value.right,
  height: height - margin.value.top - margin.value.bottom,
}))

const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const normalizedSeries = computed<Series[]>(() => {
  if (props.data.length) {
    return [{ name: 'Value', points: props.data }]
  }
  return props.series
    .filter(item => item && Array.isArray(item.points))
    .map(item => ({
      name: item.name || 'Series',
      color: item.color,
      points: item.points.filter(point =>
        Array.isArray(point)
        && point.length >= 2
        && Number.isFinite(Number(point[1])),
      ),
    }))
})

const labels = computed<XValue[]>(() => {
  if (props.xLabels.length)
    return props.xLabels

  const seen = new Set<string>()
  const result: XValue[] = []
  normalizedSeries.value.forEach(item => {
    item.points.forEach(([x]) => {
      const key = String(x)
      if (!seen.has(key)) {
        seen.add(key)
        result.push(x)
      }
    })
  })
  return result
})

function niceStep(range: number, target = 4) {
  if (!Number.isFinite(range) || range <= 0)
    return 1
  const rough = range / target
  const power = 10 ** Math.floor(Math.log10(rough))
  const fraction = rough / power
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return niceFraction * power
}

const yScale = computed(() => {
  const values = normalizedSeries.value.flatMap(item => item.points.map(point => Number(point[1])))
  const dataMin = values.length ? Math.min(...values) : 0
  const dataMax = values.length ? Math.max(...values) : 1
  const spread = Math.max(dataMax - dataMin, Math.abs(dataMax) * 0.1, 1)
  const rawMin = props.min ?? Math.min(dataMin, dataMin >= 0 ? 0 : dataMin - spread * 0.08)
  const rawMax = props.max ?? (dataMax + spread * 0.08)
  const step = niceStep(Math.max(rawMax - rawMin, 1), 4)
  let min = props.min ?? Math.floor(rawMin / step) * step
  let max = props.max ?? Math.ceil(rawMax / step) * step

  if (max <= min)
    max = min + step

  const ticks: number[] = []
  const tickStep = niceStep(max - min, 4)
  const first = Math.ceil(min / tickStep) * tickStep
  for (let value = first; value <= max + tickStep * 0.001; value += tickStep)
    ticks.push(Number(value.toPrecision(12)))

  if (!ticks.length || Math.abs(ticks[0] - min) > tickStep * 0.01)
    ticks.unshift(min)
  if (Math.abs(ticks[ticks.length - 1] - max) > tickStep * 0.01)
    ticks.push(max)

  return { min, max, ticks }
})

function xFor(value: XValue, pointIndex: number) {
  const count = Math.max(labels.value.length, 1)
  if (count === 1)
    return plot.value.x + plot.value.width / 2

  let index = labels.value.findIndex(label => String(label) === String(value))
  if (index < 0)
    index = Math.min(pointIndex, count - 1)

  return plot.value.x + (index / (count - 1)) * plot.value.width
}

function yFor(value: number) {
  const { min, max } = yScale.value
  const ratio = (Number(value) - min) / (max - min)
  return plot.value.y + plot.value.height - ratio * plot.value.height
}

function smoothPath(points: Array<{ x: number; y: number }>) {
  if (!points.length)
    return ''
  if (points.length === 1)
    return `M ${points[0].x} ${points[0].y}`

  let path = `M ${points[0].x} ${points[0].y}`
  for (let i = 1; i < points.length; i++) {
    const previous = points[i - 1]
    const current = points[i]
    const midX = (previous.x + current.x) / 2
    path += ` C ${midX} ${previous.y}, ${midX} ${current.y}, ${current.x} ${current.y}`
  }
  return path
}

const renderedSeries = computed(() =>
  normalizedSeries.value.map((item, seriesIndex) => {
    const points = item.points.map(([x, y], pointIndex) => ({
      x: xFor(x, pointIndex),
      y: yFor(Number(y)),
      value: Number(y),
      label: x,
    }))
    const linePath = smoothPath(points)
    const baseline = yFor(yScale.value.min)
    const areaPath = points.length
      ? `${linePath} L ${points[points.length - 1].x} ${baseline} L ${points[0].x} ${baseline} Z`
      : ''

    return {
      ...item,
      color: item.color || palette[seriesIndex % palette.length],
      points,
      linePath,
      areaPath,
    }
  }),
)

const clipWidth = computed(() => plot.value.width * progress.value)
const detailOpacity = computed(() => Math.max(0, Math.min(1, (progress.value - 0.62) / 0.38)))

function formatValue(value: number) {
  const magnitude = Math.abs(value)
  const maximumFractionDigits = magnitude < 10 && !Number.isInteger(value) ? 1 : 0
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits }).format(value)}${props.unit}`
}

function labelAnchor(index: number) {
  if (index === 0)
    return 'start'
  if (index === labels.value.length - 1)
    return 'end'
  return 'middle'
}
</script>

<template>
  <div class="line-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-label="title || 'Multi-series line chart'"
    >
      <title>{{ title || 'Multi-series line chart' }}</title>

      <text v-if="title" class="chart-title" x="24" y="29">
        {{ title }}
      </text>

      <g
        v-if="renderedSeries.length > 1"
        class="legend"
        :transform="`translate(${width - 28}, 25)`"
        :style="{ opacity: detailOpacity }"
      >
        <g
          v-for="(item, index) in renderedSeries"
          :key="`legend-${item.name}-${index}`"
          :transform="`translate(${-index * 128}, 0)`"
        >
          <line x1="-104" y1="0" x2="-84" y2="0" :stroke="item.color" />
          <circle cx="-94" cy="0" r="3.5" :fill="item.color" />
          <text x="-76" y="4" text-anchor="start">{{ item.name }}</text>
        </g>
      </g>

      <g class="grid">
        <g v-for="tick in yScale.ticks" :key="tick">
          <line
            :x1="plot.x"
            :x2="plot.x + plot.width"
            :y1="yFor(tick)"
            :y2="yFor(tick)"
          />
          <text
            class="number"
            :x="plot.x - 12"
            :y="yFor(tick) + 4"
            text-anchor="end"
          >
            {{ formatValue(tick) }}
          </text>
        </g>
      </g>

      <line
        class="axis"
        :x1="plot.x"
        :x2="plot.x + plot.width"
        :y1="plot.y + plot.height"
        :y2="plot.y + plot.height"
      />

      <g class="x-labels" :style="{ opacity: detailOpacity }">
        <text
          v-for="(label, index) in labels"
          :key="`${label}-${index}`"
          :x="labels.length === 1
            ? plot.x + plot.width / 2
            : plot.x + (index / (labels.length - 1)) * plot.width"
          :y="plot.y + plot.height + 31"
          :text-anchor="labelAnchor(index)"
        >
          {{ label }}
        </text>
      </g>

      <defs>
        <clipPath id="line-chart-reveal">
          <rect
            :x="plot.x"
            :y="plot.y - 8"
            :width="clipWidth"
            :height="plot.height + 16"
          />
        </clipPath>
      </defs>

      <g clip-path="url(#line-chart-reveal)">
        <path
          v-for="(item, index) in renderedSeries"
          v-show="area"
          :key="`area-${index}`"
          class="area"
          :d="item.areaPath"
          :fill="item.color"
        />
        <path
          v-for="(item, index) in renderedSeries"
          :key="`line-${index}`"
          class="series-line"
          :d="item.linePath"
          :stroke="item.color"
        />
      </g>

      <g v-if="dots" :style="{ opacity: detailOpacity }">
        <g v-for="(item, seriesIndex) in renderedSeries" :key="`dots-${seriesIndex}`">
          <circle
            v-for="(point, pointIndex) in item.points"
            :key="`dot-${seriesIndex}-${pointIndex}`"
            class="dot"
            :cx="point.x"
            :cy="point.y"
            r="4"
            :fill="item.color"
          >
            <title>{{ item.name }} — {{ point.label }}: {{ formatValue(point.value) }}</title>
          </circle>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.line-chart {
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

.grid line {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.grid text,
.x-labels text,
.legend text {
  fill: #5A6472;
  font-size: 13px;
}

.number {
  font-variant-numeric: tabular-nums;
}

.axis {
  stroke: #DFE3E8;
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.legend {
  transition: none;
}

.legend line {
  stroke-width: 2.5;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}

.area {
  opacity: 0.11;
}

.series-line {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.dot {
  stroke: #FFFFFF;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
</style>
