<!--
Roadmap.vue

Props:
- milestones: Array<{ date: string | number, title: string, desc?: string, done?: boolean, color?: string }>
  Milestones are evenly spaced unless every date is numeric or a parseable ISO date, in which case spacing is proportional.
- title?: Optional diagram heading.
- laneLabel?: Optional caption displayed beside the time axis.
- animate?: Enables the subtle enter animation (default: true).

Usage:
<Roadmap
  title="Product roadmap"
  lane-label="2026 delivery plan"
  :milestones="[
    { date: '2026-01-15', title: 'Discovery', desc: 'Validate priorities', done: true },
    { date: '2026-03-01', title: 'Prototype', desc: 'Test core workflows', done: true },
    { date: '2026-06-15', title: 'Beta', desc: 'Invite pilot teams' },
    { date: '2026-09-01', title: 'Launch', desc: 'General availability' }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type Milestone = {
  date: string | number
  title: string
  desc?: string
  done?: boolean
  color?: string
}

const props = defineProps({
  milestones: {
    type: Array as () => Milestone[],
    default: () => [
      { date: '2026-01-15', title: 'Discovery', desc: 'Align needs and success measures.', done: true },
      { date: '2026-03-10', title: 'Prototype', desc: 'Test the core experience.', done: true },
      { date: '2026-06-01', title: 'Private beta', desc: 'Learn with pilot teams.' },
      { date: '2026-09-15', title: 'Launch', desc: 'Release to all customers.' },
      { date: '2026-12-01', title: 'Scale', desc: 'Expand adoption and capability.' },
    ],
  },
  title: {
    type: String,
    default: '',
  },
  laneLabel: {
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
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: each top <li> is a milestone ("date | title | desc"; leading "[x]" = done).
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    let text = node.text
    let done = false
    const dm = text.match(/^\[\s*x\s*\]\s*/i)
    if (dm) { done = true; text = text.slice(dm[0].length) }
    const { color, parts } = parseLabel(text)
    const m: Milestone = { date: parts[0] || '', title: parts[1] || parts[0] || '' }
    if (parts[2]) m.desc = parts[2]
    if (done) m.done = true
    if (color) m.color = color
    return m
  })
}
const milestonesData = computed<Milestone[]>(() => (parsed.value ? mapToShape(parsed.value) : props.milestones))

function dateValue(date: string | number) {
  if (typeof date === 'number' && Number.isFinite(date))
    return date
  if (typeof date === 'string') {
    const trimmed = date.trim()
    if (/^-?\d+(?:\.\d+)?$/.test(trimmed))
      return Number(trimmed)
    if (/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(trimmed)) {
      const parsed = Date.parse(trimmed)
      return Number.isNaN(parsed) ? null : parsed
    }
  }
  return null
}

const positions = computed(() => {
  const count = milestonesData.value.length
  if (!count) return []

  const values = milestonesData.value.map(item => dateValue(item.date))
  const proportional = count > 1 && values.every(value => value !== null)
  const min = proportional ? Math.min(...values as number[]) : 0
  const max = proportional ? Math.max(...values as number[]) : 0
  const span = max - min

  return milestonesData.value.map((_, index) => {
    let ratio = count === 1 ? 0.5 : index / (count - 1)
    if (proportional && span > 0)
      ratio = ((values[index] as number) - min) / span
    // inset from the edges so the first/last cards (translateX(-50%)) are not
    // clipped by the stage's overflow:hidden
    return 12 + ratio * 76
  })
})

const items = computed(() =>
  milestonesData.value.map((milestone, index) => ({
    ...milestone,
    index,
    position: positions.value[index] ?? 50,
    side: index % 2 === 0 ? 'above' : 'below',
  })),
)

function phase(index: number, start: number, spread: number) {
  const count = Math.max(1, milestonesData.value.length)
  const delay = start + (index / count) * spread
  return Math.max(0, Math.min(1, (progress.value - delay) / Math.max(0.001, 1 - delay)))
}

const baselineStyle = computed(() => ({
  transform: `scaleX(${Math.max(0, Math.min(1, progress.value / 0.58))})`,
}))

function markerStyle(index: number, color?: string) {
  const p = phase(index, 0.18, 0.38)
  return {
    '--item-color': color || '#28527A',
    opacity: p,
    transform: `translate(-50%, -50%) scale(${0.55 + p * 0.45})`,
  }
}

function cardStyle(index: number, side: string, color?: string) {
  const p = phase(index, 0.28, 0.42)
  const direction = side === 'above' ? 1 : -1
  return {
    '--item-color': color || '#28527A',
    opacity: p,
    transform: `translateX(-50%) translateY(${direction * (1 - p) * 8}px)`,
  }
}
</script>

