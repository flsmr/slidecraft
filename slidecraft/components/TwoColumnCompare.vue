<catalog>
use: A criterion-by-criterion comparison of two concepts or options.
looks: A two-column table with a criterion label per row and a value in each column.
fill: row = "criterion | left | right"; a leading "= Left title | Right title" li sets the two headings.
</catalog>
<!--
TwoColumnCompare.vue

Props:
- title?: string — optional diagram heading.
- left: { title: string; subtitle?: string; accent?: string } — left option.
- right: { title: string; subtitle?: string; accent?: string } — right option.
- rows: Array<{ criterion: string; left: string | number; right: string | number; leftGood?: boolean; rightGood?: boolean }>
- dividerLabel: string — badge between headers; default "vs".
- animate: boolean — enables the subtle enter animation; default true.

Usage:
<TwoColumnCompare
  title="Platform comparison"
  :left="{ title: 'Build', subtitle: 'Custom platform', accent: '#28527A' }"
  :right="{ title: 'Buy', subtitle: 'Managed service', accent: '#3F7D74' }"
  :rows="[
    { criterion: 'Launch time', left: '12–16 weeks', right: '2–4 weeks', rightGood: true },
    { criterion: 'Control', left: 'Complete', right: 'Configured', leftGood: true }
  ]"
  divider-label="or"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type Option = {
  title: string
  subtitle?: string
  accent?: string
}

type CompareRow = {
  criterion: string
  left: string | number
  right: string | number
  leftGood?: boolean
  rightGood?: boolean
}

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  left: {
    type: Object as () => Option,
    default: () => ({
      title: 'Build in-house',
      subtitle: 'Maximum ownership and flexibility',
      accent: '#28527A',
    }),
  },
  right: {
    type: Object as () => Option,
    default: () => ({
      title: 'Managed platform',
      subtitle: 'Faster deployment with shared ownership',
      accent: '#3F7D74',
    }),
  },
  rows: {
    type: Array as () => CompareRow[],
    default: () => [
      { criterion: 'Time to launch', left: '12–16 weeks', right: '2–4 weeks', rightGood: true },
      { criterion: 'Upfront cost', left: 'Higher', right: 'Lower', rightGood: true },
      { criterion: 'Customisation', left: 'Complete control', right: 'Configurable', leftGood: true },
      { criterion: 'Maintenance', left: 'Internal team', right: 'Provider managed', rightGood: true },
      { criterion: 'Data ownership', left: 'Full ownership', right: 'Contract dependent', leftGood: true },
    ],
  },
  dividerLabel: {
    type: String,
    default: 'vs',
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const duration=700; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: each top <li> is a row ("criterion | left | right"). A leading
// header bullet "= Left title | Right title" sets the two column headings; without it the
// heading props (left/right) are used.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  let left: Option | null = null
  let right: Option | null = null
  const rows: CompareRow[] = []
  tree.forEach(node => {
    const raw = node.text.trim()
    if (raw.startsWith('=')) {
      const p = raw.slice(1).split('|').map(s => s.trim())
      left = { title: p[0] || props.left.title, subtitle: '' }
      right = { title: p[1] || props.right.title, subtitle: '' }
      return
    }
    const { parts } = parseLabel(node.text)
    rows.push({ criterion: parts[0] || '', left: parts[1] || '', right: parts[2] || '' })
  })
  return { rows, left, right }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : null))
const rowsData = computed<CompareRow[]>(() => (model.value ? model.value.rows : props.rows))
const leftData = computed<Option>(() => (model.value && model.value.left ? model.value.left : props.left))
const rightData = computed<Option>(() => (model.value && model.value.right ? model.value.right : props.right))

const leftAccent = computed(() => leftData.value.accent || '#28527A')
const rightAccent = computed(() => rightData.value.accent || '#3F7D74')

function phase(start: number, span: number) {
  return Math.max(0, Math.min(1, (progress.value - start) / span))
}

const titleStyle = computed(() => ({
  opacity: phase(0, 0.28),
  transform: `translateY(${(1 - phase(0, 0.28)) * 5}px)`,
}))

function headerStyle(side: 'left' | 'right') {
  const p = phase(0.04, 0.48)
  return {
    opacity: p,
    transform: `translateX(${(1 - p) * (side === 'left' ? -14 : 14)}px)`,
  }
}

const badgeStyle = computed(() => {
  const p = phase(0.2, 0.35)
  return {
    opacity: p,
    transform: `translate(-50%, -50%) scale(${0.9 + p * 0.1})`,
  }
})

