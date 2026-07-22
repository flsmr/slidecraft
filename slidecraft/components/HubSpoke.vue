<!--
HubSpoke.vue

Props:
- hub: { label: string, desc?: string } — central node.
- spokes: Array<{ label: string, desc?: string, color?: string }> — satellite nodes.
- title?: string — optional diagram title.
- animate: boolean — enables the subtle entrance animation.

Usage:
<HubSpoke
  title="Platform ecosystem"
  :hub="{ label: 'Platform', desc: 'Shared foundation' }"
  :spokes="[
    { label: 'Analytics', desc: 'Measure outcomes' },
    { label: 'Commerce', desc: 'Enable transactions' },
    { label: 'Identity', desc: 'Secure access' }
  ]"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

const props = defineProps({
  hub: {
    type: Object,
    default: () => ({
      label: 'Platform',
      desc: 'Shared foundation',
    }),
  },
  spokes: {
    type: Array,
    default: () => [
      { label: 'Identity', desc: 'Secure access' },
      { label: 'Analytics', desc: 'Actionable insight' },
      { label: 'Commerce', desc: 'Transactions' },
      { label: 'Content', desc: 'Publishing tools' },
      { label: 'Automation', desc: 'Connected workflows' },
      { label: 'Integrations', desc: 'Open ecosystem' },
    ],
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
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const tick=(now)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: first top <li> is the hub, its nested children are spokes ("label | desc").
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  const first = tree[0] || { text: '', children: [] }
  const hubParts = parseLabel(first.text)
  const hub = { label: hubParts.parts[0] || '' }
  if (hubParts.parts[1]) hub.desc = hubParts.parts[1]
  const spokes = (first.children || []).map(c => {
    const { color, parts } = parseLabel(c.text)
    const s = { label: parts[0] || '' }
    if (parts[1]) s.desc = parts[1]
    if (color) s.color = color
    return s
  })
  return { hub, spokes }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : { hub: props.hub, spokes: props.spokes }))
const hubData = computed(() => model.value.hub)
const spokesData = computed(() => model.value.spokes)

const palette = ['#28527A', '#B07D2B', '#3F7D74']
const viewWidth = 1000
const viewHeight = computed(() => props.title ? 560 : 500)
const center = computed(() => ({
  x: viewWidth / 2,
  y: props.title ? 300 : 250,
}))

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))
const phase = (start, span) => clamp((progress.value - start) / span, 0, 1)

const hubPhase = computed(() => phase(0, 0.34))

const nodes = computed(() => {
  const count = Math.max(spokesData.value.length, 1)
  const cx = center.value.x
  const cy = center.value.y
  const radiusX = count <= 4 ? 300 : 350
  const radiusY = count <= 4 ? 168 : 188

  return spokesData.value.map((spoke, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / count
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    const width = 190
    const height = spoke.desc ? 76 : 58
    const finalX = cx + cos * radiusX
    const finalY = cy + sin * radiusY
    const start = 0.22 + (index / count) * 0.34
    const itemProgress = phase(start, 0.42)
    const x = cx + (finalX - cx) * itemProgress
    const y = cy + (finalY - cy) * itemProgress
    const edgePadding = 16
    const boxX = clamp(x - width / 2, edgePadding, viewWidth - width - edgePadding)
    const boxY = clamp(y - height / 2, props.title ? 68 : edgePadding, viewHeight.value - height - edgePadding)

    return {
      ...spoke,
      index,
      color: spoke.color || palette[index % palette.length],
      width,
      height,
      x,
      y,
      boxX,
      boxY,
      progress: itemProgress,
      textAnchor: cos > 0.22 ? 'start' : cos < -0.22 ? 'end' : 'middle',
    }
  })
})

const hubStyle = computed(() => ({
  opacity: hubPhase.value,
  transform: `translate(${center.value.x}px, ${center.value.y}px) scale(${0.88 + hubPhase.value * 0.12})`,
}))
</script>

<template>
  <div class="hub-spoke-wrap">
    <div ref="src" style="display:none"><slot /></div>
    <svg
      class="hub-spoke"
      :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
      role="img"
      :aria-label="title || `${hubData.label} hub-and-spoke diagram`"
    preserveAspectRatio="xMidYMid meet"
  >
    <text
      v-if="title"
      class="diagram-title"
      x="500"
      y="34"
      text-anchor="middle"
    >
      {{ title }}
    </text>

    <g class="connectors">
      <line
        v-for="node in nodes"
        :key="`line-${node.index}`"
        :x1="center.x"
        :y1="center.y"
        :x2="node.x"
        :y2="node.y"
        :stroke="node.color"
        :style="{ opacity: node.progress * 0.72 }"
      />
    </g>

    <g
      v-for="node in nodes"
      :key="`node-${node.index}`"
      class="satellite"
      :style="{
        opacity: node.progress,
        transform: `translate(${node.x}px, ${node.y}px) scale(${0.94 + node.progress * 0.06}) translate(${-node.x}px, ${-node.y}px)`,
      }"
    >
      <GenBox
        :x="node.boxX"
        :y="node.boxY"
        :w="node.width"
        :h="node.height"
        :accent="node.color"
      />
      <text
        class="satellite-label"
        :x="node.boxX + 18"
        :y="node.boxY + (node.desc ? 29 : 35)"
      >
        {{ node.label }}
      </text>
      <text
        v-if="node.desc"
        class="satellite-desc"
        :x="node.boxX + 18"
        :y="node.boxY + 52"
      >
        {{ node.desc }}
      </text>
    </g>

    <g class="hub" :style="hubStyle">
      <circle r="83" class="hub-circle" />
      <text class="hub-label" y="-5" text-anchor="middle">
        {{ hubData.label }}
      </text>
      <text
        v-if="hubData.desc"
        class="hub-desc"
        y="22"
        text-anchor="middle"
      >
        {{ hubData.desc }}
      </text>
    </g>
    </svg>
  </div>
</template>

<style scoped>
.hub-spoke {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.diagram-title {
  fill: #1C2530;
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.connectors line {
  stroke-width: 2;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}

.satellite,
.hub {
  transform-box: view-box;
  transform-origin: 0 0;
}

.satellite-box {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.satellite-accent {
  fill: none;
  stroke-width: 3;
}

.satellite-label {
  fill: #1C2530;
  font-size: 16px;
  font-weight: 650;
}

.satellite-desc {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 400;
}

.hub-circle {
  fill: #28527A;
  stroke: #1D3E5E;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.hub-label {
  fill: #FFFFFF;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.hub-desc {
  fill: #FFFFFF;
  font-size: 13px;
  font-weight: 450;
  opacity: 0.84;
}
</style>
