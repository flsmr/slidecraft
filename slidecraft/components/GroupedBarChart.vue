<catalog>
use: Comparing multiple series side-by-side within each category (e.g. year-over-year by quarter).
looks: Clustered vertical bars, one cluster per category, one bar per series within the cluster.
fill: prop-only; :categories=[…], :series=[{name, values:[…]}].
</catalog>
<!--
GroupedBarChart.vue

Props:
- categories: string[] — labels for each x-axis group.
- series: Array<{ name: string; color?: string; values: number[] }> — aligned values.
- unit: string — suffix shown on ticks and value labels.
- title: string — accessible chart title.
- max: number | undefined — optional y-axis maximum; otherwise calculated automatically.
- animate: boolean — enables the subtle bar reveal animation.

Example:
<GroupedBarChart
  title="Quarterly revenue"
  :categories="['Q1', 'Q2', 'Q3', 'Q4']"
  :series="[
    { name: '2023', values: [42, 55, 61, 68] },
    { name: '2024', values: [49, 63, 72, 81] }
  ]"
  unit="k"
  :max="100"
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
    default: () => ['Q1', 'Q2', 'Q3', 'Q4'],
  },
  series: {
    type: Array as () => ChartSeries[],
    default: () => [
      { name: '2023', values: [42, 55, 61, 68] },
      { name: '2024', values: [49, 63, 72, 81] },
    ],
  },
  unit: {
    type: String,
    default: 'k',
  },
  title: {
    type: String,
    default: 'Quarterly revenue',
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
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const frame=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const width = 960
const height = 500
const margin = { top: 82, right: 28, bottom: 82, left: 72 }
const plotWidth = width - margin.left - margin.right
const plotHeight = height - margin.top - margin.bottom
const baseline = margin.top + plotHeight
const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
]

const visibleSeries = computed(() => props.series.slice(0, 4))
const categoryCount = computed(() => Math.max(1, props.categories.length))
const seriesCount = computed(() => Math.max(1, visibleSeries.value.length))

const dataMaximum = computed(() => {
  const values = visibleSeries.value.flatMap(item =>
    item.values.slice(0, props.categories.length),
  )
  return Math.max(0, ...values.filter(Number.isFinite))
})

function niceCeiling(value: number) {
  if (value <= 0) return 1
  const roughStep = value / 4
  const magnitude = 10 ** Math.floor(Math.log10(roughStep))
  const normalized = roughStep / magnitude
  const niceFactor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return Math.ceil(value / (niceFactor * magnitude)) * niceFactor * magnitude
}

const yMaximum = computed(() => {
  if (Number.isFinite(props.max) && (props.max as number) > 0)
    return props.max as number
  return niceCeiling(dataMaximum.value)
})

const ticks = computed(() =>
  Array.from({ length: 5 }, (_, index) => {
    const value = yMaximum.value * index / 4
    return {
      value,
      y: baseline - (value / yMaximum.value) * plotHeight,
    }
  }).reverse(),
)

const groupWidth = computed(() => plotWidth / categoryCount.value)
const groupInnerWidth = computed(() => Math.min(groupWidth.value * 0.72, 132))
const barGap = computed(() => seriesCount.value > 1 ? Math.min(8, groupInnerWidth.value * 0.06) : 0)
const barWidth = computed(() =>
  Math.max(
    8,
    Math.min(
      42,
      (groupInnerWidth.value - barGap.value * (seriesCount.value - 1)) / seriesCount.value,
    ),
  ),
)
const clusterWidth = computed(() =>
  barWidth.value * seriesCount.value + barGap.value * (seriesCount.value - 1),
)

const bars = computed(() =>
  props.categories.flatMap((category, categoryIndex) => {
    const center = margin.left + groupWidth.value * (categoryIndex + 0.5)
    const startX = center - clusterWidth.value / 2

    return visibleSeries.value.map((item, seriesIndex) => {
      const raw = Number(item.values[categoryIndex] ?? 0)
      const value = Number.isFinite(raw) ? Math.max(0, raw) : 0
      const cappedValue = Math.min(value, yMaximum.value)
      const finalHeight = (cappedValue / yMaximum.value) * plotHeight
      const animatedHeight = finalHeight * progress.value

      return {
        key: `${category}-${item.name}-${seriesIndex}`,
        x: startX + seriesIndex * (barWidth.value + barGap.value),
        y: baseline - animatedHeight,
        width: barWidth.value,
        height: animatedHeight,
        value,
        color: item.color || palette[seriesIndex],
        labelY: Math.max(margin.top + 12, baseline - finalHeight - 8),
      }
    })
  }),
)

const categoryLabels = computed(() =>
  props.categories.map((label, index) => ({
    label,
    x: margin.left + groupWidth.value * (index + 0.5),
  })),
)

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value)
}

function formatValue(value: number) {
  return `${formatNumber(value)}${props.unit}`
}
</script>

<template>
  <div class="grouped-bar-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-labelledby="'grouped-bar-title grouped-bar-desc'"
    >
      <title id="grouped-bar-title">{{ title }}</title>
      <desc id="grouped-bar-desc">
        Grouped vertical bar chart comparing {{ visibleSeries.length }} series
        across {{ categories.length }} categories.
      </desc>

      <text class="chart-title" :x="margin.left" y="30">{{ title }}</text>

      <g
        class="legend"
        :transform="`translate(${margin.left}, 52)`"
        :style="{ opacity: progress }"
      >
        <g
          v-for="(item, index) in visibleSeries"
          :key="item.name"
          :transform="`translate(${index * 132}, 0)`"
        >
          <rect
            x="0"
            y="-9"
            width="12"
            height="12"
            rx="2"
            :fill="item.color || palette[index]"
          />
          <text x="19" y="1">{{ item.name }}</text>
        </g>
      </g>

      <g class="grid">
        <g v-for="tick in ticks" :key="tick.value">
          <line
            :x1="margin.left"
            :x2="width - margin.right"
            :y1="tick.y"
            :y2="tick.y"
            :class="{ baseline: tick.value === 0 }"
          />
          <text
            class="tick-label numeric"
            :x="margin.left - 12"
            :y="tick.y + 4"
            text-anchor="end"
          >
            {{ formatValue(tick.value) }}
          </text>
        </g>
      </g>

      <g class="bars">
        <g v-for="bar in bars" :key="bar.key">
          <rect
            :x="bar.x"
            :y="bar.y"
            :width="bar.width"
            :height="bar.height"
            :fill="bar.color"
            rx="2"
          />
          <text
            class="value-label numeric"
            :x="bar.x + bar.width / 2"
            :y="bar.labelY"
            text-anchor="middle"
            :style="{ opacity: Math.max(0, (progress - 0.55) / 0.45) }"
          >
            {{ formatValue(bar.value) }}
          </text>
        </g>
      </g>

      <g class="categories">
        <text
          v-for="item in categoryLabels"
          :key="item.label"
          class="category-label"
          :x="item.x"
          :y="baseline + 30"
          text-anchor="middle"
        >
          {{ item.label }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.grouped-bar-chart {
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

.legend {
  transition: none;
}

.legend text {
  fill: #5A6472;
  font-size: 13px;
}

.grid line {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.grid line.baseline {
  stroke: #5A6472;
}

.tick-label,
.category-label {
  fill: #5A6472;
  font-size: 13px;
}

.value-label {
  fill: #1C2530;
  font-size: 12px;
  font-weight: 600;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.bars rect {
  shape-rendering: geometricPrecision;
}
</style>
