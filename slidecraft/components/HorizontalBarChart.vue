<catalog>
use: Ranking or comparing many categories by a single value, especially with long labels.
looks: Horizontal bars extending from a baseline, one per category, optionally sorted descending.
fill: prop-only; :data=[[label, value], …] or {label, value, color}.
</catalog>
<!--
HorizontalBarChart.vue

Props:
- data: Array of [label, value] pairs or { label, value, color? } objects.
- unit: Suffix appended to axis ticks and values.
- title: Accessible and visible chart title.
- max: Optional upper scale bound; otherwise calculated as a nice value.
- sort: Sort categories descending by value. Default false.
- baseline: Value from which bars extend. Default 0.
- animate: Enable the subtle enter animation. Default true.

Example:
<HorizontalBarChart
  title="Customer satisfaction by channel"
  :data="[
    ['Account management', 92],
    { label: 'Technical support', value: 84, color: '#3F7D74' },
    ['Implementation services', 78],
    ['Knowledge base', 71],
    ['Community forum', 63],
  ]"
  unit="%"
  :sort="true"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const props = defineProps({
  data: {
    type: Array,
    default: () => [
      ['Enterprise accounts', 92],
      ['Mid-market customers', 81],
      ['Small businesses', 69],
      ['Public sector', 57],
      ['Non-profit organisations', 43],
    ],
  },
  unit: { type: String, default: '%' },
  title: { type: String, default: 'Satisfaction by customer segment' },
  max: { type: Number, default: undefined },
  sort: { type: Boolean, default: false },
  baseline: { type: Number, default: 0 },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const frame=(now)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const width = 960
const labelGutter = 250
const right = 78
const top = 76
const bottom = 48
const rowHeight = 58
const plotLeft = labelGutter
const plotRight = width - right
const plotWidth = plotRight - plotLeft

const items = computed(() => {
  const normalized = props.data.map((item, index) => {
    if (Array.isArray(item)) {
      return {
        label: String(item[0] ?? ''),
        value: Number(item[1]) || 0,
        color: '#28527A',
        index,
      }
    }
    return {
      label: String(item?.label ?? ''),
      value: Number(item?.value) || 0,
      color: item?.color || '#28527A',
      index,
    }
  })
  return props.sort
    ? [...normalized].sort((a, b) => b.value - a.value || a.index - b.index)
    : normalized
})

const height = computed(() => top + Math.max(items.value.length, 1) * rowHeight + bottom)

function niceCeil(value) {
  if (!Number.isFinite(value) || value <= 0) return 1
  const exponent = Math.floor(Math.log10(value))
  const magnitude = 10 ** exponent
  const fraction = value / magnitude
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return niceFraction * magnitude
}

const domain = computed(() => {
  const values = items.value.map(item => item.value)
  const low = Math.min(props.baseline, ...values)
  const highData = Math.max(props.baseline, ...values)
  let high = Number.isFinite(props.max) ? props.max : niceCeil(highData)
  if (high <= low) high = low + 1
  return { low, high }
})

function xScale(value) {
  const { low, high } = domain.value
  return plotLeft + ((value - low) / (high - low)) * plotWidth
}

const baselineX = computed(() => xScale(props.baseline))

const ticks = computed(() => {
  const { low, high } = domain.value
  const count = 5
  return Array.from({ length: count + 1 }, (_, i) => {
    const value = low + ((high - low) * i) / count
    return { value, x: xScale(value) }
  })
})

const bars = computed(() => items.value.map((item, index) => {
  const targetX = xScale(item.value)
  const fullWidth = Math.abs(targetX - baselineX.value)
  const animatedWidth = fullWidth * progress.value
  const x = targetX >= baselineX.value
    ? baselineX.value
    : baselineX.value - animatedWidth
  return {
    ...item,
    y: top + index * rowHeight + 13,
    centerY: top + index * rowHeight + 27,
    x,
    width: animatedWidth,
    targetX,
    valueX: targetX >= baselineX.value
      ? Math.min(plotRight + 8, baselineX.value + animatedWidth + 9)
      : Math.max(plotLeft - 8, baselineX.value - animatedWidth - 9),
    valueAnchor: targetX >= baselineX.value ? 'start' : 'end',
  }
}))

function formatNumber(value) {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value)
}

function formatTick(value) {
  return `${formatNumber(value)}${props.unit}`
}
</script>

<template>
  <div class="horizontal-bar-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-labelledby="`${ctx.$page}-horizontal-bar-title ${ctx.$page}-horizontal-bar-desc`"
    >
      <title :id="`${ctx.$page}-horizontal-bar-title`">{{ title }}</title>
      <desc :id="`${ctx.$page}-horizontal-bar-desc`">
        Horizontal bar chart comparing {{ items.length }} categories.
      </desc>

      <text class="chart-title" x="0" y="28">{{ title }}</text>

      <g class="grid">
        <g v-for="tick in ticks" :key="tick.value">
          <line
            :x1="tick.x"
            :x2="tick.x"
            :y1="top - 8"
            :y2="height - bottom + 2"
          />
          <text
            class="tick-label numeric"
            :x="tick.x"
            :y="height - 15"
            text-anchor="middle"
          >
            {{ formatTick(tick.value) }}
          </text>
        </g>
      </g>

      <line
        class="baseline"
        :x1="baselineX"
        :x2="baselineX"
        :y1="top - 8"
        :y2="height - bottom + 2"
      />

      <g v-for="bar in bars" :key="`${bar.label}-${bar.index}`">
        <text
          class="category-label"
          :x="plotLeft - 16"
          :y="bar.centerY"
          text-anchor="end"
          dominant-baseline="middle"
        >
          {{ bar.label }}
        </text>

        <rect
          class="bar"
          :x="bar.x"
          :y="bar.y"
          :width="bar.width"
          height="28"
          rx="3"
          :fill="bar.color"
        />

        <text
          class="value-label numeric"
          :x="bar.valueX"
          :y="bar.centerY"
          :text-anchor="bar.valueAnchor"
          dominant-baseline="middle"
          :opacity="progress"
        >
          {{ formatNumber(bar.value) }}{{ unit }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.horizontal-bar-chart {
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

.grid line {
  stroke: #DFE3E8;
  stroke-width: 1;
}

.baseline {
  stroke: #5A6472;
  stroke-width: 1.25;
}

.tick-label {
  fill: #5A6472;
  font-size: 12px;
}

.category-label {
  fill: #5A6472;
  font-size: 14px;
}

.value-label {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 650;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.bar {
  shape-rendering: geometricPrecision;
}
</style>
