<!--
SlopeChart.vue

Props:
- items: Array<{ label: string; before: number; after: number; color? }> — compared items.
- leftLabel: string — caption above the left period/state.
- rightLabel: string — caption above the right period/state.
- unit: string — suffix appended to values.
- title: string — accessible chart title.
- highlight: string — optional item label to emphasise; all others are muted.
- animate: boolean — enables the subtle enter animation.

Usage:
<SlopeChart
  title="Market share change"
  left-label="2020"
  right-label="2025"
  unit="%"
  highlight="North"
  :items="[
    { label: 'North', before: 28, after: 41 },
    { label: 'South', before: 36, after: 31 },
    { label: 'East', before: 22, after: 29 },
    { label: 'West', before: 31, after: 24 }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type SlopeItem = {
  label: string
  before: number
  after: number
  color?: string
}

const props = defineProps({
  items: {
    type: Array as () => SlopeItem[],
    default: () => [
      { label: 'Enterprise', before: 34, after: 48 },
      { label: 'Mid-market', before: 42, after: 38 },
      { label: 'Small business', before: 27, after: 35 },
      { label: 'Public sector', before: 31, after: 25 },
      { label: 'Non-profit', before: 18, after: 22 },
    ],
  },
  leftLabel: { type: String, default: '2020' },
  rightLabel: { type: String, default: '2025' },
  unit: { type: String, default: '%' },
  title: { type: String, default: 'Change by segment' },
  highlight: { type: String, default: '' },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const width = 960
const height = 500
const leftX = 250
const rightX = 710
const topY = 82
const bottomY = 442

const domain = computed(() => {
  const values = props.items.flatMap(item => [item.before, item.after]).filter(Number.isFinite)
  if (!values.length) return { min: 0, max: 1 }

  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    const padding = Math.max(Math.abs(min) * 0.1, 1)
    min -= padding
    max += padding
  } else {
    const padding = (max - min) * 0.08
    min -= padding
    max += padding
  }
  return { min, max }
})

function y(value: number) {
  const { min, max } = domain.value
  return bottomY - ((value - min) / (max - min)) * (bottomY - topY)
}

function formatValue(value: number) {
  return `${new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
  }).format(value)}${props.unit}`
}

function isHighlighted(item: SlopeItem) {
  return !props.highlight || item.label === props.highlight
}

function lineColor(item: SlopeItem) {
  if (item.color) return item.color
  return item.after >= item.before ? '#28527A' : '#B07D2B'
}

const plottedItems = computed(() =>
  props.items.map((item, index) => {
    const y1 = y(item.before)
    const y2 = y(item.after)
    const x2 = leftX + (rightX - leftX) * progress.value
    const animatedY2 = y1 + (y2 - y1) * progress.value
    const active = isHighlighted(item)

    return {
      ...item,
      key: `${item.label}-${index}`,
      y1,
      y2,
      x2,
      animatedY2,
      color: lineColor(item),
      opacity: active ? 1 : 0.24,
      strokeWidth: props.highlight && active ? 4 : 2.5,
    }
  }),
)

const dotOpacity = computed(() => Math.max(0, (progress.value - 0.72) / 0.28))
</script>

<template>
  <div class="slope-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-labelledby="'slope-title slope-desc'"
      preserveAspectRatio="xMidYMid meet"
    >
      <title id="slope-title">{{ title }}</title>
      <desc id="slope-desc">
        Slope chart comparing {{ leftLabel }} with {{ rightLabel }} for {{ items.length }} items.
      </desc>

      <text class="chart-title" x="480" y="30" text-anchor="middle">{{ title }}</text>

      <text class="period-label" :x="leftX" y="58" text-anchor="middle">{{ leftLabel }}</text>
      <text class="period-label" :x="rightX" y="58" text-anchor="middle">{{ rightLabel }}</text>

      <line class="axis" :x1="leftX" :x2="leftX" :y1="topY" :y2="bottomY" />
      <line class="axis" :x1="rightX" :x2="rightX" :y1="topY" :y2="bottomY" />

      <g
        v-for="item in plottedItems"
        :key="item.key"
        :opacity="item.opacity"
      >
        <line
          :x1="leftX"
          :y1="item.y1"
          :x2="item.x2"
          :y2="item.animatedY2"
          :stroke="item.color"
          :stroke-width="item.strokeWidth"
          stroke-linecap="round"
        />

        <circle
          :cx="leftX"
          :cy="item.y1"
          r="4.5"
          :fill="item.color"
          :opacity="dotOpacity"
        />
        <circle
          :cx="rightX"
          :cy="item.y2"
          r="4.5"
          :fill="item.color"
          :opacity="dotOpacity"
        />

        <g :opacity="dotOpacity">
          <text
            class="endpoint-label"
            :class="{ emphasized: highlight && item.label === highlight }"
            :x="leftX - 14"
            :y="item.y1 - 4"
            text-anchor="end"
          >
            {{ item.label }}
          </text>
          <text
            class="value-label"
            :x="leftX - 14"
            :y="item.y1 + 13"
            text-anchor="end"
          >
            {{ formatValue(item.before) }}
          </text>

          <text
            class="endpoint-label"
            :class="{ emphasized: highlight && item.label === highlight }"
            :x="rightX + 14"
            :y="item.y2 - 4"
            text-anchor="start"
          >
            {{ item.label }}
          </text>
          <text
            class="value-label"
            :x="rightX + 14"
            :y="item.y2 + 13"
            text-anchor="start"
          >
            {{ formatValue(item.after) }}
          </text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.slope-chart {
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

.period-label {
  fill: #5A6472;
  font-size: 14px;
  font-weight: 650;
  letter-spacing: 0.04em;
}

.axis {
  stroke: #DFE3E8;
  stroke-width: 1.5;
}

.endpoint-label {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 550;
}

.endpoint-label.emphasized {
  fill: #1C2530;
  font-weight: 700;
}

.value-label {
  fill: #1C2530;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
</style>
