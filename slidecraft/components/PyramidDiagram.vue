<catalog>
use: A hierarchy of levels narrowing from a broad base to a narrow apex (e.g. vision to execution).
looks: A stacked pyramid, widest at the bottom to narrowest at the top, with optional side description callouts.
fill: bullet list ordered top→bottom; each item is a level, "label | desc".
</catalog>
<!--
PyramidDiagram.vue

Props:
- levels: Array<{ label: string; desc?: string; color?: string }> ordered TOP→BOTTOM.
- title?: Optional heading above the diagram.
- side?: 'right' | 'left' | 'none' — placement of description callouts.
- animate?: Enables the subtle bottom→top entrance animation.

Example:
<PyramidDiagram
  title="From vision to execution"
  side="right"
  :levels="[
    { label: 'Vision', desc: 'The enduring destination' },
    { label: 'Strategy', desc: 'Choices that focus effort' },
    { label: 'Tactics', desc: 'Coordinated initiatives' },
    { label: 'Operations', desc: 'Repeatable daily delivery' }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type PyramidLevel = {
  label: string
  desc?: string
  color?: string
}

const props = defineProps({
  levels: {
    type: Array as () => PyramidLevel[],
    default: () => [
      { label: 'Vision', desc: 'The enduring destination' },
      { label: 'Strategy', desc: 'Choices that focus effort' },
      { label: 'Tactics', desc: 'Coordinated initiatives' },
      { label: 'Operations', desc: 'Repeatable daily delivery' },
    ],
  },
  title: {
    type: String,
    default: 'From vision to execution',
  },
  side: {
    type: String as () => 'right' | 'left' | 'none',
    default: 'right',
    validator: (value: string) => ['right', 'left', 'none'].includes(value),
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

const palette = [
  '#28527A',
  '#7FA8CF',
  '#B07D2B',
  '#3F7D74',
  '#9AA7B5',
  '#C9A66B',
]

// Nested-list authoring: each top <li> is a level ("label | desc"), top -> bottom.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    const { color, parts } = parseLabel(node.text)
    const lvl: PyramidLevel = { label: parts[0] || '' }
    if (parts[1]) lvl.desc = parts[1]
    if (color) lvl.color = color
    return lvl
  })
}
const levelsData = computed<PyramidLevel[]>(() => (parsed.value ? mapToShape(parsed.value) : props.levels))
const safeLevels = computed(() => levelsData.value.length
  ? levelsData.value
  : [{ label: 'Level' }])

const hasCallouts = computed(() =>
  props.side !== 'none' && safeLevels.value.some(level => level.desc),
)

const viewWidth = computed(() => hasCallouts.value ? 1000 : 700)
const pyramidLeft = computed(() => {
  if (!hasCallouts.value) return 50
  return props.side === 'left' ? 350 : 50
})
const pyramidWidth = 600
const pyramidTop = 18
const pyramidHeight = 420

const tiers = computed(() => {
  const count = safeLevels.value.length
  const tierHeight = pyramidHeight / count
  const center = pyramidLeft.value + pyramidWidth / 2

  return safeLevels.value.map((level, index) => {
    const y1 = pyramidTop + index * tierHeight
    const y2 = pyramidTop + (index + 1) * tierHeight
    const topWidth = pyramidWidth * (index / count)
    const bottomWidth = pyramidWidth * ((index + 1) / count)
    const x1 = center - topWidth / 2
    const x2 = center + topWidth / 2
    const x3 = center + bottomWidth / 2
    const x4 = center - bottomWidth / 2
    const midY = (y1 + y2) / 2
    const edgeX = props.side === 'left'
      ? (x1 + x4) / 2
      : (x2 + x3) / 2
    const lineEnd = props.side === 'left' ? 326 : 674
    const textX = props.side === 'left' ? 310 : 690

    return {
      ...level,
      index,
      points: `${x1},${y1} ${x2},${y1} ${x3},${y2} ${x4},${y2}`,
      center,
      midY,
      edgeX,
      lineEnd,
      textX,
      color: level.color || palette[index % palette.length],
    }
  })
})

function stagedValue(index: number, total: number, callout = false) {
  const bottomOrder = total - 1 - index
  const slots = Math.max(1, total + 1)
  const delay = (bottomOrder / slots) * 0.42 + (callout ? 0.18 : 0)
  return Math.max(0, Math.min(1, (progress.value - delay) / 0.4))
}

function tierStyle(index: number) {
  const value = stagedValue(index, tiers.value.length)
  return {
    opacity: value,
    transform: `translateY(${(1 - value) * 14}px)`,
  }
}

function calloutStyle(index: number) {
  const value = stagedValue(index, tiers.value.length, true)
  return {
    opacity: value,
    transform: `translateX(${(1 - value) * (props.side === 'left' ? 8 : -8)}px)`,
  }
}
</script>

<template>
  <figure class="pyramid-diagram">
    <div ref="src" style="display:none"><slot /></div>
    <figcaption v-if="title" class="title">{{ title }}</figcaption>

    <svg
      class="diagram"
      :viewBox="`0 0 ${viewWidth} 456`"
      role="img"
      :aria-label="title || 'Stacked pyramid diagram'"
      preserveAspectRatio="xMidYMid meet"
    >
      <g
        v-for="tier in tiers"
        :key="`${tier.index}-${tier.label}`"
        class="tier"
        :style="tierStyle(tier.index)"
      >
        <polygon
          class="tier-shape"
          :points="tier.points"
          :fill="tier.color"
        />
        <text
          class="tier-label"
          :x="tier.center"
          :y="tier.midY"
          text-anchor="middle"
          dominant-baseline="middle"
        >
          {{ tier.label }}
        </text>
      </g>

      <g
        v-if="hasCallouts"
        class="callouts"
      >
        <g
          v-for="tier in tiers"
          v-show="tier.desc"
          :key="`callout-${tier.index}`"
          class="callout"
          :style="calloutStyle(tier.index)"
        >
          <line
            class="leader"
            :x1="tier.edgeX"
            :y1="tier.midY"
            :x2="tier.lineEnd"
            :y2="tier.midY"
          />
          <circle
            class="leader-dot"
            :cx="tier.edgeX"
            :cy="tier.midY"
            r="3"
          />
          <text
            class="description"
            :x="tier.textX"
            :y="tier.midY"
            :text-anchor="side === 'left' ? 'end' : 'start'"
            dominant-baseline="middle"
          >
            {{ tier.desc }}
          </text>
        </g>
      </g>
    </svg>
  </figure>
</template>

<style scoped>
.pyramid-diagram {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  margin: 0;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.title {
  margin: 0 0 0.65rem;
  color: #1C2530;
  font-size: clamp(16px, 2.2vw, 22px);
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.015em;
  text-align: center;
}

.diagram {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
}

.tier,
.callout {
  transform-box: fill-box;
  transform-origin: center;
  will-change: opacity, transform;
}

.tier-shape {
  stroke: #FFFFFF;
  stroke-width: 3;
  stroke-linejoin: round;
}

.tier-label {
  fill: #FFFFFF;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 17px;
  font-weight: 650;
  letter-spacing: 0.01em;
  paint-order: stroke;
  stroke: color-mix(in srgb, #1C2530 18%, transparent);
  stroke-width: 1.5px;
}

.leader {
  stroke: #5A6472;
  stroke-width: 1.5;
}

.leader-dot {
  fill: #28527A;
}

.description {
  fill: #5A6472;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 14px;
  font-weight: 500;
}

@media (prefers-reduced-motion: reduce) {
  .tier,
  .callout {
    will-change: auto;
  }
}
</style>
