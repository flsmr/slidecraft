<catalog>
use: Showing the trend and relative contribution of multiple series over an ordered axis.
looks: Filled areas beneath lines across shared x-labels, stacked or overlapping.
fill: prop-only; :x-labels=[…], :series=[{name, values:[…]}].
</catalog>
<!--
AreaChart.vue

Props:
- series: Array<{ name: string; color?: string; values: number[] }>
- xLabels: Shared categorical x-axis labels.
- stacked: Stack series when true; overlap translucent areas when false.
- unit: Suffix appended to y-axis values.
- title: Accessible chart title.
- max: Optional explicit y-axis maximum.
- animate: Enable the subtle enter animation.

Example:
<AreaChart
  title="Quarterly demand"
  unit="k"
  :x-labels="['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']"
  :series="[
    { name: 'Core', values: [18, 24, 22, 31, 35, 39] },
    { name: 'Growth', values: [9, 12, 15, 17, 21, 24] },
    { name: 'New', values: [4, 6, 8, 11, 13, 16] }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type AreaSeries = {
  name: string
  color?: string
  values: number[]
}

const props = defineProps({
  series: {
    type: Array as () => AreaSeries[],
    default: () => [
      { name: 'Core', values: [18, 24, 22, 31, 35, 39] },
      { name: 'Growth', values: [9, 12, 15, 17, 21, 24] },
      { name: 'New', values: [4, 6, 8, 11, 13, 16] },
    ],
  },
  xLabels: {
    type: Array as () => string[],
    default: () => ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
  },
  stacked: {
    type: Boolean,
    default: true,
  },
  unit: {
    type: String,
    default: 'k',
  },
  title: {
    type: String,
    default: 'Demand by segment',
  },
  max: {
    type: Number,
    default: undefined,
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

const width = 960
const height = 500
const margin = computed(() => ({
  top: props.title ? 54 : 28,
  right: 28,
  bottom: props.series.length > 1 ? 86 : 54,
  left: 68,
}))
const plotLeft = computed(() => margin.value.left)
const plotRight = computed(() => width - margin.value.right)
const plotTop = computed(() => margin.value.top)
const plotBottom = computed(() => height - margin.value.bottom)
const plotWidth = computed(() => plotRight.value - plotLeft.value)
const plotHeight = computed(() => plotBottom.value - plotTop.value)

const colors = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const pointCount = computed(() =>
  Math.max(props.xLabels.length, ...props.series.map(s => s.values.length), 1),
)

const normalizedSeries = computed(() =>
  props.series.map((series, index) => ({
    ...series,
    color: series.color || colors[index % colors.length],
    values: Array.from(
      { length: pointCount.value },
      (_, i) => Math.max(0, Number(series.values[i]) || 0),
    ),
  })),
)

const dataMaximum = computed(() => {
  if (!normalizedSeries.value.length)
    return 1

  if (props.stacked) {
    return Math.max(
      1,
      ...Array.from({ length: pointCount.value }, (_, i) =>
        normalizedSeries.value.reduce((sum, series) => sum + series.values[i], 0),
      ),
    )
  }

  return Math.max(1, ...normalizedSeries.value.flatMap(series => series.values))
})

function niceCeil(value: number) {
  const exponent = Math.floor(Math.log10(Math.max(value, 1)))
  const magnitude = 10 ** exponent
  const normalized = value / magnitude
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return nice * magnitude
}

const yMaximum = computed(() => {
  if (typeof props.max === 'number' && Number.isFinite(props.max) && props.max > 0)
    return props.max
  return niceCeil(dataMaximum.value * 1.08)
})

const tickCount = 5
const yTicks = computed(() =>
  Array.from({ length: tickCount + 1 }, (_, i) => {
    const value = (yMaximum.value / tickCount) * i
    return {
      value,
      y: plotBottom.value - (value / yMaximum.value) * plotHeight.value,
    }
  }).reverse(),
)

function xAt(index: number) {
  return pointCount.value <= 1
    ? plotLeft.value + plotWidth.value / 2
    : plotLeft.value + (index / (pointCount.value - 1)) * plotWidth.value
}

function yAt(value: number) {
  return plotBottom.value - (value / yMaximum.value) * plotHeight.value
}

function linePath(values: number[]) {
  return values
    .map((value, index) => `${index ? 'L' : 'M'} ${xAt(index)} ${yAt(value)}`)
    .join(' ')
}

function areaPath(top: number[], bottom: number[]) {
  if (!top.length)
    return ''

  const upper = top
    .map((value, index) => `${index ? 'L' : 'M'} ${xAt(index)} ${yAt(value)}`)
    .join(' ')
  const lower = bottom
    .map((value, index) => `L ${xAt(bottom.length - 1 - index)} ${yAt(bottom[bottom.length - 1 - index])}`)
    .join(' ')

  return `${upper} ${lower} Z`
}

const areas = computed(() => {
  const cumulative = Array(pointCount.value).fill(0)

  return normalizedSeries.value.map(series => {
    const bottom = props.stacked ? [...cumulative] : Array(pointCount.value).fill(0)
    const top = series.values.map((value, index) =>
      props.stacked ? cumulative[index] + value : value,
    )

    if (props.stacked)
      top.forEach((value, index) => { cumulative[index] = value })

    return {
      ...series,
      area: areaPath(top, bottom),
      line: linePath(top),
    }
  })
})

const xItems = computed(() =>
  Array.from({ length: pointCount.value }, (_, index) => ({
    label: props.xLabels[index] ?? String(index + 1),
    x: xAt(index),
  })),
)

const legendItems = computed(() => {
  const gap = 22
  const itemWidths = normalizedSeries.value.map(series =>
    Math.max(90, series.name.length * 7.2 + 34),
  )
  const total = itemWidths.reduce((sum, value) => sum + value, 0)
    + Math.max(0, itemWidths.length - 1) * gap
  let cursor = (width - total) / 2

  return normalizedSeries.value.map((series, index) => {
    const item = { ...series, x: cursor }
    cursor += itemWidths[index] + gap
    return item
  })
})

function formatValue(value: number) {
  const rounded = Math.abs(value) >= 100
    ? Math.round(value)
    : Number(value.toFixed(value % 1 ? 1 : 0))
  return `${rounded}${props.unit}`
}

const areaTransform = computed(
  () => `translate(0 ${plotBottom.value * (1 - progress.value)}) scale(1 ${progress.value})`,
)
</script>

<template>
  <div class="area-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-labelledby="`${ctx.$page}-area-title ${ctx.$page}-area-desc`"
    >
      <title :id="`${ctx.$page}-area-title`">{{ title }}</title>
      <desc :id="`${ctx.$page}-area-desc`">
        {{ stacked ? 'Stacked' : 'Overlapping' }} area chart with
        {{ series.length }} series across {{ pointCount }} categories.
      </desc>

      <text v-if="title" class="chart-title" x="68" y="28">{{ title }}</text>

      <g class="grid">
        <g v-for="tick in yTicks" :key="tick.value">
          <line
            :x1="plotLeft"
            :x2="plotRight"
            :y1="tick.y"
            :y2="tick.y"
          />
          <text
            class="axis-value"
            :x="plotLeft - 12"
            :y="tick.y + 4"
            text-anchor="end"
          >
            {{ formatValue(tick.value) }}
          </text>
        </g>
      </g>

      <defs>
        <clipPath :id="`${ctx.$page}-area-clip`">
          <rect
            :x="plotLeft"
            :y="plotTop"
            :width="plotWidth"
            :height="plotHeight"
          />
        </clipPath>
      </defs>

      <g :clip-path="`url(#${ctx.$page}-area-clip)`">
        <g
          class="areas"
          :transform="areaTransform"
          :opacity="progress"
        >
          <g v-for="area in areas" :key="area.name">
            <path
              :d="area.area"
              :fill="area.color"
              :fill-opacity="stacked ? 0.85 : 0.45"
            />
            <path
              class="area-line"
              :d="area.line"
              :stroke="area.color"
            />
          </g>
        </g>
      </g>

      <line
        class="axis-line"
        :x1="plotLeft"
        :x2="plotRight"
        :y1="plotBottom"
        :y2="plotBottom"
      />

      <g class="x-axis">
        <text
          v-for="item in xItems"
          :key="`${item.label}-${item.x}`"
          :x="item.x"
          :y="plotBottom + 28"
          text-anchor="middle"
        >
          {{ item.label }}
        </text>
      </g>

      <g
        v-if="series.length > 1"
        class="legend"
        :transform="`translate(0 ${height - 28})`"
      >
        <g
          v-for="item in legendItems"
          :key="item.name"
          :transform="`translate(${item.x} 0)`"
        >
          <line x1="0" x2="20" y1="-4" y2="-4" :stroke="item.color" />
          <rect
            x="3"
            y="-9"
            width="14"
            height="10"
            rx="2"
            :fill="item.color"
            :fill-opacity="stacked ? 0.85 : 0.45"
          />
          <text x="28" y="0">{{ item.name }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.area-chart {
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

.grid line,
.axis-line {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.axis-value,
.x-axis text,
.legend text {
  fill: #5A6472;
  font-size: 13px;
}

.axis-value {
  font-variant-numeric: tabular-nums;
}

.area-line {
  fill: none;
  stroke-width: 2.25;
  stroke-linejoin: round;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}

.legend line {
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.legend text {
  dominant-baseline: middle;
}
</style>
