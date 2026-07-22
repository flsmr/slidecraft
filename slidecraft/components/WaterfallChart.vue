<!--
WaterfallChart.vue

Props:
- items: Array<{ label: string; value: number; type?: 'start' | 'delta' | 'total' }>
  Start/total values are absolute; delta values are signed changes.
- unit: Unit appended to numeric labels.
- title: Accessible chart title.
- max / min: Optional explicit y-axis bounds.
- animate: Enables the subtle enter animation.

Example:
<WaterfallChart
  title="Annual recurring revenue bridge"
  unit="M"
  :items="[
    { label: 'Start', value: 12, type: 'start' },
    { label: 'New', value: 4, type: 'delta' },
    { label: 'Expansion', value: 2, type: 'delta' },
    { label: 'Churn', value: -3, type: 'delta' },
    { label: 'Total', value: 15, type: 'total' },
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type WaterfallType = 'start' | 'delta' | 'total'
interface WaterfallItem {
  label: string
  value: number
  type?: WaterfallType
}

const props = defineProps({
  items: {
    type: Array as () => WaterfallItem[],
    default: () => [
      { label: 'Start', value: 10, type: 'start' },
      { label: 'New sales', value: 4, type: 'delta' },
      { label: 'Expansion', value: 2, type: 'delta' },
      { label: 'Churn', value: -3, type: 'delta' },
      { label: 'Total', value: 13, type: 'total' },
    ],
  },
  unit: { type: String, default: 'M' },
  title: { type: String, default: 'Revenue bridge' },
  max: { type: Number, default: undefined },
  min: { type: Number, default: undefined },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const frame=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const W = 960
const H = 500
const margin = { top: 58, right: 28, bottom: 82, left: 72 }
const plotLeft = margin.left
const plotRight = W - margin.right
const plotTop = margin.top
const plotBottom = H - margin.bottom
const plotWidth = plotRight - plotLeft
const plotHeight = plotBottom - plotTop

const normalized = computed(() => {
  let running = 0
  return props.items.map((item, index) => {
    const type: WaterfallType = item.type ?? (index === 0 ? 'start' : 'delta')
    const before = running
    let after: number

    if (type === 'delta')
      after = before + item.value
    else
      after = item.value

    running = after
    return { ...item, type, before, after }
  })
})

const extent = computed(() => {
  const values = [0]
  normalized.value.forEach((item) => {
    values.push(item.type === 'delta' ? item.before : 0)
    values.push(item.after)
  })

  let lo = props.min ?? Math.min(...values)
  let hi = props.max ?? Math.max(...values)

  if (lo === hi) {
    lo -= 1
    hi += 1
  }

  const span = hi - lo
  if (props.min === undefined) lo -= span * 0.12
  if (props.max === undefined) hi += span * 0.16

  return { min: lo, max: hi }
})

const niceStep = (span: number, target = 5) => {
  const rough = Math.max(span / target, Number.EPSILON)
  const power = 10 ** Math.floor(Math.log10(rough))
  const fraction = rough / power
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return nice * power
}

const ticks = computed(() => {
  const { min, max } = extent.value
  const step = niceStep(max - min)
  const first = Math.ceil(min / step) * step
  const result: number[] = []
  for (let value = first; value <= max + step * 0.001; value += step)
    result.push(Number(value.toPrecision(12)))
  return result
})

const y = (value: number) => {
  const { min, max } = extent.value
  return plotTop + ((max - value) / (max - min)) * plotHeight
}

const slot = computed(() => plotWidth / Math.max(normalized.value.length, 1))
const barWidth = computed(() => Math.min(92, slot.value * 0.58))

const bars = computed(() => normalized.value.map((item, index) => {
  const x = plotLeft + slot.value * index + (slot.value - barWidth.value) / 2
  const anchor = item.type === 'delta' ? item.before : 0
  const animatedValue = anchor + (item.after - anchor) * progress.value
  const yAnchor = y(anchor)
  const yValue = y(animatedValue)
  const top = Math.min(yAnchor, yValue)
  const height = Math.max(0, Math.abs(yValue - yAnchor))
  const positive = item.type !== 'delta' || item.value >= 0

  return {
    ...item,
    x,
    width: barWidth.value,
    top,
    height,
    anchor,
    animatedValue,
    positive,
    fill: item.type === 'delta'
      ? (item.value >= 0 ? '#28527A' : '#B07D2B')
      : '#1D3E5E',
  }
}))

const connectors = computed(() => bars.value.slice(0, -1).map((bar, index) => {
  const next = bars.value[index + 1]
  const level = bar.after * progress.value
  return {
    x1: bar.x + bar.width,
    x2: next.x,
    y: y(level),
  }
}))

const formatNumber = (value: number) => {
  const abs = Math.abs(value)
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: abs < 10 && !Number.isInteger(abs) ? 1 : 0,
  }).format(value)
}

