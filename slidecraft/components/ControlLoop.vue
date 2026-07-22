<catalog>
use: A forward process chain with a feedback arrow returning from a later step to an earlier one.
looks: A left-to-right chain of nodes with a distinct curved feedback arrow looping back.
fill: bullet list; each top-level item is a node, "label | desc" (feedback from/to stay props).
</catalog>
<!--
ControlLoop.vue

A control / feedback-loop diagram: a forward chain of nodes with a distinct feedback arrow
returning from a later node to an earlier one.
(Renamed from FeedbackLoop — that name collides with the Iconify `fe` icon collection under
Slidev's icon auto-resolver.)

Props:
- nodes: Array<{ label: string; desc?: string }> — forward-path nodes.
- feedbackFrom: number — zero-based source index; defaults to the last node (-1).
- feedbackTo: number — zero-based destination index; defaults to the first node.
- feedbackLabel: string — return-arrow label.
- title?: string — optional diagram title.
- animate: boolean — enables the subtle staged reveal.

Example:
<ControlLoop
  title="Continuous improvement"
  :nodes="[
    { label: 'Plan', desc: 'Set objectives' },
    { label: 'Do', desc: 'Run the work' },
    { label: 'Measure', desc: 'Review evidence' },
    { label: 'Adjust', desc: 'Apply learning' }
  ]"
  :feedback-from="3"
  :feedback-to="0"
  feedback-label="Learning loop"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

type FeedbackNode = {
  label: string
  desc?: string
}

const props = defineProps({
  nodes: {
    type: Array as () => FeedbackNode[],
    default: () => [
      { label: 'Plan', desc: 'Set objectives' },
      { label: 'Do', desc: 'Execute the work' },
      { label: 'Measure', desc: 'Review outcomes' },
      { label: 'Adjust', desc: 'Apply learning' },
    ],
  },
  feedbackFrom: {
    type: Number,
    default: -1,
  },
  feedbackTo: {
    type: Number,
    default: 0,
  },
  feedbackLabel: {
    type: String,
    default: 'Feedback',
  },
  title: {
    type: String,
    default: '',
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const frame=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: each top <li> is a node ("label | desc"); feedback stays a prop.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    const { parts } = parseLabel(node.text)
    const n: FeedbackNode = { label: parts[0] || '' }
    if (parts[1]) n.desc = parts[1]
    return n
  })
}
const nodesData = computed<FeedbackNode[]>(() => (parsed.value ? mapToShape(parsed.value) : props.nodes))
const safeNodes = computed(() => nodesData.value.length ? nodesData.value : [{ label: 'Process' }])
const count = computed(() => safeNodes.value.length)
const fromIndex = computed(() =>
  props.feedbackFrom < 0
    ? count.value - 1
    : Math.min(count.value - 1, Math.max(0, Math.trunc(props.feedbackFrom))),
)
const toIndex = computed(() =>
  Math.min(count.value - 1, Math.max(0, Math.trunc(props.feedbackTo))),
)

const viewWidth = 1000
const nodeWidth = computed(() => {
  if (count.value === 1) return 260
  return Math.max(130, Math.min(190, (viewWidth - 100 - (count.value - 1) * 54) / count.value))
})
const gap = computed(() =>
  count.value > 1
    ? (viewWidth - 100 - count.value * nodeWidth.value) / (count.value - 1)
    : 0,
)
const nodeHeight = 104
const nodeY = 72
const centerX = (index: number) =>
  count.value === 1
    ? viewWidth / 2
    : 50 + nodeWidth.value / 2 + index * (nodeWidth.value + gap.value)
const leftX = (index: number) => centerX(index) - nodeWidth.value / 2
const rightX = (index: number) => centerX(index) + nodeWidth.value / 2

const itemPhase = (index: number) => {
  const start = count.value === 1 ? 0.08 : 0.06 + index * (0.56 / count.value)
  return Math.max(0, Math.min(1, (progress.value - start) / 0.22))
}
const connectorPhase = (index: number) => {
  const start = 0.12 + index * (0.56 / Math.max(1, count.value - 1))
  return Math.max(0, Math.min(1, (progress.value - start) / 0.18))
}
const feedbackPhase = computed(() =>
  Math.max(0, Math.min(1, (progress.value - 0.72) / 0.28)),
)

const feedbackPath = computed(() => {
  const source = fromIndex.value
  const target = toIndex.value
  const sx = centerX(source)
  const tx = centerX(target)
  const y = nodeY + nodeHeight
  const depth = 96
  if (source === target)
    return `M ${sx + 24} ${y} C ${sx + 145} ${y + depth}, ${sx - 145} ${y + depth}, ${sx - 24} ${y}`
  return `M ${sx} ${y} C ${sx} ${y + depth}, ${tx} ${y + depth}, ${tx} ${y}`
})
const feedbackLabelX = computed(() => (centerX(fromIndex.value) + centerX(toIndex.value)) / 2)
</script>

