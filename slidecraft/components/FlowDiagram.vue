<catalog>
use: A linear process or pipeline with one clear direction of flow.
looks: Left-to-right boxes joined by single arrows.
fill: bullet list; each top-level item is a step, "title | short description".
</catalog>
<!--
FlowDiagram.vue

Props:
- steps: Array<{ title: string; desc?: string; color?: string }> — process steps.
- direction: 'horizontal' | 'vertical' — flow orientation. Default: 'horizontal'.
- numbered: boolean — shows numbered badges when true. Default: true.
- title?: string — optional heading above the flow.
- animate: boolean — enables the subtle enter animation. Default: true.

Usage:
<FlowDiagram
  title="Editorial workflow"
  :steps="[
    { title: 'Discover', desc: 'Frame the audience and need.' },
    { title: 'Design', desc: 'Shape the narrative and system.', color: '#B07D2B' },
    { title: 'Build', desc: 'Produce and review the material.' },
    { title: 'Publish', desc: 'Release, measure, and refine.' }
  ]"
  direction="horizontal"
  :numbered="true"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type FlowStep = {
  title: string
  desc?: string
  color?: string
}

const props = defineProps({
  steps: {
    type: Array as () => FlowStep[],
    default: () => [
      { title: 'Discover', desc: 'Clarify the audience, context, and desired outcome.' },
      { title: 'Define', desc: 'Turn findings into a focused plan.', color: '#B07D2B' },
      { title: 'Deliver', desc: 'Build, review, and refine the solution.', color: '#3F7D74' },
      { title: 'Measure', desc: 'Assess results and identify the next move.' },
    ],
  },
  direction: {
    type: String as () => 'horizontal' | 'vertical',
    default: 'horizontal',
    validator: (value: string) => ['horizontal', 'vertical'].includes(value),
  },
  numbered: {
    type: Boolean,
    default: true,
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

// Nested-list authoring: each top <li> is a step ("title | desc").
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    const { color, parts } = parseLabel(node.text)
    const step: FlowStep = { title: parts[0] || '' }
    if (parts[1]) step.desc = parts[1]
    if (color) step.color = color
    return step
  })
}
const stepsData = computed<FlowStep[]>(() => (parsed.value ? mapToShape(parsed.value) : props.steps))

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0

function animate(){
  if(!props.animate||reduced){progress.value=1;return}
  cancelAnimationFrame(raf)
  progress.value=0
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

const isVertical = computed(() => props.direction === 'vertical')

function reveal(index: number, kind: 'step' | 'arrow' = 'step') {
  const count = Math.max(stepsData.value.length, 1)
  const stagger = Math.min(0.42, (count - 1) * 0.09)
  const start = kind === 'arrow'
    ? Math.min(0.72, index * 0.09 + 0.07)
    : Math.min(0.68, index * 0.09)
  const local = Math.max(0, Math.min(1, (progress.value - start) / Math.max(0.2, 1 - stagger)))
  const distance = (1 - local) * 10

  return {
    opacity: local,
    transform: isVertical.value
      ? `translateY(${distance}px)`
      : `translateX(${distance}px)`,
  }
}

function stepColor(step: FlowStep, index: number) {
  if (index === stepsData.value.length - 1)
    return '#28527A'
  return step.color || '#28527A'
}
</script>

<template>
  <section
    class="flow-diagram"
    :class="[`is-${direction}`, { 'is-numbered': numbered }]"
    :aria-label="title || 'Process flow'"
  >
    <div ref="src" style="display:none"><slot /></div>
    <h3 v-if="title" class="flow-title">{{ title }}</h3>

    <div class="flow-track">
      <template v-for="(step, index) in stepsData" :key="`${step.title}-${index}`">
        <article
          class="flow-step"
          :class="{ 'is-final': index === stepsData.length - 1 }"
          :style="[
            reveal(index),
            { '--step-color': stepColor(step, index) },
          ]"
        >
          <span v-if="numbered" class="step-badge" aria-hidden="true">
            {{ index + 1 }}
          </span>

          <div class="step-copy">
            <h4 class="step-title">{{ step.title }}</h4>
            <p v-if="step.desc" class="step-desc">{{ step.desc }}</p>
          </div>
        </article>

        <div
          v-if="index < stepsData.length - 1"
          class="flow-arrow"
          :style="reveal(index, 'arrow')"
          aria-hidden="true"
        >
          <svg viewBox="0 0 24 24" role="presentation">
            <path d="M7 4.5 14.5 12 7 19.5" />
          </svg>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.flow-diagram {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.flow-title {
  margin: 0 0 0.85rem;
  color: #1C2530;
  font-size: clamp(16px, 1.45vw, 21px);
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.015em;
}

.flow-track {
  display: flex;
  width: 100%;
  max-width: 100%;
}

.is-horizontal .flow-track {
  align-items: stretch;
  flex-flow: row wrap;
  gap: 0.65rem 0;
}

.flow-step {
  --step-color: #28527A;
  position: relative;
  display: flex;
  box-sizing: border-box;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-left: 3px solid var(--step-color);
  border-radius: 8px;
  background: #F5F6F8;
  color: #1C2530;
  will-change: opacity, transform;
}

.is-horizontal .flow-step {
  flex: 1 1 9.5rem;
  min-height: 6.5rem;
  padding: 0.9rem 0.85rem;
}

.is-vertical .flow-track {
  flex-direction: column;
  align-items: stretch;
}

.is-vertical .flow-step {
  width: 100%;
  min-height: 4.7rem;
  padding: 0.8rem 1rem;
}

.flow-step.is-final {
  border-color: color-mix(in srgb, #28527A 42%, #DFE3E8);
  border-left-color: #28527A;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #28527A 8%, transparent);
}

.step-badge {
  display: inline-grid;
  flex: 0 0 auto;
  place-items: center;
  width: 1.65rem;
  height: 1.65rem;
  margin-right: 0.65rem;
  border: 1px solid var(--step-color);
  border-radius: 999px;
  color: var(--step-color);
  background: #FFFFFF;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.is-final .step-badge {
  color: #FFFFFF;
  background: #28527A;
}

.step-copy {
  min-width: 0;
}

.step-title {
  margin: 0;
  color: #1C2530;
  font-size: clamp(13px, 1.1vw, 16px);
  font-weight: 650;
  line-height: 1.3;
}

.step-desc {
  margin: 0.35rem 0 0;
  color: #5A6472;
  font-size: clamp(12.5px, 0.95vw, 14px);
  line-height: 1.42;
  overflow-wrap: anywhere;
}

.flow-arrow {
  display: grid;
  flex: 0 0 1.8rem;
  place-items: center;
  color: #5A6472;
  will-change: opacity, transform;
}

.flow-arrow svg {
  display: block;
  width: 1.15rem;
  height: 1.15rem;
  overflow: visible;
}

.flow-arrow path {
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.6;
}

.is-vertical .flow-arrow {
  width: 100%;
  height: 1.55rem;
  flex-basis: 1.55rem;
}

.is-vertical .flow-arrow svg {
  transform: rotate(90deg);
}

@media (max-width: 720px) {
  .is-horizontal .flow-track {
    flex-direction: column;
  }

  .is-horizontal .flow-step {
    width: 100%;
    min-height: auto;
  }

  .is-horizontal .flow-arrow {
    width: 100%;
    height: 1.55rem;
    flex-basis: 1.55rem;
  }

  .is-horizontal .flow-arrow svg {
    transform: rotate(90deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .flow-step,
  .flow-arrow {
    will-change: auto;
  }
}
</style>
