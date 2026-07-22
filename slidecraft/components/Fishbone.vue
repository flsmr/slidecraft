<!--
Fishbone.vue

Props:
- effect: String — problem or effect shown in the right-side head.
- categories: Array<{ label: string; causes: string[] }> — major causes, alternating above/below the spine.
- title?: String — optional diagram heading.
- animate: Boolean — enables the subtle staged reveal.

Usage:
<Fishbone
  title="Root-cause analysis"
  effect="Delayed product launch"
  :categories="[
    { label: 'People', causes: ['Unclear ownership', 'Limited capacity'] },
    { label: 'Process', causes: ['Late approvals', 'Scope changes'] },
    { label: 'Tools', causes: ['Manual reporting', 'System outages'] },
    { label: 'Environment', causes: ['Vendor delays', 'Policy changes'] }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

type Category = {
  label: string
  causes: string[]
}

const props = defineProps({
  effect: {
    type: String,
    default: 'Delayed product launch',
  },
  categories: {
    type: Array as () => Category[],
    default: () => [
      { label: 'People', causes: ['Unclear ownership', 'Limited capacity', 'Training gaps'] },
      { label: 'Process', causes: ['Late approvals', 'Scope changes', 'Weak handoffs'] },
      { label: 'Tools', causes: ['Manual reporting', 'System outages'] },
      { label: 'Environment', causes: ['Vendor delays', 'Policy changes'] },
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
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const frame=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: an optional childless first <li> is the effect; each remaining
// top <li> is a category ("label"), its nested list = causes.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  let effect = props.effect
  let cats = tree
  if (tree.length && (!tree[0].children || !tree[0].children.length)) {
    effect = parseLabel(tree[0].text).parts[0] || props.effect
    cats = tree.slice(1)
  }
  const categories = cats.map(node => ({
    label: parseLabel(node.text).parts[0] || '',
    causes: (node.children || []).map(c => c.text),
  }))
  return { effect, categories: categories.length ? categories : props.categories }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : { effect: props.effect, categories: props.categories }))
const effectData = computed(() => model.value.effect)
const categoriesData = computed<Category[]>(() => model.value.categories)

const viewWidth = 1000
const viewHeight = computed(() => props.title ? 520 : 480)
const spineY = computed(() => props.title ? 278 : 250)
const spineStart = 52
const spineEnd = 808   // extend spine so the arrowhead reaches the effect head
const headX = 820
const headWidth = 164
const headHeight = 92

const clamp = (value: number) => Math.max(0, Math.min(1, value))
const phase = (start: number, end: number) =>
  clamp((progress.value - start) / Math.max(0.001, end - start))

const spineProgress = computed(() => phase(0, 0.34))
// Solid spine that fades in, so the horizontal line always reaches the arrowhead
// (a tail-first dash-draw could leave the spine short of the effect head at rest).
const spineStyle = computed(() => ({ opacity: spineProgress.value }))

const headStyle = computed(() => {
  const p = phase(0.25, 0.48)
  return {
    opacity: p,
    transform: `translate(${(1 - p) * 8}px, 0px) scale(${0.98 + p * 0.02})`,
    transformOrigin: `${headX + headWidth / 2}px ${spineY.value}px`,
  }
})

const titleStyle = computed(() => {
  const p = phase(0, 0.22)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 5}px)`,
  }
})

const layout = computed(() => {
  const count = Math.max(1, categoriesData.value.length)
  const usableStart = 145
  const usableEnd = 735
  const spacing = count === 1 ? 0 : (usableEnd - usableStart) / (count - 1)

  return categoriesData.value.map((category, index) => {
    const side = index % 2 === 0 ? -1 : 1
    const attachX = count === 1 ? (usableStart + usableEnd) / 2 : usableStart + spacing * index
    const outerX = Math.max(42, attachX - 118)
    const outerY = spineY.value + side * 172
    const boxWidth = 138
    const boxHeight = 38
    const boxX = Math.max(18, outerX - boxWidth / 2)
    const boxY = side < 0 ? outerY - boxHeight : outerY
    const lineEndY = side < 0 ? boxY + boxHeight : boxY
    const lineEndX = outerX

    const causes = category.causes.slice(0, 3).map((cause, causeIndex, all) => {
      const fraction = (causeIndex + 1) / (all.length + 1)
      const x = attachX + (lineEndX - attachX) * fraction
      const y = spineY.value + (lineEndY - spineY.value) * fraction
      const tickDirection = side < 0 ? -1 : 1
      const tickLength = 50
      const tickEndX = x + tickLength
      const tickEndY = y + tickDirection * 13
      return {
        cause,
        x,
        y,
        tickEndX,
        tickEndY,
        textX: tickEndX + 5,
        textY: tickEndY + (side < 0 ? -3 : 13),
      }
    })

    return {
      category,
      index,
      side,
      attachX,
      outerX,
      lineEndX,
      lineEndY,
      boxX,
      boxY,
      boxWidth,
      boxHeight,
      causes,
    }
  })
})

function boneProgress(index: number) {
  const count = Math.max(1, categoriesData.value.length)
  const start = 0.34 + (index / count) * 0.28
  return phase(start, Math.min(0.88, start + 0.24))
}

function causeProgress(index: number, causeIndex: number) {
  const count = Math.max(1, categoriesData.value.length)
  const start = 0.48 + (index / count) * 0.25 + causeIndex * 0.035
  return phase(start, Math.min(1, start + 0.2))
}

function boneLineStyle(index: number) {
  return {
    strokeDashoffset: `${1 - boneProgress(index)}`,
  }
}

function categoryStyle(index: number, side: number) {
  const p = boneProgress(index)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * side * -6}px) scale(${0.98 + p * 0.02})`,
  }
}

