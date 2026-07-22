<!--
BeforeAfter.vue

A before → after comparison. Paired rows: each "before" point sits on the same row as the
corresponding "after" point, so the reader reads across to see what changed.

Props:
- before: { title: string, points: string[], color? } — starting state (left column).
- after:  { title: string, points: string[], color? } — new state (right column).
- arrowLabel: string — small caption shown between the two headers.
- title?: string — optional heading.
- animate: boolean — subtle top→down row reveal (default true).

Usage:
<BeforeAfter
  title="Platform evolution"
  :before="{ title: 'Before', points: ['Manual releases', 'Siloed ownership'] }"
  :after="{ title: 'After', points: ['Automated delivery', 'Shared ownership'] }"
  arrow-label="Platform shift"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type ComparisonSide = {
  title: string
  points: string[]
  color?: string
}

const props = withDefaults(defineProps<{
  before?: ComparisonSide
  after?: ComparisonSide
  arrowLabel?: string
  title?: string
  animate?: boolean
}>(), {
  before: () => ({
    title: 'Before',
    points: [
      'Manual, high-risk releases',
      'Teams maintain duplicated tooling',
      'Operational knowledge stays siloed',
      'Scaling requires more coordination',
    ],
    color: '#5A6472',
  }),
  after: () => ({
    title: 'After',
    points: [
      'Automated, repeatable delivery',
      'Teams build on shared platform services',
      'Operational patterns become reusable',
      'Scaling is supported by self-service',
    ],
    color: '#3F7D74',
  }),
  arrowLabel: 'Platform shift',
  title: 'From fragmented delivery to a shared platform',
  animate: true,
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const d=700; const tick=(now)=>{const t=Math.min(1,(now-start)/d);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: two top <li> ("Before", "After"), each nested list = points.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  const side = (node, fallback: ComparisonSide): ComparisonSide => {
    if (!node) return fallback
    const { color, parts } = parseLabel(node.text)
    const s: ComparisonSide = { title: parts[0] || fallback.title, points: (node.children || []).map(c => c.text) }
    if (color) s.color = color
    return s
  }
  return { before: side(tree[0], props.before), after: side(tree[1], props.after) }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : { before: props.before, after: props.after }))
const beforeData = computed<ComparisonSide>(() => model.value.before)
const afterData = computed<ComparisonSide>(() => model.value.after)

const rows = computed(() => {
  const count = Math.max(beforeData.value.points.length, afterData.value.points.length)
  return Array.from({ length: count }, (_, index) => ({
    before: beforeData.value.points[index] ?? '',
    after: afterData.value.points[index] ?? '',
  }))
})

const revealStyle = (start: number, duration = 0.24) => {
  const local = Math.max(0, Math.min(1, (progress.value - start) / duration))
  return {
    opacity: local,
    transform: `translateY(${(1 - local) * 8}px)`,
  }
}

const headerStyle = computed(() => revealStyle(0, 0.3))

const rowStyle = (index: number) => {
  const available = 0.62
  const step = rows.value.length > 1 ? available / (rows.value.length - 1) : 0
  return revealStyle(0.22 + index * step, 0.24)
}

const beforeColor = computed(() => beforeData.value.color || '#5A6472')
const afterColor = computed(() => afterData.value.color || '#3F7D74')
</script>

<template>
  <figure class="before-after" aria-label="Before and after comparison">
    <div ref="src" style="display:none"><slot /></div>
    <figcaption
      v-if="title"
      class="figure-title"
      :style="revealStyle(0, 0.25)"
    >
      {{ title }}
    </figcaption>

    <div class="comparison">
      <div class="header-row" :style="headerStyle">
        <div
          class="column-heading before-heading"
          :style="{ color: beforeColor }"
        >
          <span class="eyebrow">Starting point</span>
          <strong>{{ beforeData.title }}</strong>
        </div>

        <div class="transition-caption" aria-label="Transition">
          <span>{{ arrowLabel }}</span>
        </div>

        <div
          class="column-heading after-heading"
          :style="{ color: afterColor }"
        >
          <span class="eyebrow">New state</span>
          <strong>{{ afterData.title }}</strong>
        </div>
      </div>

      <div class="body">
        <div
          v-for="(row, index) in rows"
          :key="index"
          class="comparison-row"
          :style="rowStyle(index)"
        >
          <div class="cell before-cell">
            <span v-if="row.before">{{ row.before }}</span>
            <span v-else class="empty" aria-label="No corresponding item">&nbsp;</span>
          </div>

          <div
            class="cell after-cell"
            :style="{ '--after-edge': afterColor }"
          >
            <span v-if="row.after">{{ row.after }}</span>
            <span v-else class="empty" aria-label="No corresponding item">&nbsp;</span>
          </div>
        </div>
      </div>
    </div>
  </figure>
</template>

<style scoped>
.before-after {
  width: 100%;
  max-width: 100%;
  margin: 0;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 15px;
  line-height: 1.45;
  overflow: hidden;
}

.figure-title {
  margin: 0 0 14px;
  color: #1C2530;
  font-family: 'Spectral', Georgia, 'Times New Roman', serif;
  font-size: clamp(19px, 2.2vw, 27px);
  font-weight: 600;
  line-height: 1.2;
  transition: opacity 80ms linear, transform 80ms linear;
}

.comparison {
  width: 100%;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-radius: 8px;
  background: #FFFFFF;
}

.header-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(88px, 0.22fr) minmax(0, 1fr);
  min-height: 74px;
  border-bottom: 1px solid #DFE3E8;
  background: #F5F6F8;
  transition: opacity 80ms linear, transform 80ms linear;
}

.column-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  padding: 13px 18px;
}

.column-heading strong {
  overflow-wrap: anywhere;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.25;
}

.eyebrow {
  margin-bottom: 3px;
  color: #5A6472;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.08em;
  line-height: 1.2;
  text-transform: uppercase;
}

.after-heading {
  border-left: 1px solid #DFE3E8;
  background: color-mix(in srgb, #3F7D74 7%, #F5F6F8);
}

.transition-caption {
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 5px;
}

.transition-caption span {
  max-width: 100%;
  padding: 4px 9px;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-radius: 999px;
  background: #FFFFFF;
  color: #5A6472;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.body {
  width: 100%;
}

.comparison-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  transition: opacity 80ms linear, transform 80ms linear;
}

.comparison-row + .comparison-row {
  border-top: 1px solid #DFE3E8;
}

.comparison-row:nth-child(even) .before-cell {
  background: color-mix(in srgb, #F5F6F8 55%, #FFFFFF);
}

.cell {
  min-width: 0;
  min-height: 54px;
  padding: 14px 18px;
  overflow-wrap: anywhere;
}

.before-cell {
  color: #1C2530;
}

.after-cell {
  border-left: 3px solid var(--after-edge, #3F7D74);
  background: color-mix(in srgb, #3F7D74 6%, #FFFFFF);
  color: #1C2530;
}

.empty {
  display: block;
  min-height: 1em;
}

@media (max-width: 560px) {
  .before-after {
    font-size: 13px;
  }

  .header-row {
    grid-template-columns: minmax(0, 1fr) 72px minmax(0, 1fr);
  }

  .column-heading,
  .cell {
    padding: 11px 12px;
  }

  .column-heading strong {
    font-size: 14px;
  }

  .transition-caption span {
    padding-inline: 6px;
    font-size: 10px;
  }
}
</style>
