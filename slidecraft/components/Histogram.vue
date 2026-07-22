<catalog>
use: Showing the distribution of a single numeric variable.
looks: Adjacent vertical bars over binned x-ranges, with an optional dashed mean line.
fill: prop-only; :values=[…] (auto-binned) or :bins=[{x0, x1, count}].
</catalog>
<!--
Histogram.vue

Props:
- values: number[] — raw samples; automatically binned when `bins` is empty.
- bins: Array<{ x0: number, x1: number, count: number }> — pre-binned data; takes precedence.
- binCount: number — number of bins for raw values (default: 8).
- unit: string — suffix appended to x-axis tick values.
- title: string — chart title.
- xLabel: string — x-axis label.
- yLabel: string — y-axis label.
- mean: boolean — show a dashed mean line (default: false).
- animate: boolean — enable the subtle enter animation (default: true).

Usage:
<Histogram
  :values="[42, 47, 51, 53, 55, 58, 61, 63, 66, 69, 72]"
  :bin-count="6"
  unit=" kg"
  title="Weight distribution"
  x-label="Weight"
  y-label="Frequency"
  mean
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const props = defineProps({
  values: {
    type: Array,
    default: () => [
      42, 45, 47, 48, 49, 50, 51, 52, 52, 53,
      54, 54, 55, 55, 56, 56, 57, 57, 58, 58,
      59, 59, 60, 60, 61, 61, 62, 62, 63, 63,
      64, 65, 65, 66, 67, 68, 69, 71, 73, 76,
    ],
  },
  bins: {
    type: Array,
    default: () => [],
  },
  binCount: {
    type: Number,
    default: 8,
  },
  unit: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: 'Sample distribution',
  },
  xLabel: {
    type: String,
    default: 'Observed value',
  },
  yLabel: {
    type: String,
    default: 'Frequency',
  },
  mean: {
    type: Boolean,
    default: false,
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const width = 800
const height = 430
const margin = { top: 58, right: 28, bottom: 82, left: 76 }
const plotLeft = margin.left
const plotTop = margin.top
const plotRight = width - margin.right
const plotBottom = height - margin.bottom
const plotWidth = plotRight - plotLeft
const plotHeight = plotBottom - plotTop

const finiteValues = computed(() =>
  props.values.map(Number).filter(Number.isFinite),
)

const normalizedBins = computed(() => {
  if (props.bins.length) {
    return props.bins
      .map(bin => ({
        x0: Number(bin.x0),
        x1: Number(bin.x1),
        count: Math.max(0, Number(bin.count)),
      }))
      .filter(bin =>
        Number.isFinite(bin.x0)
        && Number.isFinite(bin.x1)
        && Number.isFinite(bin.count)
        && bin.x1 > bin.x0,
      )
      .sort((a, b) => a.x0 - b.x0)
  }

  const samples = finiteValues.value
  if (!samples.length)
    return []

  const count = Math.max(1, Math.floor(props.binCount) || 1)
  const rawMin = Math.min(...samples)
  const rawMax = Math.max(...samples)

  if (rawMin === rawMax) {
    const padding = Math.abs(rawMin) * 0.05 || 0.5
    return [{ x0: rawMin - padding, x1: rawMax + padding, count: samples.length }]
  }

  const step = (rawMax - rawMin) / count
  const result = Array.from({ length: count }, (_, index) => ({
    x0: rawMin + index * step,
    x1: index === count - 1 ? rawMax : rawMin + (index + 1) * step,
    count: 0,
  }))

  for (const value of samples) {
    const index = value === rawMax
      ? count - 1
      : Math.min(count - 1, Math.floor((value - rawMin) / step))
    result[index].count += 1
  }

  return result
})

const domain = computed(() => {
  const data = normalizedBins.value
  if (!data.length)
    return { min: 0, max: 1 }
  return {
    min: Math.min(...data.map(bin => bin.x0)),
    max: Math.max(...data.map(bin => bin.x1)),
  }
})

function niceCeil(value) {
  if (value <= 0)
    return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const nice = normalized <= 1
    ? 1
    : normalized <= 2
      ? 2
      : normalized <= 5
        ? 5
        : 10
  return nice * magnitude
}

const yMax = computed(() =>
  niceCeil(Math.max(1, ...normalizedBins.value.map(bin => bin.count))),
)

const yTicks = computed(() => {
  const target = 5
  const roughStep = yMax.value / target
  const magnitude = 10 ** Math.floor(Math.log10(roughStep || 1))
  const normalized = roughStep / magnitude
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude
  const ticks = []
  for (let value = 0; value <= yMax.value + step * 0.001; value += step)
    ticks.push(value)
  if (ticks.at(-1) < yMax.value)
    ticks.push(yMax.value)
  return ticks
})

function xScale(value) {
  const span = domain.value.max - domain.value.min || 1
  return plotLeft + ((value - domain.value.min) / span) * plotWidth
}

function yScale(value) {
  return plotBottom - (value / yMax.value) * plotHeight
}

const bars = computed(() =>
  normalizedBins.value.map((bin, index) => {
    const x = xScale(bin.x0)
    const x1 = xScale(bin.x1)
    const finalY = yScale(bin.count)
    const animatedHeight = (plotBottom - finalY) * progress.value
    return {
      ...bin,
      index,
      x: x + 1.5,
      width: Math.max(0, x1 - x - 3),
      y: plotBottom - animatedHeight,
      height: animatedHeight,
    }
  }),
)

const edgeTicks = computed(() => {
  const data = normalizedBins.value
  if (!data.length)
    return []
  return [
    { value: data[0].x0, x: xScale(data[0].x0) },
    ...data.map(bin => ({ value: bin.x1, x: xScale(bin.x1) })),
  ]
})

const decimals = computed(() => {
  const data = normalizedBins.value
  if (!data.length)
    return 0
  const smallestWidth = Math.min(...data.map(bin => bin.x1 - bin.x0))
  if (smallestWidth >= 1)
    return 0
  return Math.min(3, Math.max(1, Math.ceil(-Math.log10(smallestWidth))))
})

function formatX(value) {
  return `${Number(value.toFixed(decimals.value)).toLocaleString()}${props.unit}`
}

const meanValue = computed(() => {
  if (finiteValues.value.length) {
    return finiteValues.value.reduce((sum, value) => sum + value, 0)
      / finiteValues.value.length
  }

  const total = normalizedBins.value.reduce((sum, bin) => sum + bin.count, 0)
  if (!total)
    return null

  return normalizedBins.value.reduce(
    (sum, bin) => sum + ((bin.x0 + bin.x1) / 2) * bin.count,
    0,
  ) / total
})

const meanX = computed(() =>
  meanValue.value == null ? plotLeft : xScale(meanValue.value),
)

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const frame=(now)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))
</script>

