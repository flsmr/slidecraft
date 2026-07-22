<catalog>
use: A cross-functional process flow showing which actor or role performs each step over time.
looks: Horizontal lanes per actor with step nodes positioned by lane and time column, linked by directed arrows.
fill: prop-only; :lanes=[{label}], :steps=[{id, lane, column, label, type}], :links=[{from, to, label}].
</catalog>
<!--
Swimlane.vue

Props:
- title?: string — optional diagram heading.
- lanes: Array<{ label: string; color?: string }> — horizontal actors/roles.
- steps: Array<{
    id: string;
    lane: number | string;
    column: number;
    label: string;
    type?: 'start' | 'task' | 'decision' | 'end';
  }> — process nodes positioned by lane and time column.
- links: Array<{ from: string; to: string; label?: string }> — directed connections.
- animate: boolean — enables the subtle staged reveal.

Usage:
<Swimlane
  title="Editorial workflow"
  :lanes="[
    { label: 'Author' },
    { label: 'Editor', color: '#B07D2B' },
    { label: 'Publisher', color: '#3F7D74' }
  ]"
  :steps="[
    { id: 'draft', lane: 'Author', column: 0, label: 'Draft', type: 'start' },
    { id: 'review', lane: 'Editor', column: 1, label: 'Review', type: 'task' },
    { id: 'approve', lane: 'Editor', column: 2, label: 'Approved?', type: 'decision' },
    { id: 'revise', lane: 'Author', column: 2, label: 'Revise', type: 'task' },
    { id: 'publish', lane: 'Publisher', column: 3, label: 'Publish', type: 'end' }
  ]"
  :links="[
    { from: 'draft', to: 'review' },
    { from: 'review', to: 'approve' },
    { from: 'approve', to: 'revise', label: 'No' },
    { from: 'revise', to: 'review' },
    { from: 'approve', to: 'publish', label: 'Yes' }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type Lane = {
  label: string
  color?: string
}

type StepType = 'start' | 'task' | 'decision' | 'end'

type Step = {
  id: string
  lane: number | string
  column: number
  label: string
  type?: StepType
}

type Link = {
  from: string
  to: string
  label?: string
}