<template>
  <div class="feedback-loop">
    <div ref="src" style="display:none"><slot /></div>
    <div
      v-if="title"
      class="diagram-title"
      :style="{
        opacity: itemPhase(0),
        transform: `translateY(${(1 - itemPhase(0)) * 5}px)`,
      }"
    >
      {{ title }}
    </div>

    <svg
      class="diagram"
      viewBox="0 0 1000 310"
      role="img"
      :aria-label="title || 'Feedback loop diagram'"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker
          id="feedback-loop-forward-arrow"
          viewBox="0 0 10 10"
          refX="8.5"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" class="forward-marker" />
        </marker>
        <marker
          id="feedback-loop-return-arrow"
          viewBox="0 0 10 10"
          refX="8.5"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" class="feedback-marker" />
        </marker>
      </defs>

      <g v-for="(_, index) in safeNodes.slice(0, -1)" :key="`connector-${index}`">
        <line
          class="forward-line"
          :x1="rightX(index) + 8"
          :y1="nodeY + nodeHeight / 2"
          :x2="leftX(index + 1) - 10"
          :y2="nodeY + nodeHeight / 2"
          pathLength="1"
          marker-end="url(#feedback-loop-forward-arrow)"
          :style="{
            opacity: connectorPhase(index),
            strokeDasharray: 1,
            strokeDashoffset: 1 - connectorPhase(index),
          }"
        />
      </g>

      <g
        v-for="(node, index) in safeNodes"
        :key="`${node.label}-${index}`"
        :style="{
          opacity: itemPhase(index),
          transform: `translate(${centerX(index) * (1 - itemPhase(index)) * 0.002}px, ${(1 - itemPhase(index)) * 7}px) scale(${0.985 + itemPhase(index) * 0.015})`,
          transformOrigin: `${centerX(index)}px ${nodeY + nodeHeight / 2}px`,
        }"
      >
        <GenBox
          :x="leftX(index)"
          :y="nodeY"
          :w="nodeWidth"
          :h="nodeHeight"
          accent="#28527A"
        />
        <text
          class="node-label"
          :x="leftX(index) + 20"
          :y="node.desc ? nodeY + 39 : nodeY + 58"
        >
          {{ node.label }}
        </text>
        <foreignObject
          v-if="node.desc"
          :x="leftX(index) + 20"
          :y="nodeY + 50"
          :width="nodeWidth - 38"
          height="43"
        >
          <div xmlns="http://www.w3.org/1999/xhtml" class="node-desc">
            {{ node.desc }}
          </div>
        </foreignObject>
      </g>

      <path
        class="feedback-line"
        :d="feedbackPath"
        pathLength="1"
        marker-end="url(#feedback-loop-return-arrow)"
        :style="{
          opacity: feedbackPhase,
          strokeDasharray: 1,
          strokeDashoffset: 1 - feedbackPhase,
        }"
      />
      <g
        :style="{
          opacity: feedbackPhase,
          transform: `translateY(${(1 - feedbackPhase) * 5}px)`,
        }"
      >
        <rect
          class="feedback-label-bg"
          :x="feedbackLabelX - Math.max(48, feedbackLabel.length * 4.2)"
          y="255"
          :width="Math.max(96, feedbackLabel.length * 8.4)"
          height="28"
          rx="14"
        />
        <text class="feedback-label" :x="feedbackLabelX" y="274">
          {{ feedbackLabel }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.feedback-loop {
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.diagram-title {
  margin: 0 0 0.35rem;
  color: #1C2530;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.25;
}

.diagram {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
}

.node {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.node-accent {
  fill: none;
  stroke: #28527A;
  stroke-width: 3;
}

.node-label {
  fill: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 16px;
  font-weight: 650;
}

.node-desc {
  display: flex;
  align-items: flex-start;
  width: 100%;
  height: 100%;
  overflow: hidden;
  color: #5A6472;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 13px;
  line-height: 1.28;
}

.forward-line {
  fill: none;
  stroke: #28527A;
  stroke-width: 2;
  stroke-linecap: round;
}

.forward-marker {
  fill: #28527A;
}

.feedback-line {
  fill: none;
  stroke: #B07D2B;
  stroke-width: 2;
  stroke-linecap: round;
}

.feedback-marker {
  fill: #B07D2B;
}

.feedback-label-bg {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.feedback-label {
  fill: #B07D2B;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 13px;
  font-weight: 650;
  text-anchor: middle;
}
</style>
