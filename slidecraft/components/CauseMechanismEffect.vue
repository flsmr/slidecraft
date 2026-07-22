<catalog>
use: A cause → mechanism → effect chain making the causal path explicit.
looks: Three linked stages left-to-right, each a labeled box with a short description.
fill: exactly 3 items (cause / mechanism / effect), each "label | desc".
</catalog>
<!--
CauseMechanismEffect.vue

Props:
- cause: { label: string, desc?: string }
- mechanism: { label: string, desc?: string }
- effect: { label: string, desc?: string }
- causeCaption: string — default "Cause"
- mechanismCaption: string — default "Mechanism"
- effectCaption: string — default "Effect"
- title?: string
- animate: boolean — default true

Usage:
<CauseMechanismEffect
  title="Why delivery slows"
  :cause="{ label: 'Rising demand', desc: 'Orders increase faster than forecast.' }"
  :mechanism="{ label: 'Capacity constraint', desc: 'Available production cannot absorb the added load.' }"
  :effect="{ label: 'Longer lead times', desc: 'Customers wait longer for delivery.' }"
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
  cause: {
    type: Object as () => Stage,
    default: () => ({
      label: 'Rising demand',
      desc: 'Orders increase faster than forecast.',
    }),
  },
  mechanism: {
    type: Object as () => Stage,
    default: () => ({
      label: 'Capacity constraint',
      desc: 'Available production cannot absorb the added load.',
    }),
  },
  effect: {
    type: Object as () => Stage,
    default: () => ({
      label: 'Longer lead times',
      desc: 'Customers wait longer for delivery.',
    }),
  },
  causeCaption: { type: String, default: 'Cause' },
  mechanismCaption: { type: String, default: 'Mechanism' },
  effectCaption: { type: String, default: 'Effect' },
  title: { type: String, default: '' },
  animate: { type: Boolean, default: true },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0

function animate(){
  if(!props.animate||reduced){progress.value=1;return}
  cancelAnimationFrame(raf)
  progress.value=0
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

// Nested-list authoring: 3 top <li> = cause / mechanism / effect ("label | desc").
const { src, parsed } = useSlotTree()
function toStage(n): Stage {
  const { parts } = parseLabel(n.text)
  const s: Stage = { label: parts[0] || '' }
  if (parts[1]) s.desc = parts[1]
  return s
}
function mapToShape(tree) {
  const t = tree.slice(0, 3)
  return {
    cause: t[0] ? toStage(t[0]) : props.cause,
    mechanism: t[1] ? toStage(t[1]) : props.mechanism,
    effect: t[2] ? toStage(t[2]) : props.effect,
  }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : { cause: props.cause, mechanism: props.mechanism, effect: props.effect }))

const stages = computed(() => [
  { caption: props.causeCaption, content: model.value.cause, kind: 'cause' },
  { caption: props.mechanismCaption, content: model.value.mechanism, kind: 'mechanism' },
  { caption: props.effectCaption, content: model.value.effect, kind: 'effect' },
])

function phase(index: number, start = 0.08, span = 0.34) {
  const delay = start + index * 0.22
  return Math.max(0, Math.min(1, (progress.value - delay) / span))
}

function cardStyle(index: number) {
  const p = phase(index)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 8}px) scale(${0.985 + p * 0.015})`,
  }
}

function arrowStyle(index: number) {
  const p = phase(index, 0.24, 0.25)
  return {
    opacity: p,
    '--draw': `${(1 - p) * 100}%`,
  }
}

const titleStyle = computed(() => ({
  opacity: Math.min(1, progress.value * 5),
  transform: `translateY(${(1 - Math.min(1, progress.value * 5)) * 5}px)`,
}))
</script>

<template>
  <section class="cme">
    <div ref="src" style="display:none"><slot /></div>
    <h3 v-if="title" class="cme__title" :style="titleStyle">{{ title }}</h3>

    <div class="cme__chain">
      <template v-for="(stage, index) in stages" :key="stage.kind">
        <article
          class="cme__card"
          :class="`cme__card--${stage.kind}`"
          :style="cardStyle(index)"
        >
          <div class="cme__caption">{{ stage.caption }}</div>
          <div class="cme__label">{{ stage.content.label }}</div>
          <p v-if="stage.content.desc" class="cme__desc">
            {{ stage.content.desc }}
          </p>
        </article>

        <div
          v-if="index < stages.length - 1"
          class="cme__arrow"
          :style="arrowStyle(index)"
          aria-hidden="true"
        >
          <svg viewBox="0 0 64 24" role="presentation">
            <path class="cme__arrow-line" pathLength="100" d="M3 12H55" />
            <path class="cme__arrow-head" pathLength="100" d="M47 4L56 12L47 20" />
          </svg>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.cme {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.cme__title {
  margin: 0 0 1rem;
  color: #1C2530;
  font-size: clamp(17px, 2vw, 22px);
  font-weight: 700;
  line-height: 1.2;
}

.cme__chain {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(42px, 6vw, 68px) minmax(0, 1.08fr) clamp(42px, 6vw, 68px) minmax(0, 1fr);
  align-items: stretch;
  width: 100%;
}

.cme__card {
  position: relative;
  min-width: 0;
  min-height: 132px;
  box-sizing: border-box;
  padding: 1rem 1.05rem 1.05rem;
  overflow: hidden;
  background: #F5F6F8;
  border: 1px solid #DFE3E8;
  border-left: 3px solid #5A6472;
  border-radius: 8px;
  transform-origin: center;
}

.cme__card--mechanism {
  background: #FFFFFF;
  border-left-color: #28527A;
  box-shadow: 0 5px 16px color-mix(in srgb, #28527A 10%, transparent);
}

.cme__card--effect {
  border-left-color: #3F7D74;
}

.cme__caption {
  margin-bottom: 0.55rem;
  color: #5A6472;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.cme__card--mechanism .cme__caption {
  color: #28527A;
}

.cme__card--effect .cme__caption {
  color: #3F7D74;
}

.cme__label {
  color: #1C2530;
  font-size: clamp(15px, 1.65vw, 18px);
  font-weight: 700;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.cme__desc {
  margin: 0.55rem 0 0;
  color: #5A6472;
  font-size: clamp(13px, 1.35vw, 15px);
  line-height: 1.42;
  overflow-wrap: anywhere;
}

.cme__arrow {
  --draw: 0%;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  color: #28527A;
}

.cme__arrow svg {
  display: block;
  width: 76%;
  max-width: 64px;
  overflow: visible;
}

.cme__arrow-line,
.cme__arrow-head {
  fill: none;
  stroke: currentColor;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 100;
  stroke-dashoffset: var(--draw);
}

@media (max-width: 680px) {
  .cme__chain {
    grid-template-columns: minmax(0, 1fr);
  }

  .cme__card {
    min-height: 0;
  }

  .cme__arrow {
    height: 42px;
  }

  .cme__arrow svg {
    width: 52px;
    transform: rotate(90deg);
  }
}
</style>