function rowStyle(index: number) {
  const count = Math.max(rowsData.value.length, 1)
  const start = 0.28 + (index / count) * 0.38
  const p = phase(start, 0.3)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 7}px)`,
  }
}
</script>

<template>
  <div
    class="two-column-compare"
    :style="{
      '--left-accent': leftAccent,
      '--right-accent': rightAccent,
    }"
  >
    <div ref="src" style="display:none"><slot /></div>
    <h3 v-if="title" class="diagram-title" :style="titleStyle">{{ title }}</h3>

    <div class="comparison">
      <div class="headers">
        <article class="header-card header-left" :style="headerStyle('left')">
          <span class="header-rule" />
          <div>
            <h4>{{ leftData.title }}</h4>
            <p v-if="leftData.subtitle">{{ leftData.subtitle }}</p>
          </div>
        </article>

        <div class="header-gutter" aria-hidden="true" />

        <article class="header-card header-right" :style="headerStyle('right')">
          <span class="header-rule" />
          <div>
            <h4>{{ rightData.title }}</h4>
            <p v-if="rightData.subtitle">{{ rightData.subtitle }}</p>
          </div>
        </article>

        <span class="versus" :style="badgeStyle">{{ dividerLabel }}</span>
      </div>

      <div class="rows">
        <div
          v-for="(row, index) in rowsData"
          :key="`${row.criterion}-${index}`"
          class="compare-row"
          :style="rowStyle(index)"
        >
          <div class="value-cell left-cell" :class="{ winner: row.leftGood }">
            <span class="value">{{ row.left }}</span>
          </div>

          <div class="criterion">
            <span>{{ row.criterion }}</span>
          </div>

          <div class="value-cell right-cell" :class="{ winner: row.rightGood }">
            <span class="value">{{ row.right }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.two-column-compare {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.diagram-title {
  margin: 0 0 0.8rem;
  color: #1C2530;
  font-size: clamp(1.05rem, 2.1vw, 1.35rem);
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.015em;
  will-change: opacity, transform;
}

.comparison {
  width: 100%;
}

.headers,
.compare-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(7.5rem, 18%, 10.5rem) minmax(0, 1fr);
}

.headers {
  position: relative;
  align-items: stretch;
  margin-bottom: 0.55rem;
}

.header-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 5.2rem;
  align-items: center;
  overflow: hidden;
  box-sizing: border-box;
  padding: 0.85rem 1rem;
  border: 1px solid #DFE3E8;
  border-radius: 8px;
  background: #F5F6F8;
  will-change: opacity, transform;
}

.header-left {
  grid-column: 1;
  background:
    linear-gradient(color-mix(in srgb, var(--left-accent) 8%, transparent), color-mix(in srgb, var(--left-accent) 8%, transparent)),
    #F5F6F8;
}

.header-right {
  grid-column: 3;
  background:
    linear-gradient(color-mix(in srgb, var(--right-accent) 8%, transparent), color-mix(in srgb, var(--right-accent) 8%, transparent)),
    #F5F6F8;
}

.header-rule {
  align-self: stretch;
  flex: 0 0 3px;
  margin-right: 0.75rem;
  border-radius: 3px;
  background: var(--left-accent);
}

.header-right .header-rule {
  background: var(--right-accent);
}

.header-card h4 {
  margin: 0;
  color: #1C2530;
  font-size: clamp(0.94rem, 1.8vw, 1.12rem);
  font-weight: 700;
  line-height: 1.2;
}

.header-card p {
  margin: 0.28rem 0 0;
  color: #5A6472;
  font-size: clamp(0.78rem, 1.35vw, 0.9rem);
  line-height: 1.35;
}

.header-gutter {
  grid-column: 2;
}

.versus {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 2;
  display: grid;
  min-width: 2.25rem;
  min-height: 2.25rem;
  place-items: center;
  box-sizing: border-box;
  padding: 0.3rem 0.5rem;
  border: 1px solid #DFE3E8;
  border-radius: 999px;
  background: #FFFFFF;
  color: #5A6472;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1;
  text-transform: uppercase;
  box-shadow: 0 2px 8px color-mix(in srgb, #1C2530 7%, transparent);
  will-change: opacity, transform;
}

.rows {
  border-top: 1px solid #DFE3E8;
}

.compare-row {
  position: relative;
  min-height: 3.25rem;
  align-items: stretch;
  border-bottom: 1px solid #DFE3E8;
  will-change: opacity, transform;
}

.value-cell,
.criterion {
  display: flex;
  min-width: 0;
  align-items: center;
  box-sizing: border-box;
}

.value-cell {
  gap: 0.5rem;
  padding: 0.65rem 0.85rem;
  color: #1C2530;
  font-size: clamp(0.8rem, 1.4vw, 0.94rem);
  font-weight: 520;
  line-height: 1.3;
}

.left-cell {
  justify-content: flex-end;
  text-align: right;
}

.right-cell {
  justify-content: flex-start;
  text-align: left;
}

/* winner cells: no checkmark and no shading (removed per design request) */

.value {
  overflow-wrap: anywhere;
}

.check {
  display: inline-grid;
  flex: 0 0 1.25rem;
  width: 1.25rem;
  height: 1.25rem;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, currentColor 10%, #FFFFFF);
  color: var(--left-accent);
  font-size: 0.76rem;
  font-weight: 800;
  line-height: 1;
}

.right-cell .check {
  color: var(--right-accent);
}

.criterion {
  position: relative;
  justify-content: center;
  padding: 0.55rem 0.65rem;
  border-right: 1px solid #DFE3E8;
  border-left: 1px solid #DFE3E8;
  background: #FFFFFF;
  color: #5A6472;
  font-size: clamp(0.75rem, 1.25vw, 0.86rem);
  font-weight: 650;
  line-height: 1.25;
  text-align: center;
}

@media (max-width: 620px) {
  .headers,
  .compare-row {
    grid-template-columns: minmax(0, 1fr) 6.2rem minmax(0, 1fr);
  }

  .header-card {
    min-height: 4.7rem;
    padding: 0.7rem;
  }

  .header-rule {
    margin-right: 0.55rem;
  }

  .value-cell {
    padding: 0.55rem 0.5rem;
  }

  .criterion {
    padding: 0.5rem 0.35rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .diagram-title,
  .header-card,
  .versus,
  .compare-row {
    will-change: auto;
  }
}
</style>
