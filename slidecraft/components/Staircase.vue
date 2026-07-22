<!--
Staircase.vue
Props:
- steps: Array<{ level?: string | number, label: string, desc?: string, color?: string }>
  ordered from lowest to highest maturity.
- title?: string — optional diagram heading.
- axisLabel?: string — optional vertical-axis label.
- current?: number — zero-based index of the current level.
- animate?: boolean — enables the subtle staged reveal.

Example:
<Staircase
  title="Capability maturity"
  axis-label="Maturity"
  :current="2"
  :steps="[
    { level: 1, label: 'Initial', desc: 'Ad hoc practices' },
    { level: 2, label: 'Managed', desc: 'Repeatable delivery' },
    { level: 3, label: 'Defined', desc: 'Shared standards' },
    { level: 4, label: 'Measured', desc: 'Evidence-led control' },
    { level: 5, label: 'Optimised', desc: 'Continuous improvement' }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

type StairStep = {
  level?: string | number
  label: string
  desc?: string
  color?: string
}

const props = defineProps({
  steps: {
    type: Array as () => StairStep[],
    default: () => [
      { level: 1, label: 'Initial', desc: 'Ad hoc practices' },
      { level: 2, label: 'Managed', desc: 'Repeatable delivery' },
      { level: 3, label: 'Defined', desc: 'Shared standards' },
      { level: 4, label: 'Measured', desc: 'Evidence-led control' },
      { level: 5, label: 'Optimised', desc: 'Continuous improvement' },
    ],
  },
  title: {
    type: String,
    default: '',
  },
  axisLabel: {
    type: String,
    default: 'Maturity',
  },
  current: {
    type: Number,
    default: 2,
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
  progress.value=0
  const start = performance.now()
  const duration = 700
  const frame = (now: number) => {
    const t = Math.min(1, (now - start) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)
}
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: each top <li> is a level ("label | desc"), lowest -> highest.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    const { color, parts } = parseLabel(node.text)
    const s: StairStep = { label: parts[0] || '' }
    if (parts[1]) s.desc = parts[1]
    if (color) s.color = color
    return s
  })
}
const stepsData = computed<StairStep[]>(() => (parsed.value ? mapToShape(parsed.value) : props.steps))
const safeSteps = computed(() => stepsData.value.length ? stepsData.value : [
  { level: 1, label: 'Initial', desc: 'Starting point' },
])

const count = computed(() => safeSteps.value.length)
const viewWidth = 1000
const viewHeight = 520
const left = computed(() => props.axisLabel ? 92 : 48)
const right = 42
const top = 82
const bottom = 54
const baseY = viewHeight - bottom
const usableWidth = computed(() => viewWidth - left.value - right)
const blockWidth = computed(() => usableWidth.value / count.value)
const minHeight = 126
const maxHeight = baseY - top - 34
const heightIncrement = computed(() =>
  count.value > 1 ? (maxHeight - minHeight) / (count.value - 1) : 0,
)

const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

function stepHeight(index: number) {
  return minHeight + index * heightIncrement.value
}

function stepX(index: number) {
  return left.value + index * blockWidth.value
}

function stepY(index: number) {
  return baseY - stepHeight(index)
}

function stepColor(step: StairStep, index: number) {
  return step.color || palette[index % palette.length]
}

function staged(index: number, total = count.value + 1) {
  const span = 0.58
  const start = total > 1 ? (index / (total - 1)) * (1 - span) : 0
  return Math.max(0, Math.min(1, (progress.value - start) / span))
}

