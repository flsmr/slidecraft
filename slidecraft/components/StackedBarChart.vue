<!--
StackedBarChart.vue

Props:
- categories: string[] — category labels, one per vertical bar.
- series: Array<{ name: string; color?: string; values: number[] }> — stacked series.
- unit: string — suffix used in values and axis labels.
- title: string — accessible chart title.
- max?: number — optional y-axis maximum; ignored when percent is true.
- percent: boolean — normalise every stack to 100%.
- animate: boolean — enable the subtle stack-growth animation.

Usage:
<StackedBarChart
  title="Quarterly channel mix"
  :categories="['Q1', 'Q2', 'Q3', 'Q4']"
  :series="[
    { name: 'Direct', values: [42, 48, 51, 57] },
    { name: 'Partners', values: [28, 31, 35, 38] },
    { name: 'Digital', values: [18, 24, 29, 34] }
  ]"
  unit="k"
  :max="140"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type ChartSeries = {
  name: string
  color?: string
  values: number[]
}

const props = defineProps({
  categories: {
    type: Array as () => string[],
    default: () => ['North', 'South', 'East', 'West'],
  },
  series: {
    type: Array as () => ChartSeries[],
    default: () => [
      { name: 'Core', values: [42, 54, 47, 61] },
      { name: 'Growth', values: [28, 24, 36, 31] },
      { name: 'New', values: [16, 22, 19, 27] },
    ],
  },
  unit: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: 'Regional portfolio composition',
  },
  max: {
    type: Number,
    default: undefined,
  },
  percent: {
    type: Boolean,
    default: false,
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const W = 900
const H = 500
const margin = { top: 72, right: 28, bottom: 92, left: 68 }
const plotTop = margin.top
const plotBottom = H - margin.bottom
const plotHeight = plotBottom - plotTop
const plotWidth = W - margin.left - margin.right
const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const safeCategories = computed(() => props.categories.length ? props.categories : ['Category'])
const rawTotals = computed(() =>
  safeCategories.value.map((_, categoryIndex) =>
    props.series.reduce((sum, item) => sum + Math.max(0, Number(item.values[categoryIndex]) || 0), 0),
  ),
)

const niceCeil = (value: number) => {
  if (value <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  const fraction = value / power
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return nice * power
}

const domainMax = computed(() => {
  if (props.percent) return 100
  const dataMax = Math.max(0, ...rawTotals.value)
  return Math.max(1, props.max != null && props.max > 0 ? props.max : niceCeil(dataMax * 1.12))
})

const y = (value: number) => plotBottom - (value / domainMax.value) * plotHeight
const band = computed(() => plotWidth / safeCategories.value.length)
const barWidth = computed(() => Math.min(104, band.value * 0.56))

const stacks = computed(() =>
  safeCategories.value.map((category, categoryIndex) => {
    const total = rawTotals.value[categoryIndex]
    let cumulative = 0
    const segments = props.series.map((item, seriesIndex) => {
      const raw = Math.max(0, Number(item.values[categoryIndex]) || 0)
      const value = props.percent ? (total > 0 ? raw / total * 100 : 0) : raw
      const start = cumulative
      cumulative += value
      const top = y(cumulative)
      const bottom = y(start)
      return {
        name: item.name,
        raw,
        value,
        x: margin.left + categoryIndex * band.value + (band.value - barWidth.value) / 2,
        y: top,
        width: barWidth.value,
        height: Math.max(0, bottom - top),
        color: item.color || palette[seriesIndex % palette.length],
      }
    })
    return {
      category,
      total,
      x: margin.left + categoryIndex * band.value + band.value / 2,
      top: y(props.percent && total > 0 ? 100 : total),
      segments,
    }
  }),
)

const ticks = computed(() =>
  Array.from({ length: 6 }, (_, index) => {
    const value = domainMax.value * index / 5
    return { value, y: y(value) }
  }),
)

const legend = computed(() => {
  const gap = 18
  const widths = props.series.map(item => 30 + item.name.length * 7.2)
  const totalWidth = widths.reduce((sum, width) => sum + width, 0) + Math.max(0, widths.length - 1) * gap
  let cursor = (W - totalWidth) / 2
  return props.series.map((item, index) => {
    const entry = {
      name: item.name,
      color: item.color || palette[index % palette.length],
      x: cursor,
    }
    cursor += widths[index] + gap
    return entry
  })
})

const formatNumber = (value: number) =>
  Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 })

const formatValue = (value: number) =>
  props.percent ? `${formatNumber(value)}%` : `${formatNumber(value)}${props.unit}`

const formatTotal = (value: number) =>
  props.percent ? '100%' : `${formatNumber(value)}${props.unit}`

const segmentLabel = (raw: number, value: number) =>
  props.percent ? `${formatNumber(value)}%` : `${formatNumber(raw)}${props.unit}`
</script>

<template>
  <div class="stacked-bar-chart">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-labelledby="'stacked-bar-title stacked-bar-desc'"
    >
      <title id="stacked-bar-title">{{ title }}</title>
      <desc id="stacked-bar-desc">
        Vertical stacked bar chart comparing {{ categories.join(', ') }}.
      </desc>

      <text class="chart-title" x="24" y="30">{{ title }}</text>

      <g class="legend" aria-label="Legend">
        <g v-for="item in legend" :key="item.name" :transform="`translate(${item.x} 48)`">
          <rect width="12" height="12" rx="2" :fill="item.color" />
          <text x="18" y="10">{{ item.name }}</text>
        </g>
      </g>

      <g class="grid">
        <g v-for="tick in ticks" :key="tick.value">
          <line
            :x1="margin.left"
            :x2="W - margin.right"
            :y1="tick.y"
            :y2="tick.y"
          />
          <text
            class="axis-value"
            :x="margin.left - 12"
            :y="tick.y + 4"
            text-anchor="end"
          >
            {{ formatValue(tick.value) }}
          </text>
        </g>
      </g>

      <line
        class="baseline"
        :x1="margin.left"
        :x2="W - margin.right"
        :y1="plotBottom"
        :y2="plotBottom"
      />

      <g
        class="animated-stacks"
        :transform="`translate(0 ${plotBottom * (1 - progress)}) scale(1 ${progress})`"
      >
        <g v-for="stack in stacks" :key="stack.category">
          <rect
            v-for="segment in stack.segments"
            :key="segment.name"
            :x="segment.x"
            :y="segment.y"
            :width="segment.width"
            :height="segment.height"
            :fill="segment.color"
          />
        </g>
      </g>

      <g class="segment-labels" :opacity="progress">
        <template v-for="stack in stacks" :key="`labels-${stack.category}`">
          <text
            v-for="segment in stack.segments.filter(item => item.height >= 27 && item.value > 0)"
            :key="segment.name"
            class="segment-value"
            :x="segment.x + segment.width / 2"
            :y="segment.y + segment.height / 2 + 4"
            text-anchor="middle"
          >
            {{ segmentLabel(segment.raw, segment.value) }}
          </text>
        </template>
      </g>

      <g class="totals" :opacity="progress">
        <text
          v-for="stack in stacks"
          :key="`total-${stack.category}`"
          :x="stack.x"
          :y="Math.max(plotTop - 8, stack.top - 10)"
          text-anchor="middle"
        >
          {{ formatTotal(stack.total) }}
        </text>
      </g>

      <g class="categories">
        <text
          v-for="stack in stacks"
          :key="`category-${stack.category}`"
          :x="stack.x"
          :y="plotBottom + 28"
          text-anchor="middle"
        >
          {{ stack.category }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.stacked-bar-chart {
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
.categories text {
  fill: #5A6472;
  font-size: 13px;
}

.grid line {
  stroke: #DFE3E8;
  stroke-width: 1;
}

.axis-value {
  fill: #5A6472;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.baseline {
  stroke: #5A6472;
  stroke-width: 1.25;
}

.animated-stacks {
  transform-box: view-box;
}

.segment-value {
  fill: #FFFFFF;
  font-size: 12px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.totals text {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.categories text {
  font-size: 13px;
  font-weight: 550;
}
</style>
