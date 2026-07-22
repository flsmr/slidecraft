<catalog>
use: Comparing a single value across categories (e.g. quarterly totals).
looks: Vertical bars growing from a baseline, one per category, value labels on the bars.
fill: prop-only; :data=[[label, value], …].
</catalog>
<!-- BarChart: reusable, on-style bar chart for slidev-theme-general.
     Data in, geometry + palette + labels owned by the component, so every chart
     is on-style by construction. Bars grow smoothly from the baseline when the
     slide becomes active (respects prefers-reduced-motion).

     Usage (inside a ::figure:: slot or anywhere in a slide):
       <BarChart :data="[['Q1',21],['Q2',35],['Q3',50],['Q4',64]]" unit="%" title="Adoption by quarter" />
     data: Array of [label, value] pairs OR { label, value } objects.
     Props: unit (suffix on value labels), max (fixed y-max), title (optional heading). -->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const props = defineProps({
  data:  { type: Array, required: true },
  unit:  { type: String, default: '' },
  max:   { type: Number, default: 0 },
  title: { type: String, default: '' },
})

// geometry (SVG user units; the SVG scales to its container width)
const W = 560, H = 340, padL = 24, padR = 20, padB = 40
const padT = computed(() => (props.title ? 54 : 34))
const baseY = H - padB

const rows = computed(() => props.data.map(d =>
  Array.isArray(d) ? { label: String(d[0]), value: +d[1] } : { label: String(d.label), value: +d.value }))

function niceMax(v) {
  const p = Math.pow(10, Math.floor(Math.log10(v)))
  const f = v / p
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p
}
const maxVal = computed(() => props.max || niceMax(Math.max(...rows.value.map(r => r.value), 1)))
const band = computed(() => (W - padL - padR) / rows.value.length)
const barW = computed(() => Math.min(74, band.value * 0.52))
const bars = computed(() => rows.value.map((r, i) => ({
  ...r,
  cx: padL + band.value * (i + 0.5),
  full: (r.value / maxVal.value) * (baseY - padT.value),
})))

// enter animation
const progress = ref(0)
const { currentPage } = useNav()
const ctx = useSlideContext()
const reduced = typeof window !== 'undefined' && window.matchMedia
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf
function animate() {
  if (reduced) { progress.value = 1; return }
  cancelAnimationFrame(raf)
  const dur = 700, start = performance.now()
  const step = (t) => {
    const p = Math.min(1, (t - start) / dur)
    progress.value = 1 - Math.pow(1 - p, 3)   // easeOutCubic
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}
// Animate on mount (covers first render + static export) and again whenever the
// slide is (re-)entered during a live presentation.
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) })
watch(() => currentPage.value === unref(ctx.$page), (active, was) => { if (active && !was) animate() })
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <svg class="gen-chart" :viewBox="`0 0 ${W} ${H}`" xmlns="http://www.w3.org/2000/svg" role="img">
    <text v-if="title" :x="padL - 4" y="26" class="gen-chart__title">{{ title }}<tspan v-if="unit"> ({{ unit }})</tspan></text>
    <line :x1="padL - 4" :y1="baseY" :x2="W - padR" :y2="baseY" stroke="#DFE3E8" stroke-width="1.5" />
    <g v-for="b in bars" :key="b.label">
      <rect :x="b.cx - barW / 2" :y="baseY - b.full * progress" :width="barW" :height="b.full * progress" fill="#28527A" />
      <text :x="b.cx" :y="baseY - b.full * progress - 8" text-anchor="middle" class="gen-chart__val" :style="{ opacity: progress }">{{ b.value }}{{ unit }}</text>
      <text :x="b.cx" :y="baseY + 22" text-anchor="middle" class="gen-chart__lbl">{{ b.label }}</text>
    </g>
  </svg>
</template>

<style scoped>
.gen-chart { width: 100%; height: auto; display: block; font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.gen-chart__title { font-size: 15px; font-weight: 600; fill: #1C2530; }
.gen-chart__val { font-size: 14px; font-weight: 600; fill: #1C2530; font-variant-numeric: tabular-nums; }
.gen-chart__lbl { font-size: 13px; fill: #5A6472; }
</style>