<template>
  <div class="histogram">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-label="`${title}. Histogram of ${xLabel} by ${yLabel}.`"
    >
      <title>{{ title }}</title>
      <desc>
        Frequency histogram with {{ normalizedBins.length }} bins.
        <template v-if="mean && meanValue != null">
          Mean: {{ formatX(meanValue) }}.
        </template>
      </desc>

      <text
        v-if="title"
        class="chart-title"
        :x="plotLeft"
        y="28"
      >
        {{ title }}
      </text>

      <g class="grid">
        <g v-for="tick in yTicks" :key="tick">
          <line
            :x1="plotLeft"
            :x2="plotRight"
            :y1="yScale(tick)"
            :y2="yScale(tick)"
          />
          <text
            class="tick-label numeric"
            :x="plotLeft - 12"
            :y="yScale(tick) + 4"
            text-anchor="end"
          >
            {{ tick.toLocaleString() }}
          </text>
        </g>
      </g>

      <g class="bars">
        <rect
          v-for="bar in bars"
          :key="bar.index"
          :x="bar.x"
          :y="bar.y"
          :width="bar.width"
          :height="bar.height"
          fill="#28527A"
        />
      </g>

      <g
        v-if="mean && meanValue != null"
        class="mean"
        :opacity="progress"
      >
        <line
          :x1="meanX"
          :x2="meanX"
          :y1="plotTop"
          :y2="plotBottom"
        />
        <text
          class="mean-label numeric"
          :x="meanX"
          :y="plotTop - 10"
          text-anchor="middle"
        >
          Mean {{ formatX(meanValue) }}
        </text>
      </g>

      <line
        class="axis"
        :x1="plotLeft"
        :x2="plotRight"
        :y1="plotBottom"
        :y2="plotBottom"
      />

      <g class="x-ticks">
        <g v-for="(tick, index) in edgeTicks" :key="`${tick.value}-${index}`">
          <line
            class="tick-mark"
            :x1="tick.x"
            :x2="tick.x"
            :y1="plotBottom"
            :y2="plotBottom + 6"
          />
          <text
            class="tick-label numeric"
            :x="tick.x"
            :y="plotBottom + 23"
            text-anchor="middle"
          >
            {{ formatX(tick.value) }}
          </text>
        </g>
      </g>

      <text
        v-if="xLabel"
        class="axis-label"
        :x="plotLeft + plotWidth / 2"
        :y="height - 16"
        text-anchor="middle"
      >
        {{ xLabel }}
      </text>

      <text
        v-if="yLabel"
        class="axis-label"
        :transform="`translate(20 ${plotTop + plotHeight / 2}) rotate(-90)`"
        text-anchor="middle"
      >
        {{ yLabel }}
      </text>

      <text
        v-if="!normalizedBins.length"
        class="empty-label"
        :x="plotLeft + plotWidth / 2"
        :y="plotTop + plotHeight / 2"
        text-anchor="middle"
      >
        No data
      </text>
    </svg>
  </div>
</template>

<style scoped>
.histogram {
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
  background: #FFFFFF;
}

.chart-title {
  fill: #1C2530;
  font-size: 18px;
  font-weight: 650;
}

.grid line {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.axis,
.tick-mark {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.bars rect {
  shape-rendering: crispEdges;
}

.tick-label {
  fill: #5A6472;
  font-size: 12px;
}

.axis-label {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 550;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.mean line {
  stroke: #1D3E5E;
  stroke-width: 2;
  stroke-dasharray: 6 5;
  vector-effect: non-scaling-stroke;
}

.mean-label {
  fill: #1D3E5E;
  font-size: 12px;
  font-weight: 650;
}

.empty-label {
  fill: #5A6472;
  font-size: 14px;
}
</style>
