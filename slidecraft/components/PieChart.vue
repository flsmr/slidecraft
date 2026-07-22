<catalog>
use: Showing how a whole splits into shares across a small number of categories.
looks: A donut (or full pie) with slices sized by share and a legend of percentages.
fill: prop-only; :data=[[label, value], …].
</catalog>
<!-- PieChart: reusable, on-style donut chart for slidev-theme-general.
     Slices sweep from 0 to their final fraction when the slide becomes active
     (respects prefers-reduced-motion). Palette + legend owned by the component.

     Usage (inside a ::figure:: slot or anywhere in a slide):
       <PieChart :data="[['Lecture',45],['Lab',30],['Self-study',25]]" />
     data: Array of [label, value] pairs OR { label, value } objects (any units;
     the component shows each slice's share as a percentage).
     Props: colors (override the default navy/ochre/teal palette), donut (bool). -->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

const props = defineProps({
  data:   { type: Array, required: true },
  colors: { type: Array, default: () => [] },
  donut:  { type: Boolean, default: true },
})

// On-style default palette: navy, ochre, teal, then lightened companions.
const PALETTE = ['#28527A', '#B07D2B', '#3F7D74', '#7FA8CF', '#9AA7B5', '#C9A66B']

const W = 560, H = 340
const cx = 168, cy = 170, r = 112
const sw = computed(() => (props.donut ? 46 : r))   // full pie = stroke as thick as radius

const rows = computed(() => props.data.map((d, i) => {
  const label = Array.isArray(d) ? String(d[0]) : String(d.label)
  const value = Array.isArray(d) ? +d[1] : +d.value
  return { label, value, color: (props.colors[i] || PALETTE[i % PALETTE.length]) }
}))
const total = computed(() => rows.value.reduce((s, r) => s + r.value, 0) || 1)

const slices = computed(() => {
  let acc = 0
  return rows.value.map((row) => {
    const frac = row.value / total.value
    const start = acc
    acc += frac
    return { ...row, frac, start, pct: Math.round(frac * 100) }
  })
})

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
  const dur = 750, start = performance.now()
  const step = (t) => {
    const p = Math.min(1, (t - start) / dur)
    progress.value = 1 - Math.pow(1 - p, 3)
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}
// Animate on mount (covers first render + static export) and again whenever the
// slide is (re-)entered during a live presentation.
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) })
watch(() => currentPage.value === unref(ctx.$page), (active, was) => { if (active && !was) animate() })
onBeforeUnmount(() => cancelAnimationFrame(raf))

// legend layout
const legendX = 336
const legendTop = computed(() => cy - (slices.value.length - 1) * 17)
</script>

<template>
  <svg class="gen-chart" :viewBox="`0 0 ${W} ${H}`" xmlns="http://www.w3.org/2000/svg" role="img">
    <!-- donut/pie: each slice is a circle whose stroke-dash draws its arc.
         pathLength=100 lets us treat the circumference as percentages. -->
    <g :transform="`rotate(-90 ${cx} ${cy})`">
      <circle
        v-for="s in slices"
        :key="s.label"
        :cx="cx" :cy="cy" :r="r"
        fill="none"
        :stroke="s.color"
        :stroke-width="sw"
        pathLength="100"
        :stroke-dasharray="`${Math.max(0, s.frac * 100 * progress)} 100`"
        :stroke-dashoffset="-(s.start * 100)"
      />
    </g>

    <!-- legend -->
    <g v-for="(s, i) in slices" :key="'l' + s.label" :transform="`translate(${legendX} ${legendTop + i * 34})`">
      <rect x="0" y="-11" width="14" height="14" rx="2" :fill="s.color" />
      <text x="24" y="0" class="gen-chart__lgd">{{ s.label }}</text>
      <text :x="W - legendX - 20" y="0" text-anchor="end" class="gen-chart__pct" :style="{ opacity: progress }">{{ s.pct }}%</text>
    </g>
  </svg>
</template>

<style scoped>
.gen-chart { width: 100%; height: auto; display: block; font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.gen-chart__lgd { font-size: 15px; fill: #1C2530; dominant-baseline: middle; }
.gen-chart__pct { font-size: 15px; font-weight: 600; fill: #28527A; dominant-baseline: middle; font-variant-numeric: tabular-nums; }
</style>