function causeStyle(index: number, causeIndex: number, side: number) {
  const p = causeProgress(index, causeIndex)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * side * -4}px)`,
  }
}

function accent(index: number) {
  return [
    '#28527A',
    '#B07D2B',
    '#3F7D74',
    '#7FA8CF',
    '#9AA7B5',
    '#C9A66B',
  ][index % 6]
}
</script>

<template>
  <div class="fishbone-wrap">
    <div ref="src" style="display:none"><slot /></div>
    <svg
      class="fishbone"
      :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
      role="img"
      :aria-label="`${title ? `${title}: ` : ''}${effectData}`"
      preserveAspectRatio="xMidYMid meet"
    >
    <g v-if="title" class="diagram-title" :style="titleStyle">
      <text x="28" y="38">{{ title }}</text>
      <line x1="28" y1="52" x2="972" y2="52" />
    </g>

    <g class="spine">
      <line
        class="spine-line"
        :style="spineStyle"
        :x1="spineStart"
        :y1="spineY"
        :x2="spineEnd"
        :y2="spineY"
      />
      <path
        class="spine-arrow"
        :style="{ opacity: spineProgress }"
        :d="`M ${spineEnd - 2} ${spineY - 7} L ${spineEnd + 12} ${spineY} L ${spineEnd - 2} ${spineY + 7}`"
      />
    </g>

    <g
      v-for="item in layout"
      :key="`${item.category.label}-${item.index}`"
      class="bone-group"
    >
      <line
        class="draw-line bone-line"
        :style="boneLineStyle(item.index)"
        :x1="item.attachX"
        :y1="spineY"
        :x2="item.lineEndX"
        :y2="item.lineEndY"
        pathLength="1"
      />

      <g
        class="category-node"
        :style="categoryStyle(item.index, item.side)"
      >
        <GenBox
          :x="item.boxX"
          :y="item.boxY"
          :w="item.boxWidth"
          :h="item.boxHeight"
          :accent="accent(item.index)"
        />
        <text
          class="category-label"
          :x="item.boxX + item.boxWidth / 2"
          :y="item.boxY + item.boxHeight / 2 + 5"
          text-anchor="middle"
        >
          {{ item.category.label }}
        </text>
      </g>

      <g
        v-for="(cause, causeIndex) in item.causes"
        :key="`${cause.cause}-${causeIndex}`"
        class="cause"
        :style="causeStyle(item.index, causeIndex, item.side)"
      >
        <line
          :x1="cause.x"
          :y1="cause.y"
          :x2="cause.tickEndX"
          :y2="cause.tickEndY"
        />
        <text
          :x="cause.textX"
          :y="cause.textY"
          text-anchor="start"
        >
          {{ cause.cause }}
        </text>
      </g>
    </g>

    <g class="effect-head" :style="headStyle">
      <GenBox
        :x="headX"
        :y="spineY - headHeight / 2"
        :w="headWidth"
        :h="headHeight"
        accent="#28527A"
        :emphasis="true"
      />
      <text
        class="effect-kicker"
        :x="headX + 22"
        :y="spineY - 17"
      >
        EFFECT
      </text>
      <foreignObject
        :x="headX + 21"
        :y="spineY - 8"
        :width="headWidth - 34"
        height="50"
      >
        <div xmlns="http://www.w3.org/1999/xhtml" class="effect-text">
          {{ effectData }}
        </div>
      </foreignObject>
    </g>
    </svg>
  </div>
</template>

<style scoped>
.fishbone {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.diagram-title text {
  fill: #1C2530;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.diagram-title line {
  stroke: #DFE3E8;
  stroke-width: 1;
}

.draw-line {
  fill: none;
  stroke-dasharray: 1;
  stroke-dashoffset: 0;
  vector-effect: non-scaling-stroke;
}

.spine-line {
  stroke: #28527A;
  stroke-width: 2;
}

.spine-arrow {
  fill: none;
  stroke: #28527A;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.bone-line {
  stroke: #5A6472;
  stroke-linecap: round;
  stroke-width: 1.35;
}

.category-node,
.effect-head,
.cause,
.diagram-title {
  transform-box: fill-box;
}

.category-node rect {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.category-accent {
  fill: none;
  stroke-width: 3;
  vector-effect: non-scaling-stroke;
}

.category-label {
  fill: #1C2530;
  font-size: 14px;
  font-weight: 650;
}

.cause line {
  stroke: #5A6472;
  stroke-linecap: round;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.cause text {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 450;
}

.effect-head > rect:first-child {
  fill: #F5F6F8;
  stroke: #28527A;
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.effect-head .effect-bar {
  fill: #28527A;
  stroke: none;
}

.effect-kicker {
  fill: #28527A;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.12em;
}

.effect-text {
  display: flex;
  align-items: flex-start;
  width: 100%;
  height: 100%;
  overflow: hidden;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
</style>