const props = withDefaults(defineProps<{
  title?: string
  lanes?: Lane[]
  steps?: Step[]
  links?: Link[]
  animate?: boolean
}>(), {
  title: 'Content approval workflow',
  lanes: () => [
    { label: 'Requester', color: '#28527A' },
    { label: 'Reviewer', color: '#B07D2B' },
    { label: 'Operations', color: '#3F7D74' },
  ],
  steps: () => [
    { id: 'request', lane: 0, column: 0, label: 'Submit request', type: 'start' },
    { id: 'check', lane: 1, column: 1, label: 'Check details', type: 'task' },
    { id: 'decision', lane: 1, column: 2, label: 'Ready?', type: 'decision' },
    { id: 'revise', lane: 0, column: 2, label: 'Revise request', type: 'task' },
    { id: 'schedule', lane: 2, column: 3, label: 'Schedule work', type: 'task' },
    { id: 'complete', lane: 2, column: 4, label: 'Complete', type: 'end' },
  ],
  links: () => [
    { from: 'request', to: 'check' },
    { from: 'check', to: 'decision' },
    { from: 'decision', to: 'revise', label: 'No' },
    { from: 'revise', to: 'check' },
    { from: 'decision', to: 'schedule', label: 'Yes' },
    { from: 'schedule', to: 'complete' },
  ],
  animate: true,
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const gutterWidth = 150
const columnWidth = 170
const laneHeight = 104
const topPadding = 18
const bottomPadding = 18
const nodeWidth = 126
const nodeHeight = 52

const laneIndex = (lane: number | string) => {
  if (typeof lane === 'number')
    return Math.max(0, Math.min(props.lanes.length - 1, lane))
  const index = props.lanes.findIndex(item => item.label === lane)
  return index < 0 ? 0 : index
}

const columnCount = computed(() =>
  Math.max(1, ...props.steps.map(step => Math.max(0, step.column) + 1)),
)

const viewWidth = computed(() => gutterWidth + columnCount.value * columnWidth)
const bodyHeight = computed(() => Math.max(1, props.lanes.length) * laneHeight)
const viewHeight = computed(() => topPadding + bodyHeight.value + bottomPadding)

const normalizedSteps = computed(() => props.steps.map((step, index) => {
  const lane = laneIndex(step.lane)
  const column = Math.max(0, step.column)
  const cx = gutterWidth + column * columnWidth + columnWidth / 2
  const cy = topPadding + lane * laneHeight + laneHeight / 2

  return {
    ...step,
    type: step.type || 'task',
    index,
    laneIndex: lane,
    column,
    cx,
    cy,
    x: cx - nodeWidth / 2,
    y: cy - nodeHeight / 2,
  }
}))

const stepMap = computed(() =>
  new Map(normalizedSteps.value.map(step => [step.id, step])),
)

const normalizedLinks = computed(() => props.links.flatMap((link, index) => {
  const from = stepMap.value.get(link.from)
  const to = stepMap.value.get(link.to)
  if (!from || !to)
    return []

  const forward = to.cx >= from.cx
  const sx = from.cx + (forward ? nodeWidth / 2 : -nodeWidth / 2)
  const sy = from.cy
  const tx = to.cx + (forward ? -nodeWidth / 2 : nodeWidth / 2)
  const ty = to.cy
  const gap = Math.abs(tx - sx)
  const bendX = forward
    ? sx + Math.max(18, gap / 2)
    : Math.max(gutterWidth + 10, Math.min(sx, tx) - 22 - (index % 2) * 8)

  const path = sy === ty
    ? `M ${sx} ${sy} H ${tx}`
    : `M ${sx} ${sy} H ${bendX} V ${ty} H ${tx}`

  return [{
    ...link,
    index,
    path,
    labelX: sy === ty ? (sx + tx) / 2 : bendX,
    labelY: sy === ty ? sy - 10 : (sy + ty) / 2 - 7,
  }]
}))

const clamp01 = (value: number) => Math.max(0, Math.min(1, value))
const phase = (start: number, end: number) =>
  clamp01((progress.value - start) / Math.max(0.001, end - start))

const laneStyle = (index: number) => {
  const count = Math.max(1, props.lanes.length)
  const start = 0.02 + (index / count) * 0.12
  const value = phase(start, start + 0.22)
  return {
    opacity: value,
    transform: `translateY(${(1 - value) * 5}px)`,
  }
}

const stepStyle = (column: number, index: number) => {
  const count = Math.max(1, columnCount.value)
  const start = 0.24 + (column / count) * 0.34 + (index % 3) * 0.012
  const value = phase(start, start + 0.22)
  return {
    opacity: value,
    transform: `translate(${(1 - value) * -5}px, ${(1 - value) * 2}px) scale(${0.985 + value * 0.015})`,
    transformOrigin: 'center',
  }
}

const linkStyle = (index: number) => {
  const count = Math.max(1, normalizedLinks.value.length)
  const start = 0.66 + (index / count) * 0.16
  const value = phase(start, start + 0.18)
  return {
    opacity: value,
    strokeDasharray: 1,
    strokeDashoffset: 1 - value,
  }
}

const linkLabelStyle = (index: number) => {
  const count = Math.max(1, normalizedLinks.value.length)
  const start = 0.72 + (index / count) * 0.15
  return { opacity: phase(start, start + 0.14) }
}

const laneColor = (index: number) =>
  props.lanes[index]?.color || '#28527A'

const nodePath = (step: typeof normalizedSteps.value[number]) => {
  const { cx, cy } = step
  const halfW = nodeWidth / 2
  const halfH = nodeHeight / 2

  if (step.type === 'decision')
    return `${cx},${cy - halfH} ${cx + halfW},${cy} ${cx},${cy + halfH} ${cx - halfW},${cy}`

  return ''
}
</script>

<template>
  <figure class="swimlane">
    <figcaption v-if="title" class="swimlane__title">
      {{ title }}
    </figcaption>

    <div class="swimlane__viewport">
      <svg
        class="swimlane__svg"
        :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
        role="img"
        :aria-label="title || 'Swimlane process diagram'"
      >
        <defs>
          <marker
            id="swimlane-arrow"
            markerWidth="7"
            markerHeight="7"
            refX="6"
            refY="3.5"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M 0 0 L 7 3.5 L 0 7 Z" class="swimlane__arrowhead" />
          </marker>
        </defs>

        <g
          v-for="(lane, index) in lanes"
          :key="`${lane.label}-${index}`"
          class="swimlane__lane"
          :style="laneStyle(index)"
        >
          <rect
            class="swimlane__band"
            :class="{ 'swimlane__band--alternate': index % 2 === 0 }"
            x="0"
            :y="topPadding + index * laneHeight"
            :width="viewWidth"
            :height="laneHeight"
          />
          <rect
            :x="0"
            :y="topPadding + index * laneHeight"
            width="4"
            :height="laneHeight"
            :fill="laneColor(index)"
          />
          <text
            class="swimlane__lane-label"
            x="18"
            :y="topPadding + index * laneHeight + laneHeight / 2"
            dominant-baseline="middle"
          >
            {{ lane.label }}
          </text>
          <line
            class="swimlane__rule"
            x1="0"
            :x2="viewWidth"
            :y1="topPadding + (index + 1) * laneHeight"
            :y2="topPadding + (index + 1) * laneHeight"
          />
        </g>

        <line
          class="swimlane__gutter-rule"
          :x1="gutterWidth"
          :x2="gutterWidth"
          :y1="topPadding"
          :y2="topPadding + bodyHeight"
        />

        <line
          v-for="column in columnCount - 1"
          :key="`column-${column}`"
          class="swimlane__column-rule"
          :x1="gutterWidth + column * columnWidth"
          :x2="gutterWidth + column * columnWidth"
          :y1="topPadding"
          :y2="topPadding + bodyHeight"
        />

        <g class="swimlane__links">
          <template v-for="link in normalizedLinks" :key="`${link.from}-${link.to}-${link.index}`">
            <path
              class="swimlane__link"
              :d="link.path"
              pathLength="1"
              marker-end="url(#swimlane-arrow)"
              :style="linkStyle(link.index)"
            />
            <g
              v-if="link.label"
              class="swimlane__link-label"
              :style="linkLabelStyle(link.index)"
            >
              <rect
                :x="link.labelX - Math.max(15, link.label.length * 4.2)"
                :y="link.labelY - 9"
                :width="Math.max(30, link.label.length * 8.4)"
                height="18"
                rx="5"
              />
              <text
                :x="link.labelX"
                :y="link.labelY + 0.5"
                text-anchor="middle"
                dominant-baseline="middle"
              >
                {{ link.label }}
              </text>
            </g>
          </template>
        </g>

        <g
          v-for="step in normalizedSteps"
          :key="step.id"
          class="swimlane__step"
          :style="stepStyle(step.column, step.index)"
        >
          <polygon
            v-if="step.type === 'decision'"
            class="swimlane__node swimlane__node--decision"
            :points="nodePath(step)"
            :style="{ stroke: laneColor(step.laneIndex) }"
          />
          <rect
            v-else
            class="swimlane__node"
            :class="{
              'swimlane__node--start': step.type === 'start',
              'swimlane__node--end': step.type === 'end'
            }"
            :x="step.x"
            :y="step.y"
            :width="nodeWidth"
            :height="nodeHeight"
            :rx="step.type === 'start' || step.type === 'end' ? nodeHeight / 2 : 8"
          />
          <rect
            v-if="step.type === 'task'"
            :x="step.x"
            :y="step.y"
            width="4"
            :height="nodeHeight"
            rx="2"
            :fill="laneColor(step.laneIndex)"
          />
          <text
            class="swimlane__step-label"
            :x="step.cx"
            :y="step.cy"
            text-anchor="middle"
            dominant-baseline="middle"
          >
            {{ step.label }}
          </text>
        </g>
      </svg>
    </div>
  </figure>
</template>

<style scoped>
.swimlane {
  width: 100%;
  max-width: 100%;
  margin: 0;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.swimlane__title {
  margin: 0 0 0.55rem;
  color: #1C2530;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.swimlane__viewport {
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-radius: 9px;
  background: #FFFFFF;
}

.swimlane__svg {
  display: block;
  width: 100%;
  height: auto;
  max-width: 100%;
}

.swimlane__band {
  fill: #FFFFFF;
}

.swimlane__band--alternate {
  fill: #F5F6F8;
}

.swimlane__rule,
.swimlane__gutter-rule {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.swimlane__column-rule {
  stroke: #DFE3E8;
  stroke-width: 1;
  stroke-dasharray: 3 5;
  opacity: 0.8;
  vector-effect: non-scaling-stroke;
}

.swimlane__lane-label {
  fill: #1C2530;
  font-size: 14px;
  font-weight: 650;
}

.swimlane__link {
  fill: none;
  stroke: #5A6472;
  stroke-width: 1.35;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.swimlane__arrowhead {
  fill: #28527A;
}

.swimlane__link-label rect {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.swimlane__link-label text {
  fill: #5A6472;
  font-size: 11px;
  font-weight: 600;
}

.swimlane__node {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.swimlane__node--start,
.swimlane__node--end {
  stroke: #28527A;
}

.swimlane__node--end {
  stroke-width: 2;
}

.swimlane__node--decision {
  stroke-width: 1.25;
}

.swimlane__step-label {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 600;
  pointer-events: none;
}
</style>
