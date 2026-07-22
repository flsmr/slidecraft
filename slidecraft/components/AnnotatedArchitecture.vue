<!--
AnnotatedArchitecture.vue

Props:
- title?: string
- blocks: Array<{ id: string; label: string; sublabel?: string; x: number; y: number; w?: number; h?: number; color?: string }>
  Coordinates use the 0..100 architecture area; w/h are optional coordinate-space sizes.
- connections: Array<{ from: string; to: string; label?: string; dashed?: boolean }>
- annotations?: Array<{ at: string | { x: number; y: number }; text: string }>
- animate?: boolean

Usage:
<AnnotatedArchitecture
  title="Request architecture"
  :blocks="[
    { id: 'client', label: 'Client', sublabel: 'Web application', x: 4, y: 38, w: 17 },
    { id: 'api', label: 'API', sublabel: 'Gateway', x: 28, y: 38, w: 17 },
    { id: 'service', label: 'Service', sublabel: 'Business logic', x: 52, y: 38, w: 18 },
    { id: 'db', label: 'Database', sublabel: 'Primary store', x: 78, y: 38, w: 17 }
  ]"
  :connections="[
    { from: 'client', to: 'api', label: 'HTTPS' },
    { from: 'api', to: 'service', label: 'JSON' },
    { from: 'service', to: 'db', label: 'SQL' }
  ]"
  :annotations="[
    { at: 'api', text: 'Authenticates and routes incoming requests.' },
    { at: 'db', text: 'Persists authoritative application state.' }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type ArchitectureBlock = {
  id: string
  label: string
  sublabel?: string
  x: number
  y: number
  w?: number
  h?: number
  color?: string
}

type ArchitectureConnection = {
  from: string
  to: string
  label?: string
  dashed?: boolean
}

type AnnotationTarget = string | { x: number; y: number }

type ArchitectureAnnotation = {
  at: AnnotationTarget
  text: string
}

