<!--
CycleDiagram.vue

Props:
- stages: Array<{ label: string; desc?: string }> — stages arranged around the cycle.
- title?: string — optional heading above the diagram.
- centerLabel?: string — optional text displayed in the centre.
- animate: boolean — enables the subtle entrance animation.

Example:
<CycleDiagram
  title="Improvement cycle"
  center-label="Continuous improvement"
  :stages="[
    { label: 'Observe', desc: 'Gather evidence' },
    { label: 'Assess', desc: 'Find opportunities' },
    { label: 'Plan', desc: 'Set priorities' },
    { label: 'Act', desc: 'Implement changes' },
    { label: 'Review', desc: 'Measure outcomes' }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type Stage = {
  label: string
  desc?: string
}

const props = defineProps({
  stages: {
    type: Array as () => Stage[],
    default: () => [
      { label: 'Observe', desc: 'Gather evidence' },
      { label: 'Assess', desc: 'Find opportunities' },
      { label: 'Plan', desc: 'Set priorities' },
      { label: 'Act', desc: 'Implement changes' },
      { label: 'Review', desc: 'Measure outcomes' },
    ],
  },
  title: {
    type: String,
    default: '',
  },
  centerLabel: {
    type: String,
    default: 'Continuous improvement',
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
  const started = performance.now()
  const duration = 700
  const frame = (now: number) => {
    const t = Math.min(1, (now - started) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)
}

onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: each top <li> is a stage ("label | desc").
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    const { parts } = parseLabel(node.text)
    const stage: Stage = { label: parts[0] || '' }
    if (parts[1]) stage.desc = parts[1]
    return stage
  })
}
const stagesData = computed<Stage[]>(() => (parsed.value ? mapToShape(parsed.value) : props.stages))
const safeStages = computed(() => stagesData.value.filter(stage => stage?.label))
const count = computed(() => safeStages.value.length)

const cx = 400
const cy = 250
const ringRadius = 142
const labelRadius = 205
const nodeRadius = 25
const arcGap = nodeRadius / ringRadius   // arcs end exactly at the node edge (arrowhead meets node)
const palette = ['#28527A', '#B07D2B', '#3F7D74']

function point(radius: number, angle: number) {
  return {
    x: cx + Math.cos(angle) * radius,
    y: cy + Math.sin(angle) * radius,
  }
}

function angleAt(index: number) {
  return -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count.value, 1)
}

const nodes = computed(() =>
  safeStages.value.map((stage, index) => {
    const angle = angleAt(index)
    const node = point(ringRadius, angle)
    const label = point(labelRadius, angle)
    const side = Math.cos(angle)

    return {
      ...stage,
      index,
      angle,
      x: node.x,
      y: node.y,
      labelX: label.x,
      labelY: label.y,
      anchor: side > 0.22 ? 'start' : side < -0.22 ? 'end' : 'middle',
      color: '#28527A',
    }
  }),
)

const arcs = computed(() => {
  if (count.value < 2) return []

  return safeStages.value.map((_, index) => {
    const startAngle = angleAt(index) + arcGap
    const endAngle = angleAt((index + 1) % count.value) - arcGap
    let sweep = endAngle - startAngle
    if (sweep <= 0) sweep += Math.PI * 2

    const start = point(ringRadius, startAngle)
    const end = point(ringRadius, startAngle + sweep)
    const largeArc = sweep > Math.PI ? 1 : 0

    return {
      index,
      d: `M ${start.x.toFixed(2)} ${start.y.toFixed(2)}
          A ${ringRadius} ${ringRadius} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`,
    }
  })
})

function stagedValue(index: number, total: number, start = 0.08, span = 0.72) {
  if (total <= 1) return Math.max(0, Math.min(1, (progress.value - start) / span))
  const delay = start + (index / total) * 0.42
  return Math.max(0, Math.min(1, (progress.value - delay) / 0.32))
}

function nodeStyle(index: number) {
  const value = stagedValue(index, Math.max(count.value, 1))
  return {
    opacity: value,
    transform: `translate(${nodes.value[index]?.x || cx}px, ${nodes.value[index]?.y || cy}px) scale(${0.82 + value * 0.18})`,
  }
}

function labelStyle(index: number) {
  const value = stagedValue(index, Math.max(count.value, 1), 0.14, 0.7)
  return {
    opacity: value,
    transform: `translate(${nodes.value[index]?.labelX || cx}px, ${nodes.value[index]?.labelY || cy}px) translateY(${(1 - value) * 5}px)`,
  }
}