<template>
  <section class="roadmap" :aria-label="title || 'Roadmap'">
    <div ref="src" style="display:none"><slot /></div>
    <header v-if="title || laneLabel" class="roadmap__header">
      <h3 v-if="title">{{ title }}</h3>
      <span v-if="laneLabel">{{ laneLabel }}</span>
    </header>

    <div v-if="items.length" class="roadmap__stage">
      <div class="roadmap__axis" aria-hidden="true">
        <div class="roadmap__baseline" :style="baselineStyle" />
      </div>

      <article
        v-for="item in items"
        :key="`${item.date}-${item.title}-${item.index}`"
        class="roadmap__item"
        :style="{ left: `${item.position}%` }"
      >
        <div
          class="roadmap__marker"
          :class="{ 'roadmap__marker--done': item.done }"
          :style="markerStyle(item.index, item.color)"
          aria-hidden="true"
        />

        <div
          class="roadmap__card"
          :class="`roadmap__card--${item.side}`"
          :style="cardStyle(item.index, item.side, item.color)"
        >
          <time>{{ item.date }}</time>
          <strong>{{ item.title }}</strong>
          <p v-if="item.desc">{{ item.desc }}</p>
        </div>
      </article>
    </div>

    <p v-else class="roadmap__empty">No milestones</p>
  </section>
</template>

<style scoped>
.roadmap {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.roadmap__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.55rem;
}

.roadmap__header h3 {
  margin: 0;
  color: #1C2530;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.25;
}

.roadmap__header span {
  color: #5A6472;
  font-size: 13px;
  line-height: 1.3;
  text-align: right;
}

.roadmap__stage {
  position: relative;
  width: 100%;
  height: 25rem;
  min-height: 320px;
  overflow: hidden;
}

.roadmap__axis {
  position: absolute;
  top: 50%;
  right: 12%;
  left: 12%;
  height: 1px;
}

.roadmap__baseline {
  width: 100%;
  height: 1px;
  background: #28527A;
  opacity: 0.72;
  transform-origin: left center;
  will-change: transform;
}

.roadmap__baseline::after {
  position: absolute;
  top: 50%;
  right: -1px;
  width: 7px;
  height: 7px;
  border-top: 1px solid #28527A;
  border-right: 1px solid #28527A;
  content: "";
  transform: translateY(-50%) rotate(45deg);
}

.roadmap__item {
  position: absolute;
  top: 50%;
  width: 0;
  height: 0;
}

.roadmap__marker {
  position: absolute;
  z-index: 3;
  top: 0;
  left: 0;
  box-sizing: border-box;
  width: 13px;
  height: 13px;
  border: 2px solid var(--item-color);
  border-radius: 50%;
  background: #FFFFFF;
  box-shadow: 0 0 0 4px #FFFFFF;
  will-change: opacity, transform;
}

.roadmap__marker--done {
  background: var(--item-color);
}

.roadmap__card {
  position: absolute;
  left: 0;
  box-sizing: border-box;
  width: clamp(118px, 15vw, 168px);
  padding: 0.65rem 0.7rem 0.62rem 0.82rem;
  border: 1px solid #DFE3E8;
  border-left: 3px solid var(--item-color);
  border-radius: 8px;
  background: #F5F6F8;
  color: #1C2530;
  will-change: opacity, transform;
}

.roadmap__card::after {
  position: absolute;
  left: 50%;
  width: 1px;
  height: 2.05rem;
  background: #DFE3E8;
  content: "";
  transform: translateX(-50%);
}

.roadmap__card--above {
  bottom: 2.55rem;
}

.roadmap__card--above::after {
  top: 100%;
}

.roadmap__card--below {
  top: 2.55rem;
}

.roadmap__card--below::after {
  bottom: 100%;
}

.roadmap__card time {
  display: block;
  margin-bottom: 0.18rem;
  color: var(--item-color);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.2;
}

.roadmap__card strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.25;
}

.roadmap__card p {
  margin: 0.28rem 0 0;
  color: #5A6472;
  font-size: 13px;
  line-height: 1.35;
}

.roadmap__empty {
  margin: 1rem 0 0;
  padding: 1rem;
  border: 1px dashed #DFE3E8;
  border-radius: 8px;
  color: #5A6472;
  font-size: 14px;
  text-align: center;
}

@media (max-width: 700px) {
  .roadmap__card {
    width: clamp(104px, 18vw, 138px);
    padding: 0.52rem 0.55rem 0.5rem 0.65rem;
  }

  .roadmap__card strong {
    font-size: 14px;
  }

  .roadmap__card p,
  .roadmap__card time {
    font-size: 12px;
  }
}
</style>
