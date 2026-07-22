<!--
IPODiagram.vue

Props:
- inputs: string[] — items entering the system
- processes: string[] — transformation steps
- outputs: string[] — resulting items
- inputLabel: string — input zone caption (default: "Input")
- processLabel: string — process zone caption (default: "Process")
- outputLabel: string — output zone caption (default: "Output")
- title: string — optional diagram title
- animate: boolean — enables the subtle enter animation (default: true)

Usage:
<IPODiagram
  title="Editorial Production"
  :inputs="['Research brief', 'Source material', 'Audience needs']"
  :processes="['Synthesize findings', 'Develop narrative', 'Review and refine']"
  :outputs="['Slide deck', 'Executive summary', 'Action plan']"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

const props = defineProps({
  inputs: {
    type: Array as () => string[],
    default: () => ['Customer requirements', 'Market research', 'Available resources'],
  },
  processes: {
    type: Array as () => string[],
    default: () => ['Analyse the inputs', 'Transform and validate', 'Prepare delivery'],
  },
  outputs: {
    type: Array as () => string[],
    default: () => ['Validated solution', 'Delivery package', 'Performance insights'],
  },
  inputLabel: {
    type: String,
    default: 'Input',
  },
  processLabel: {
    type: String,
    default: 'Process',
  },
  outputLabel: {
    type: String,
    default: 'Output',
  },
  title: {
    type: String,
    default: 'Input–Process–Output',
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0)
const { currentPage } = useNav()
const ctx = useSlideContext()
const reduced = typeof window !== 'undefined'
  && window.matchMedia
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches

let raf = 0

function animate() {
  cancelAnimationFrame(raf)
  if (!props.animate || reduced) {
    progress.value = 1
    return
  }

  progress.value = 0
  const duration = 700
  let started = 0

  const frame = (time: number) => {
    if (!started)
      started = time

    const linear = Math.min((time - started) / duration, 1)
    progress.value = 1 - Math.pow(1 - linear, 3)

    if (linear < 1)
      raf = requestAnimationFrame(frame)
  }

  raf = requestAnimationFrame(frame)
}

onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) })
watch(
  () => currentPage.value === unref(ctx.$page),
  (a, w) => {
    if (a && !w)
      animate()
  },
)
onBeforeUnmount(() => cancelAnimationFrame(raf))

// Nested-list authoring: 3 top <li> (Input / Process / Output), each nested = items.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  const keys = ['input', 'process', 'output']
  return tree.slice(0, 3).map((node, i) => ({
    key: keys[i],
    label: parseLabel(node.text).text,
    items: node.children.map(c => c.text),
  }))
}
const zones = computed(() => (parsed.value ? mapToShape(parsed.value) : [
  {
    key: 'input',
    label: props.inputLabel,
    items: props.inputs,
  },
  {
    key: 'process',
    label: props.processLabel,
    items: props.processes,
  },
  {
    key: 'output',
    label: props.outputLabel,
    items: props.outputs,
  },
]))

function reveal(start: number, span = 0.42) {
  return Math.max(0, Math.min(1, (progress.value - start) / span))
}

function zoneStyle(index: number) {
  const value = reveal(index * 0.16)
  return {
    opacity: value,
    transform: `translateX(${(1 - value) * 12}px) scale(${0.985 + value * 0.015})`,
  }
}

function arrowStyle(index: number) {
  const value = reveal(0.48 + index * 0.14, 0.3)
  return {
    opacity: value,
    transform: `translateX(${(1 - value) * -7}px) scaleX(${0.72 + value * 0.28})`,
  }
}
</script>