const valueLabel = (item: typeof bars.value[number]) => {
  const prefix = item.type === 'delta' && item.value > 0 ? '+' : ''
  return `${prefix}${formatNumber(item.value)}${props.unit}`
}

const tickLabel = (value: number) => `${formatNumber(value)}${props.unit}`
const labelY = (item: typeof bars.value[number]) => {
  const valueY = y(item.animatedValue)
  if (item.type === 'delta' && item.value < 0)
    return Math.min(plotBottom - 5, valueY + 20)
  return Math.max(plotTop + 13, valueY - 10)
}
</script>

<template>
  <div class="waterfall-chart">
    <svg
      viewBox="0 0 960 500"
      role="img"
      :aria-labelledby="'waterfall-title waterfall-desc'"
    >
      <title id="waterfall-title">{{ title }}</title>
      <desc id="waterfall-desc">
        Waterfall chart showing an initial value, signed changes, and a final total.
      </desc>

      <text class="chart-title" :x="plotLeft" y="30">{{ title }}</text>

      <g class="grid">
        <g v-for="tick in ticks" :key="tick">
          <line
            :x1="plotLeft"
            :x2="plotRight"
            :y1="y(tick)"
            :y2="y(tick)"
          />
          <text
            class="tick-label numeric"
            :x="plotLeft - 12"
            :y="y(tick) + 4"
            text-anchor="end"
          >
            {{ tickLabel(tick) }}
          </text>
        </g>
      </g>

      <line
        v-if="extent.min <= 0 && extent.max >= 0"
        class="baseline"
        :x1="plotLeft"
        :x2="plotRight"
        :y1="y(0)"
        :y2="y(0)"
      />

      <g class="connectors" :opacity="0.35 + progress * 0.65">
        <line
          v-for="(connector, index) in connectors"
          :key="index"
          :x1="connector.x1"
          :x2="connector.x2"
          :y1="connector.y"
          :y2="connector.y"
        />
      </g>

      <g v-for="(bar, index) in bars" :key="`${bar.label}-${index}`">
        <rect
          :x="bar.x"
          :y="bar.top"
          :width="bar.width"
          :height="bar.height"
          :fill="bar.fill"
          rx="2"
        />
        <text
          class="value-label numeric"
          :class="{ negative: bar.type === 'delta' && bar.value < 0 }"
          :x="bar.x + bar.width / 2"
          :y="labelY(bar)"
          text-anchor="middle"
          :opacity="0.25 + progress * 0.75"
        >
          {{ valueLabel(bar) }}
        </text>
        <text
          class="category-label"
          :x="bar.x + bar.width / 2"
          :y="plotBottom + 30"
          text-anchor="middle"
        >
          {{ bar.label }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.waterfall-chart {
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
  vector-effect: non-scaling-stroke;
}

.baseline {
  stroke: #5A6472;
  stroke-width: 1.25;
  vector-effect: non-scaling-stroke;
}

.connectors line {
  stroke: #5A6472;
  stroke-width: 1.25;
  stroke-dasharray: 3 3;
  vector-effect: non-scaling-stroke;
}

.tick-label,
.category-label {
  fill: #5A6472;
  font-size: 13px;
}

.value-label {
  fill: #1C2530;
  font-size: 14px;
  font-weight: 650;
}

.value-label.negative {
  fill: #B07D2B;
}

.numeric {
  font-variant-numeric: tabular-nums;
}
</style>