function stepStyle(index: number) {
  const p = staged(index)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 18}px) scaleY(${0.94 + p * 0.06})`,
    transformOrigin: `${stepX(index) + blockWidth.value / 2}px ${baseY}px`,
  }
}

const arrowProgress = computed(() => staged(count.value, count.value + 1))
const arrowPath = computed(() => {
  const points = safeSteps.value.map((_, index) => {
    const x = stepX(index) + blockWidth.value / 2
    const y = stepY(index) - 34
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
  })
  return points.join(' ')
})

const arrowLength = computed(() => {
  if (count.value < 2) return 1
  let length = 0
  for (let i = 1; i < count.value; i++) {
    const dx = blockWidth.value
    const dy = heightIncrement.value
    length += Math.sqrt(dx * dx + dy * dy)
  }
  return Math.max(1, length)
})
</script>

<template>
  <div class="staircase" role="img" :aria-label="title || 'Maturity staircase'">
    <div ref="src" style="display:none"><slot /></div>
    <svg
      class="diagram"
      :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker
          id="staircase-arrowhead"
          markerWidth="8"
          markerHeight="8"
          refX="6.5"
          refY="4"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 8 4 L 0 8 Z" class="arrow-head" />
        </marker>
      </defs>

      <text v-if="title" x="48" y="36" class="title">{{ title }}</text>

      <g v-if="axisLabel" class="axis">
        <line :x1="left - 24" :y1="baseY" :x2="left - 24" y2="86" />
        <path :d="`M ${left - 30} 96 L ${left - 24} 86 L ${left - 18} 96`" />
        <text
          :x="left - 52"
          :y="(baseY + 86) / 2"
          :transform="`rotate(-90 ${left - 52} ${(baseY + 86) / 2})`"
          text-anchor="middle"
        >
          {{ axisLabel }}
        </text>
      </g>

      <line
        class="baseline"
        :x1="left - 4"
        :y1="baseY + 0.5"
        :x2="viewWidth - right + 4"
        :y2="baseY + 0.5"
      />

      <g
        v-for="(step, index) in safeSteps"
        :key="`${step.level ?? index}-${step.label}`"
        class="step"
        :class="{ current: index === current }"
        :style="stepStyle(index)"
      >
        <GenBox
          :x="stepX(index) + 3"
          :y="stepY(index)"
          :w="blockWidth - 6"
          :h="stepHeight(index)"
          :accent="index === current ? '#28527A' : stepColor(step, index)"
          :fill="index === current ? '#FFFFFF' : '#F5F6F8'"
          :emphasis="index === current"
        />

        <circle
          :cx="stepX(index) + 28"
          :cy="stepY(index) + 29"
          r="15"
          class="level-badge"
        />
        <text
          :x="stepX(index) + 28"
          :y="stepY(index) + 34"
          text-anchor="middle"
          class="level"
        >
          {{ step.level ?? index + 1 }}
        </text>

        <foreignObject
          :x="stepX(index) + 17"
          :y="stepY(index) + 54"
          :width="Math.max(40, blockWidth - 34)"
          :height="Math.max(54, stepHeight(index) - 66)"
        >
          <div xmlns="http://www.w3.org/1999/xhtml" class="copy">
            <div class="label">{{ step.label }}</div>
            <div v-if="step.desc" class="desc">{{ step.desc }}</div>
          </div>
        </foreignObject>

        <g v-if="index === current" class="current-tag">
          <rect
            :x="stepX(index) + blockWidth - 72"
            :y="stepY(index) + 14"
            width="54"
            height="22"
            rx="11"
          />
          <text
            :x="stepX(index) + blockWidth - 45"
            :y="stepY(index) + 29"
            text-anchor="middle"
          >
            Current
          </text>
        </g>
      </g>

      <path
        v-if="count > 1"
        :d="arrowPath"
        class="progress-arrow"
        marker-end="url(#staircase-arrowhead)"
        :style="{
          opacity: arrowProgress,
          strokeDasharray: arrowLength,
          strokeDashoffset: arrowLength * (1 - arrowProgress),
        }"
      />
    </svg>
  </div>
</template>

<style scoped>
.staircase {
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.diagram {
  display: block;
  width: 100%;
  height: auto;
  max-width: 100%;
  overflow: visible;
}

.title {
  fill: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.baseline,
.axis line {
  fill: none;
  stroke: #DFE3E8;
  stroke-width: 1.5;
}

.axis path {
  fill: none;
  stroke: #5A6472;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.axis text {
  fill: #5A6472;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.step {
  transform-box: view-box;
}

.step-box {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1.25;
}

.step.current .step-box {
  fill: #FFFFFF;
  stroke: #28527A;
  stroke-width: 2;
}

.accent-rule {
  fill: none;
  stroke-width: 3;
  opacity: 0.78;
}

.step.current .accent-rule {
  opacity: 1;
}

.level-badge {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.step.current .level-badge {
  stroke: #28527A;
}

.level {
  fill: #5A6472;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 14px;
  font-weight: 700;
}

.step.current .level {
  fill: #28527A;
}

.copy {
  box-sizing: border-box;
  width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.label {
  font-size: 16px;
  font-weight: 700;
}

.desc {
  margin-top: 7px;
  color: #5A6472;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.35;
}

.current-tag rect {
  fill: #FFFFFF;
  stroke: #28527A;
  stroke-width: 1;
}

.current-tag text {
  fill: #28527A;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.progress-arrow {
  fill: none;
  stroke: #28527A;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.arrow-head {
  fill: #28527A;
}
</style>