<template>
  <div class="ipo-diagram" role="group" :aria-label="title || 'Input Process Output diagram'">
    <div ref="src" style="display:none"><slot /></div>
    <h3 v-if="title" class="ipo-title">
      {{ title }}
    </h3>

    <div class="ipo-flow">
      <template v-for="(zone, index) in zones" :key="zone.key">
        <section
          class="ipo-zone"
          :class="`ipo-zone--${zone.key}`"
          :style="zoneStyle(index)"
          :aria-labelledby="`ipo-${zone.key}-heading`"
        >
          <header :id="`ipo-${zone.key}-heading`" class="ipo-header">
            <span class="ipo-header-mark" aria-hidden="true" />
            <span>{{ zone.label }}</span>
          </header>

          <div class="ipo-body">
            <ol class="ipo-list">
              <li v-for="(item, itemIndex) in zone.items" :key="`${zone.key}-${itemIndex}`">
                <span v-if="zone.key === 'process'" class="ipo-step">
                  {{ itemIndex + 1 }}
                </span>
                <span v-else class="ipo-bullet" aria-hidden="true" />
                <span>{{ item }}</span>
              </li>
            </ol>
          </div>
        </section>

        <div
          v-if="index < zones.length - 1"
          class="ipo-arrow"
          :style="arrowStyle(index)"
          aria-hidden="true"
        >
          <svg viewBox="0 0 72 36" focusable="false">
            <path class="ipo-arrow-line" d="M3 18H61" />
            <path class="ipo-arrow-head" d="M50 7L62 18 50 29" />
          </svg>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ipo-diagram {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.ipo-title {
  margin: 0 0 0.85rem;
  color: #1C2530;
  font-family: 'Spectral', Georgia, 'Times New Roman', serif, serif;
  font-size: clamp(1.05rem, 2.1vw, 1.42rem);
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.01em;
}

.ipo-flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(2.4rem, 6vw, 4.5rem) minmax(0, 1.08fr) clamp(2.4rem, 6vw, 4.5rem) minmax(0, 1fr);
  align-items: stretch;
  width: 100%;
}

.ipo-zone {
  display: flex;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-radius: 8px;
  background: #F5F6F8;
  box-shadow: 0 1px 2px color-mix(in srgb, #1C2530 5%, transparent);
  transform-origin: center;
  will-change: opacity, transform;
}

.ipo-zone--process {
  border-color: color-mix(in srgb, #28527A 30%, #DFE3E8);
  background: color-mix(in srgb, #28527A 6%, #F5F6F8);
}

.ipo-header {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-height: 2.55rem;
  padding: 0.55rem 0.8rem;
  border-bottom: 1px solid #DFE3E8;
  background: color-mix(in srgb, #5A6472 5%, #FFFFFF);
  font-size: clamp(0.82rem, 1.45vw, 0.96rem);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.025em;
}

.ipo-header-mark {
  width: 0.22rem;
  height: 1.15rem;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #5A6472;
}

.ipo-zone--process .ipo-header {
  background: color-mix(in srgb, #28527A 10%, #FFFFFF);
  color: #1D3E5E;
}

.ipo-zone--process .ipo-header-mark {
  background: #28527A;
}

.ipo-zone--output .ipo-header {
  background: color-mix(in srgb, #3F7D74 8%, #FFFFFF);
}

.ipo-zone--output .ipo-header-mark {
  background: #3F7D74;
}

.ipo-body {
  display: flex;
  flex: 1;
  align-items: center;
  padding: clamp(0.75rem, 1.7vw, 1.05rem);
}

.ipo-list {
  display: grid;
  width: 100%;
  margin: 0;
  padding: 0;
  gap: clamp(0.55rem, 1.2vw, 0.78rem);
  list-style: none;
}

.ipo-list li {
  display: grid;
  grid-template-columns: 1rem minmax(0, 1fr);
  align-items: start;
  gap: 0.48rem;
  color: #1C2530;
  font-size: clamp(0.8rem, 1.35vw, 0.94rem);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.ipo-bullet {
  width: 0.38rem;
  height: 0.38rem;
  margin-top: 0.42em;
  border-radius: 50%;
  background: #5A6472;
}

.ipo-zone--output .ipo-bullet {
  background: #3F7D74;
}

.ipo-step {
  display: inline-grid;
  width: 1rem;
  height: 1rem;
  place-items: center;
  border: 1px solid color-mix(in srgb, #28527A 42%, #DFE3E8);
  border-radius: 50%;
  color: #1D3E5E;
  font-size: 0.66rem;
  font-weight: 700;
  line-height: 1;
}

.ipo-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 0.28rem;
  color: #28527A;
  transform-origin: left center;
  will-change: opacity, transform;
}

.ipo-arrow svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.ipo-arrow-line,
.ipo-arrow-head {
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.ipo-arrow-line {
  stroke-width: 2;
}

.ipo-arrow-head {
  stroke-width: 2.4;
}

@media (max-width: 620px) {
  .ipo-flow {
    grid-template-columns: 1fr;
    gap: 0.55rem;
  }

  .ipo-arrow {
    height: 1.7rem;
    padding: 0;
    transform-origin: center;
  }

  .ipo-arrow svg {
    width: 2.8rem;
    transform: rotate(90deg);
  }

  .ipo-body {
    padding: 0.72rem 0.85rem;
  }
}
</style>
