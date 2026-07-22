<catalog>
use: A sequential narrowing process with measurable drop-off at each stage (e.g. a conversion funnel).
looks: Stacked trapezoid segments narrowing top to bottom, each labelled with its value and optional conversion rate.
fill: bullet list ordered top→bottom; each item is a stage, "label | value" (or "label: value"); optional 3rd segment "| note" sets a custom right callout instead of the auto conversion rate.
</catalog>
<!--
FunnelDiagram.vue

Props:
- stages: Array<{ label: string; value: number; color?: string }> ordered top→bottom.
- unit: String appended to formatted values.
- title: Optional diagram title.
- showRate: Show step-to-step conversion and percentage of top.
- animate: Enable the subtle enter animation.

Example:
<FunnelDiagram
  title="Sales conversion"
  unit=""
  :stages="[
    { label: 'Visitors', value: 12000 },
    { label: 'Leads', value: 3600 },
    { label: 'Qualified', value: 1440 },
    { label: 'Customers', value: 432 }
  ]"
  :show-rate="true"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type FunnelStage = {
  label: string
  value: number
  color?: string
  note?: string
}

const props = defineProps({
  stages: {
    type: Array as () => FunnelStage[],
    default: () => [
      { label: 'Visitors', value: 12000 },
      { label: 'Leads', value: 3600 },
      { label: 'Qualified', value: 1440 },
      { label: 'Customers', value: 432 },
    ],
  },
  unit: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  showRate: {
    type: Boolean,
    default: true,
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
  if (!props.animate || reduced) {
    progress.value = 1
    return
  }
  cancelAnimationFrame(raf)
  progress.value = 0
  const started = performance.now()
  const duration = 700

  const frame = (now: number) => {
    const t = Math.min(1, (now - started) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1)
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

// Nested-list authoring: each top <li> is a stage ("label | value" or "label: value").
// An optional 3rd segment ("label | value | note") sets a custom right-hand callout,
// overriding the auto-computed conversion rate for that stage.
const { src, parsed } = useSlotTree()
function toNumber(raw) {
  const n = Number(String(raw ?? '').replace(/[^0-9.\-]/g, ''))
  return Number.isFinite(n) ? n : 0
}
function mapToShape(tree) {
  return tree.map(node => {
    const { color, parts, text } = parseLabel(node.text)
    let label = parts[0] || ''
    let rawVal = parts[1]
    if (rawVal == null && text.includes(':')) {
      const i = text.lastIndexOf(':')
      label = text.slice(0, i).trim()
      rawVal = text.slice(i + 1).trim()
    }
    const stage: FunnelStage = { label, value: toNumber(rawVal) }
    if (color) stage.color = color
    if (parts[2]) stage.note = parts[2]
    return stage
  })
}
const stagesData = computed<FunnelStage[]>(() => (parsed.value ? mapToShape(parsed.value) : props.stages))

const safeStages = computed(() =>
  stagesData.value
    .filter(stage => stage && Number.isFinite(Number(stage.value)))
    .map(stage => ({
      ...stage,
      value: Math.max(0, Number(stage.value)),
    })),
)

const viewWidth = 920
const titleHeight = computed(() => props.title ? 48 : 12)
const stageHeight = 76
const stageGap = 3
const funnelCenter = 390
const maxFunnelWidth = 610
const minFunnelWidth = 150
const annotationX = 730

const viewHeight = computed(() =>
  Math.max(150, titleHeight.value + safeStages.value.length * (stageHeight + stageGap) + 18),
)

const topValue = computed(() =>
  Math.max(1, safeStages.value[0]?.value ?? 1),
)

const widthFor = (value: number) => {
  const ratio = Math.max(0, Math.min(1, value / topValue.value))
  return minFunnelWidth + (maxFunnelWidth - minFunnelWidth) * ratio
}

const segments = computed(() =>
  safeStages.value.map((stage, index) => {
    const topWidth = widthFor(stage.value)
    const next = safeStages.value[index + 1]
    const bottomWidth = next
      ? widthFor(next.value)
      : Math.max(minFunnelWidth * 0.72, topWidth * 0.72)

    const y = titleHeight.value + index * (stageHeight + stageGap)
    const x1 = funnelCenter - topWidth / 2
    const x2 = funnelCenter + topWidth / 2
    const x3 = funnelCenter + bottomWidth / 2
    const x4 = funnelCenter - bottomWidth / 2
    const previous = safeStages.value[index - 1]
    const stepRate = previous?.value
      ? (stage.value / previous.value) * 100
      : 100
    const totalRate = (stage.value / topValue.value) * 100

    return {
      ...stage,
      index,
      y,
      centerY: y + stageHeight / 2,
      points: `${x1},${y} ${x2},${y} ${x3},${y + stageHeight} ${x4},${y + stageHeight}`,
      fill: stage.color || `var(--funnel-${Math.min(index + 1, 6)})`,
      stepRate,
      totalRate,
    }
  }),
)

const formatValue = (value: number) =>
  `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}${props.unit}`

const formatRate = (value: number) =>
  `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}%`

const itemProgress = (index: number, label = false) => {
  const count = Math.max(1, safeStages.value.length)
  const stagger = index * (0.38 / count) + (label ? 0.12 : 0)
  return Math.max(0, Math.min(1, (progress.value - stagger) / (1 - stagger)))
}

const segmentStyle = (index: number) => {
  const p = itemProgress(index)
  return {
    opacity: p,
    transform: `translate(${funnelCenter}px, ${segments.value[index]?.centerY ?? 0}px) scale(${0.96 + p * 0.04}) translate(${-funnelCenter}px, ${-(segments.value[index]?.centerY ?? 0)}px)`,
  }
}

const labelStyle = (index: number) => {
  const p = itemProgress(index, true)
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 5}px)`,
  }
}
</script>

<template>
  <div class="funnel-wrap">
    <div ref="src" style="display:none"><slot /></div>
    <svg
      class="funnel-diagram"
      :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
    role="img"
    :aria-label="title || 'Conversion funnel'"
    preserveAspectRatio="xMidYMid meet"
  >
    <text
      v-if="title"
      class="diagram-title"
      x="390"
      y="25"
      text-anchor="middle"
    >
      {{ title }}
    </text>

    <g v-if="segments.length">
      <g
        v-for="segment in segments"
        :key="`${segment.label}-${segment.index}`"
      >
        <polygon
          class="segment"
          :points="segment.points"
          :fill="segment.fill"
          :style="segmentStyle(segment.index)"
        />

        <g
          class="segment-copy"
          :style="labelStyle(segment.index)"
        >
          <text
            class="stage-label"
            :x="funnelCenter"
            :y="segment.centerY - 5"
            text-anchor="middle"
          >
            {{ segment.label }}
          </text>
          <text
            class="stage-value"
            :x="funnelCenter"
            :y="segment.centerY + 17"
            text-anchor="middle"
          >
            {{ formatValue(segment.value) }}
          </text>
        </g>

        <g
          v-if="showRate || segment.note"
          class="rate-copy"
          :style="labelStyle(segment.index)"
        >
          <line
            class="rate-rule"
            x1="704"
            :y1="segment.centerY"
            x2="720"
            :y2="segment.centerY"
          />
          <text
            v-if="segment.note"
            class="rate-primary"
            :x="annotationX"
            :y="segment.centerY + 5"
          >
            {{ segment.note }}
          </text>
          <template v-else>
            <text
              class="rate-primary"
              :x="annotationX"
              :y="segment.centerY - 3"
            >
              {{ segment.index === 0 ? 'Baseline' : `${formatRate(segment.stepRate)} from prior` }}
            </text>
            <text
              class="rate-secondary"
              :x="annotationX"
              :y="segment.centerY + 17"
            >
              {{ formatRate(segment.totalRate) }} of top
            </text>
          </template>
        </g>
      </g>
    </g>

    <text
      v-else
      class="empty-state"
      x="460"
      :y="viewHeight / 2"
      text-anchor="middle"
    >
      No funnel stages
    </text>
    </svg>
  </div>
</template>

<style scoped>
.funnel-diagram {
  --funnel-1: #1D3E5E;
  --funnel-2: #28527A;
  --funnel-3: #3F7D74;
  --funnel-4: #7FA8CF;
  --funnel-5: #9AA7B5;
  --funnel-6: #C9A66B;

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
  font-size: 18px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.segment {
  stroke: #FFFFFF;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  transform-box: view-box;
  transform-origin: center;
}

.segment-copy,
.rate-copy {
  pointer-events: none;
}

.stage-label,
.stage-value {
  fill: #FFFFFF;
  paint-order: stroke;
  stroke: rgb(0 0 0 / 12%);
  stroke-width: 1.5px;
  stroke-linejoin: round;
}

.stage-label {
  font-size: 15px;
  font-weight: 650;
}

.stage-value {
  font-size: 14px;
  font-weight: 500;
}

.rate-rule {
  stroke: #5A6472;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.rate-primary {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 600;
}

.rate-secondary {
  fill: #5A6472;
  font-size: 12px;
  font-weight: 450;
}

.empty-state {
  fill: #5A6472;
  font-size: 14px;
}
</style>