function arcStyle(index: number) {
  const value = stagedValue(index, Math.max(count.value, 1), 0.02, 0.72)
  // Solid arc (tail always connected to the arrowhead); fade in rather than draw
  // from the tail, so the resting state is never left with an undrawn tail.
  return { opacity: value }
}

const centerStyle = computed(() => {
  const value = Math.max(0, Math.min(1, (progress.value - 0.42) / 0.4))
  return {
    opacity: value,
    transform: `translate(${cx}px, ${cy}px) scale(${0.96 + value * 0.04})`,
  }
})
</script>

<template>
  <div class="cycle-diagram">
    <div ref="src" style="display:none"><slot /></div>
    <h3 v-if="title" class="cycle-title">{{ title }}</h3>

    <svg
      class="cycle-svg"
      viewBox="0 0 800 500"
      role="img"
      :aria-label="title || centerLabel || 'Cycle diagram'"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker
          id="cycle-diagram-arrow"
          markerWidth="7"
          markerHeight="7"
          refX="5.8"
          refY="3.5"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 7 3.5 L 0 7 Z" fill="#28527A" />
        </marker>
      </defs>

      <circle
        v-if="count > 1"
        class="ring-guide"
        :cx="cx"
        :cy="cy"
        :r="ringRadius"
      />

      <path
        v-for="arc in arcs"
        :key="`arc-${arc.index}`"
        class="cycle-arc"
        :d="arc.d"
        pathLength="1"
        marker-end="url(#cycle-diagram-arrow)"
        :style="arcStyle(arc.index)"
      />

      <g
        v-if="centerLabel"
        class="center-label"
        :style="centerStyle"
      >
        <circle class="center-disc" r="70" />
        <text text-anchor="middle">
          <tspan
            v-for="(line, index) in centerLabel.split(/\s+/).reduce((rows, word) => {
              const last = rows.length - 1
              if (last >= 0 && `${rows[last]} ${word}`.length <= 20) rows[last] += ` ${word}`
              else rows.push(word)
              return rows
            }, [])"
            :key="`${line}-${index}`"
            x="0"
            :dy="index === 0 ? `${-(centerLabel.split(/\s+/).length > 2 ? 7 : 0)}px` : '18px'"
          >{{ line }}</tspan>
        </text>
      </g>

      <template v-for="node in nodes" :key="`stage-${node.index}`">
        <g class="stage-node" :style="nodeStyle(node.index)">
          <circle
            class="node-disc"
            :r="nodeRadius"
            :style="{ '--node-color': node.color }"
          />
          <text class="node-number" text-anchor="middle" dominant-baseline="central">
            {{ node.index + 1 }}
          </text>
        </g>

        <g class="stage-copy" :style="labelStyle(node.index)">
          <text
            class="stage-label"
            :text-anchor="node.anchor"
            :y="node.desc ? -4 : 5"
          >
            {{ node.label }}
          </text>
          <text
            v-if="node.desc"
            class="stage-desc"
            :text-anchor="node.anchor"
            y="16"
          >
            {{ node.desc }}
          </text>
        </g>
      </template>

      <text
        v-if="count === 0"
        :x="cx"
        :y="cy"
        class="empty-label"
        text-anchor="middle"
      >
        Add stages to build the cycle
      </text>
    </svg>
  </div>
</template>

<style scoped>
.cycle-diagram {
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.cycle-title {
  margin: 0 0 0.25rem;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 1.05rem;
  font-weight: 650;
  line-height: 1.25;
  text-align: center;
}

.cycle-svg {
  display: block;
  width: 100%;
  height: auto;
  max-height: 68vh;
  overflow: visible;
}

.ring-guide {
  fill: none;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.cycle-arc {
  fill: none;
  stroke: #28527A;
  stroke-width: 2;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}

.stage-node,
.stage-copy,
.center-label {
  transform-box: fill-box;
  transform-origin: center;
}

.node-disc {
  fill: #F5F6F8;
  stroke: var(--node-color);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.node-number {
  fill: var(--node-color);
  font-size: 15px;
  font-weight: 750;
}

.stage-label {
  fill: #1C2530;
  font-size: 15px;
  font-weight: 650;
}

.stage-desc {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 400;
}

.center-disc {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.center-label text {
  fill: #5A6472;
  font-size: 14px;
  font-weight: 550;
}

.empty-label {
  fill: #5A6472;
  font-size: 14px;
}
</style>