const props = defineProps({
  title: {
    type: String,
    default: 'Request architecture',
  },
  blocks: {
    type: Array as () => ArchitectureBlock[],
    default: () => [
      { id: 'client', label: 'Client', sublabel: 'Web application', x: 3, y: 38, w: 16, h: 18 },
      { id: 'api', label: 'API', sublabel: 'Gateway', x: 25, y: 38, w: 16, h: 18 },
      { id: 'service', label: 'Service', sublabel: 'Business logic', x: 48, y: 38, w: 18, h: 18 },
      { id: 'db', label: 'Database', sublabel: 'Primary store', x: 76, y: 38, w: 17, h: 18, color: '#3F7D74' },
      { id: 'cache', label: 'Cache', sublabel: 'Hot responses', x: 49, y: 72, w: 17, h: 16, color: '#B07D2B' },
    ],
  },
  connections: {
    type: Array as () => ArchitectureConnection[],
    default: () => [
      { from: 'client', to: 'api', label: 'HTTPS' },
      { from: 'api', to: 'service', label: 'JSON' },
      { from: 'service', to: 'db', label: 'SQL' },
      { from: 'service', to: 'cache', label: 'read / write', dashed: true },
    ],
  },
  annotations: {
    type: Array as () => ArchitectureAnnotation[],
    default: () => [
      { at: 'api', text: 'Validates identity, applies policy, and routes each request.' },
      { at: 'service', text: 'Keeps business rules isolated from transport and storage.' },
      { at: 'cache', text: 'Reduces repeated database reads for frequently requested data.' },
    ],
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

const architectureWidth = 720
const notesX = 770
const viewWidth = 1120
const viewHeight = 560
const plot = { x: 28, y: 72, w: 680, h: 430 }

const normalizedBlocks = computed(() =>
  props.blocks.map((block, index) => {
    const w = block.w ?? 18
    const h = block.h ?? 18
    return {
      ...block,
      index,
      w,
      h,
      px: plot.x + (block.x / 100) * plot.w,
      py: plot.y + (block.y / 100) * plot.h,
      pw: (w / 100) * plot.w,
      ph: (h / 100) * plot.h,
      accent: block.color || '#28527A',
    }
  }),
)

const blockMap = computed(() =>
  new Map(normalizedBlocks.value.map(block => [block.id, block])),
)

function staged(start: number, end: number) {
  if (end <= start) return progress.value >= end ? 1 : 0
  return Math.max(0, Math.min(1, (progress.value - start) / (end - start)))
}

function blockProgress(index: number) {
  const count = Math.max(normalizedBlocks.value.length, 1)
  const start = 0.02 + (index / count) * 0.22
  return staged(start, start + 0.34)
}

function blockStyle(index: number) {
  const p = blockProgress(index)
  return {
    opacity: p,
    transform: `translate(0 ${6 * (1 - p)}px) scale(${0.97 + p * 0.03})`,
    transformOrigin: 'center',
    transformBox: 'fill-box',
  }
}

function connectionGeometry(connection: ArchitectureConnection, index: number) {
  const from = blockMap.value.get(connection.from)
  const to = blockMap.value.get(connection.to)
  if (!from || !to) return null

  const fromCenter = { x: from.px + from.pw / 2, y: from.py + from.ph / 2 }
  const toCenter = { x: to.px + to.pw / 2, y: to.py + to.ph / 2 }
  const dx = toCenter.x - fromCenter.x
  const dy = toCenter.y - fromCenter.y

  let x1: number
  let y1: number
  let x2: number
  let y2: number

  if (Math.abs(dx) >= Math.abs(dy)) {
    x1 = dx >= 0 ? from.px + from.pw : from.px
    y1 = fromCenter.y
    x2 = dx >= 0 ? to.px : to.px + to.pw
    y2 = toCenter.y
  } else {
    x1 = fromCenter.x
    y1 = dy >= 0 ? from.py + from.ph : from.py
    x2 = toCenter.x
    y2 = dy >= 0 ? to.py : to.py + to.ph
  }

  const length = Math.hypot(x2 - x1, y2 - y1)
  const p = staged(0.28 + index * 0.045, 0.68 + index * 0.045)

  return {
    x1,
    y1,
    x2,
    y2,
    mx: (x1 + x2) / 2,
    my: (y1 + y2) / 2,
    length,
    progress: p,
  }
}

function annotationTarget(annotation: ArchitectureAnnotation) {
  if (typeof annotation.at === 'string') {
    const block = blockMap.value.get(annotation.at)
    if (!block) return { x: plot.x + plot.w / 2, y: plot.y + plot.h / 2 }
    return {
      x: block.px + block.pw - 2,
      y: block.py + 4,
    }
  }
  return {
    x: plot.x + (annotation.at.x / 100) * plot.w,
    y: plot.y + (annotation.at.y / 100) * plot.h,
  }
}

function noteY(index: number) {
  const count = Math.max(props.annotations.length, 1)
  const available = 390
  return 112 + index * Math.min(118, available / count)
}

function annotationProgress(index: number) {
  return staged(0.68 + index * 0.055, 0.94 + index * 0.035)
}

function annotationStyle(index: number) {
  const p = annotationProgress(index)
  return {
    opacity: p,
    transform: `translate(0 ${5 * (1 - p)}px)`,
  }
}

function leaderPath(annotation: ArchitectureAnnotation, index: number) {
  const target = annotationTarget(annotation)
  const endX = notesX - 22
  const endY = noteY(index) + 4
  const elbowX = architectureWidth + 18
  return `M ${target.x} ${target.y} L ${elbowX} ${target.y} L ${elbowX} ${endY} L ${endX} ${endY}`
}
</script>

<template>
  <svg
    class="annotated-architecture"
    :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
    role="img"
    :aria-label="title || 'Annotated system architecture'"
    preserveAspectRatio="xMidYMid meet"
  >
    <defs>
      <marker
        id="annotated-architecture-arrow"
        viewBox="0 0 10 10"
        refX="8.5"
        refY="5"
        markerWidth="7"
        markerHeight="7"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-head" />
      </marker>
    </defs>

    <text v-if="title" x="28" y="36" class="diagram-title">{{ title }}</text>
    <line x1="28" y1="53" x2="1092" y2="53" class="title-rule" />
    <text :x="notesX" y="88" class="notes-heading">KEY NOTES</text>
    <line :x1="notesX" y1="98" x2="1092" y2="98" class="notes-rule" />

    <g class="connections">
      <template v-for="(connection, index) in connections" :key="`${connection.from}-${connection.to}-${index}`">
        <template v-if="connectionGeometry(connection, index)">
          <line
            :x1="connectionGeometry(connection, index)!.x1"
            :y1="connectionGeometry(connection, index)!.y1"
            :x2="connectionGeometry(connection, index)!.x2"
            :y2="connectionGeometry(connection, index)!.y2"
            class="connection-line"
            :class="{ dashed: connection.dashed }"
            marker-end="url(#annotated-architecture-arrow)"
            pathLength="1"
            :style="{
              strokeDasharray: connection.dashed
                ? `${0.055 * connectionGeometry(connection, index)!.progress} ${0.035 + (1 - connectionGeometry(connection, index)!.progress)}`
                : '1',
              strokeDashoffset: 1 - connectionGeometry(connection, index)!.progress,
              opacity: connectionGeometry(connection, index)!.progress,
            }"
          />
          <g
            v-if="connection.label"
            :style="{ opacity: connectionGeometry(connection, index)!.progress }"
          >
            <rect
              :x="connectionGeometry(connection, index)!.mx - Math.max(27, connection.label.length * 3.8)"
              :y="connectionGeometry(connection, index)!.my - 12"
              :width="Math.max(54, connection.label.length * 7.6)"
              height="20"
              rx="5"
              class="connection-label-bg"
            />
            <text
              :x="connectionGeometry(connection, index)!.mx"
              :y="connectionGeometry(connection, index)!.my + 2"
              class="connection-label"
            >
              {{ connection.label }}
            </text>
          </g>
        </template>
      </template>
    </g>

    <g class="blocks">
      <g
        v-for="block in normalizedBlocks"
        :key="block.id"
        :style="blockStyle(block.index)"
      >
        <rect
          :x="block.px"
          :y="block.py"
          :width="block.pw"
          :height="block.ph"
          rx="8"
          class="block-body"
        />
        <path
          :d="`M ${block.px + 5} ${block.py + 8} L ${block.px + 5} ${block.py + block.ph - 8}`"
          :stroke="block.accent"
          class="block-accent"
        />
        <text
          :x="block.px + 18"
          :y="block.py + block.ph / 2 + (block.sublabel ? -4 : 5)"
          class="block-label"
        >
          {{ block.label }}
        </text>
        <text
          v-if="block.sublabel"
          :x="block.px + 18"
          :y="block.py + block.ph / 2 + 17"
          class="block-sublabel"
        >
          {{ block.sublabel }}
        </text>
      </g>
    </g>

    <g class="annotations">
      <template v-for="(annotation, index) in annotations" :key="index">
        <path
          :d="leaderPath(annotation, index)"
          class="leader-line"
          pathLength="1"
          :style="{
            strokeDasharray: 1,
            strokeDashoffset: 1 - annotationProgress(index),
            opacity: annotationProgress(index),
          }"
        />
        <g :style="annotationStyle(index)">
          <circle
            :cx="annotationTarget(annotation).x"
            :cy="annotationTarget(annotation).y"
            r="12"
            class="annotation-badge"
          />
          <text
            :x="annotationTarget(annotation).x"
            :y="annotationTarget(annotation).y + 4.5"
            class="annotation-number"
          >
            {{ index + 1 }}
          </text>

          <circle :cx="notesX" :cy="noteY(index)" r="13" class="note-badge" />
          <text :x="notesX" :y="noteY(index) + 4.5" class="note-number">
            {{ index + 1 }}
          </text>
          <foreignObject
            :x="notesX + 25"
            :y="noteY(index) - 17"
            width="292"
            height="78"
          >
            <div xmlns="http://www.w3.org/1999/xhtml" class="note-text">
              {{ annotation.text }}
            </div>
          </foreignObject>
        </g>
      </template>
    </g>
  </svg>
</template>

<style scoped>
.annotated-architecture {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.diagram-title {
  fill: #1C2530;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.title-rule,
.notes-rule {
  stroke: #DFE3E8;
  stroke-width: 1;
}

.notes-heading {
  fill: #5A6472;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.block-body {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.block-accent {
  fill: none;
  stroke-width: 4;
  stroke-linecap: round;
}

.block-label {
  fill: #1C2530;
  font-size: 15px;
  font-weight: 650;
}

.block-sublabel {
  fill: #5A6472;
  font-size: 12.5px;
  font-weight: 450;
}

.connection-line {
  fill: none;
  stroke: #28527A;
  stroke-width: 1.7;
  stroke-linecap: round;
}

.connection-line.dashed {
  stroke: #5A6472;
}

.arrow-head {
  fill: #28527A;
}

.connection-label-bg {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 0.8;
}

.connection-label {
  fill: #5A6472;
  font-size: 11.5px;
  font-weight: 600;
  text-anchor: middle;
}

.leader-line {
  fill: none;
  stroke: #5A6472;
  stroke-width: 1;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.annotation-badge,
.note-badge {
  fill: #FFFFFF;
  stroke: #28527A;
  stroke-width: 1.7;
}

.annotation-number,
.note-number {
  fill: #1D3E5E;
  font-size: 12px;
  font-weight: 750;
  text-anchor: middle;
}

.note-text {
  box-sizing: border-box;
  width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 13.5px;
  font-weight: 450;
  line-height: 1.38;
}
</style>
