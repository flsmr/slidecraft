<!--
VennDiagram.vue

Props:
- sets: Array of 2 or 3 { label: string, color?: string } set definitions.
- intersections: Optional object or array of overlap labels. Object keys: AB, AC, BC, ABC.
  Array order: 2 sets → [AB]; 3 sets → [AB, AC, BC, ABC].
- title: Optional diagram title.
- centerLabel: Optional all-sets overlap label for a 3-set diagram; overrides intersections.ABC.
- animate: Enables the subtle entrance animation.

Usage:
<VennDiagram
  title="Product strategy"
  :sets="[
    { label: 'Desirable' },
    { label: 'Feasible' },
    { label: 'Viable' }
  ]"
  :intersections="{ AB: 'Useful', AC: 'Valuable', BC: 'Practical' }"
  center-label="Innovation"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type VennSet = {
  label: string
  color?: string
}

type IntersectionMap = Partial<Record<'AB' | 'AC' | 'BC' | 'ABC', string>>

const props = defineProps({
  sets: {
    type: Array as () => VennSet[],
    default: () => [
      { label: 'Desirable' },
      { label: 'Feasible' },
      { label: 'Viable' },
    ],
  },
  intersections: {
    type: [Object, Array] as unknown as () => IntersectionMap | string[],
    default: () => ({
      AB: 'Useful',
      AC: 'Valuable',
      BC: 'Practical',
    }),
  },
  title: {
    type: String,
    default: 'The innovation sweet spot',
  },
  centerLabel: {
    type: String,
    default: 'Innovation',
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0

function animate(){
  if(!props.animate||reduced){progress.value=1;return}
  cancelAnimationFrame(raf)
  progress.value = 0
  const duration = 700
  let start = 0
  const frame = (time: number) => {
    if (!start) start = time
    const t = Math.min(1, (time - start) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)
}
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const normalizedSets = computed(() => {
  const source = props.sets.slice(0, 3)
  return source.length >= 2
    ? source
    : [
        source[0] || { label: 'Set A' },
        { label: 'Set B' },
      ]
})

const isThree = computed(() => normalizedSets.value.length === 3)

const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
]

const circles = computed(() => {
  const geometry = isThree.value
    ? [
        { cx: 260, cy: 190, r: 126 },
        { cx: 440, cy: 190, r: 126 },
        { cx: 350, cy: 330, r: 126 },
      ]
    : [
        { cx: 285, cy: 245, r: 150 },
        { cx: 415, cy: 245, r: 150 },
      ]

  return normalizedSets.value.map((set, index) => ({
    ...geometry[index],
    label: set.label,
    color: set.color || palette[index],
    index,
  }))
})

const setLabels = computed(() => isThree.value
  ? [
      { x: 176, y: 42, anchor: 'middle' },
      { x: 524, y: 42, anchor: 'middle' },
      { x: 350, y: 490, anchor: 'middle' },
    ]
  : [
      { x: 180, y: 58, anchor: 'middle' },
      { x: 520, y: 58, anchor: 'middle' },
    ],
)

const intersectionMap = computed<IntersectionMap>(() => {
  if (!Array.isArray(props.intersections))
    return props.intersections || {}

  const keys = isThree.value
    ? ['AB', 'AC', 'BC', 'ABC'] as const
    : ['AB'] as const

  return keys.reduce<IntersectionMap>((result, key, index) => {
    if (props.intersections[index]) result[key] = props.intersections[index]
    return result
  }, {})
})

const overlapLabels = computed(() => {
  if (!isThree.value) {
    return intersectionMap.value.AB
      ? [{ key: 'AB', text: intersectionMap.value.AB, x: 350, y: 250, strong: false }]
      : []
  }

  const positions = {
    AB: { x: 350, y: 148 },
    AC: { x: 282, y: 286 },
    BC: { x: 418, y: 286 },
    ABC: { x: 350, y: 238 },
  }

  const labels = (['AB', 'AC', 'BC'] as const)
    .filter(key => intersectionMap.value[key])
    .map(key => ({
      key,
      text: intersectionMap.value[key] as string,
      ...positions[key],
      strong: false,
    }))

  const center = props.centerLabel || intersectionMap.value.ABC
  if (center) {
    labels.push({
      key: 'ABC',
      text: center,
      ...positions.ABC,
      strong: true,
    })
  }

  return labels
})

function reveal(index: number, total: number, span = 0.58) {
  const delay = total <= 1 ? 0 : (index / (total - 1)) * (1 - span)
  return Math.max(0, Math.min(1, (progress.value - delay) / span))
}

function circleStyle(index: number) {
  const p = reveal(index, circles.value.length, 0.72)
  return {
    opacity: p,
    transform: `translate(${circles.value[index].cx}px, ${circles.value[index].cy}px) scale(${0.92 + p * 0.08}) translate(${-circles.value[index].cx}px, ${-circles.value[index].cy}px)`,
  }
}

function labelStyle(index: number, total: number) {
  const p = reveal(index, total, 0.48)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 5}px)`,
  }
}
</script>

<template>
  <div class="venn-diagram">
    <svg
      class="venn-svg"
      viewBox="0 0 700 520"
      role="img"
      :aria-label="title || `${normalizedSets.length}-set Venn diagram`"
      preserveAspectRatio="xMidYMid meet"
    >
      <text
        v-if="title"
        class="title"
        x="350"
        y="24"
        text-anchor="middle"
        :style="labelStyle(0, 1)"
      >
        {{ title }}
      </text>

      <g class="circle-layer">
        <circle
          v-for="circle in circles"
          :key="`circle-${circle.index}`"
          :cx="circle.cx"
          :cy="circle.cy"
          :r="circle.r"
          :fill="circle.color"
          :stroke="circle.color"
          :style="circleStyle(circle.index)"
        />
      </g>

      <g class="set-label-layer">
        <text
          v-for="(label, index) in setLabels"
          :key="`set-label-${index}`"
          class="set-label"
          :x="label.x"
          :y="label.y"
          :text-anchor="label.anchor"
          :style="labelStyle(index, setLabels.length)"
        >
          {{ normalizedSets[index].label }}
        </text>
      </g>

      <g class="intersection-layer">
        <text
          v-for="(label, index) in overlapLabels"
          :key="label.key"
          :class="['intersection-label', { strong: label.strong }]"
          :x="label.x"
          :y="label.y"
          text-anchor="middle"
          dominant-baseline="middle"
          :style="labelStyle(index, overlapLabels.length)"
        >
          {{ label.text }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.venn-diagram {
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.venn-svg {
  display: block;
  width: 100%;
  height: auto;
  max-height: 72vh;
  overflow: visible;
}

.circle-layer {
  isolation: isolate;
}

.circle-layer circle {
  fill-opacity: 0.22;
  stroke-width: 1.4;
  stroke-opacity: 0.62;
  transform-box: view-box;
  transform-origin: center;
  mix-blend-mode: multiply;
}

.title {
  fill: #1C2530;
  font-size: 18px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.set-label {
  fill: #1C2530;
  font-size: 15px;
  font-weight: 650;
}

.intersection-label {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 550;
}

.intersection-label.strong {
  fill: #1D3E5E;
  font-size: 15px;
  font-weight: 750;
}
</style>
