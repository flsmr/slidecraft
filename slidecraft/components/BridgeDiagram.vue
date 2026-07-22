<catalog>
use: Connecting two states or concepts across a gap, with the enablers that close it.
looks: Two outer pillars joined by a spanning deck, with optional enabler supports over the middle gap.
fill: 1st item = the "from" pillar, last item = the "to" pillar (each "label | desc"); middle items are the enabler pillars.
</catalog>
<!--
BridgeDiagram.vue

Connect two concepts across a gap with a bridge. Non-overlapping layout: two outer pillars,
a deck spanning between their tops, and optional enabler supports strictly in the middle region.

Props:
- from: { label, desc? } — left pillar concept.
- to:   { label, desc? } — right pillar concept (emphasised).
- bridge: { label, pillars?: string[] } — deck label + optional intermediate enablers.
- gapLabel?: string — caption in the chasm below.
- title?: string — optional heading.
- animate: boolean — default true.

Usage:
<BridgeDiagram
  :from="{ label: 'Current state', desc: 'Where we are today' }"
  :to="{ label: 'Target state', desc: 'Where we need to be' }"
  :bridge="{ label: 'Transformation programme', pillars: ['Technology', 'Process', 'People'] }"
  gap-label="The gap"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type Concept = {
  label: string
  desc?: string
}

type Bridge = {
  label: string
  pillars?: string[]
}

const props = withDefaults(defineProps<{
  from?: Concept
  to?: Concept
  bridge?: Bridge
  gapLabel?: string
  title?: string
  animate?: boolean
}>(), {
  from: () => ({
    label: 'Current state',
    desc: 'Where we are today',
  }),
  to: () => ({
    label: 'Target state',
    desc: 'Where we need to be',
  }),
  bridge: () => ({
    label: 'Transformation programme',
    pillars: ['Technology', 'Process', 'People'],
  }),
  gapLabel: 'The gap',
  title: '',
  animate: true,
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); progress.value=0; const start=performance.now(); const d=700; const tick=(now)=>{const t=Math.min(1,(now-start)/d);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: first <li> = from, last <li> = to (each "label | desc"); the
// middle <li> become the enabler pillars. The bridge (deck) label stays a prop.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  if (tree.length < 2) return { from: props.from, to: props.to, bridge: props.bridge }
  const concept = (n, fb: Concept): Concept => {
    const { parts } = parseLabel(n.text)
    const c: Concept = { label: parts[0] || fb.label }
    if (parts[1]) c.desc = parts[1]
    return c
  }
  const from = concept(tree[0], props.from)
  const to = concept(tree[tree.length - 1], props.to)
  const middle = tree.slice(1, -1).map(n => parseLabel(n.text).parts[0] || n.text)
  const bridge = { label: props.bridge.label, pillars: middle.length ? middle : props.bridge.pillars }
  return { from, to, bridge }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : { from: props.from, to: props.to, bridge: props.bridge }))
const fromData = computed<Concept>(() => model.value.from)
const toData = computed<Concept>(() => model.value.to)
const bridgeData = computed<Bridge>(() => model.value.bridge)

const clamp01 = (value: number) => Math.max(0, Math.min(1, value))

const pillarProgress = computed(() => clamp01(progress.value / 0.42))
const deckProgress = computed(() => clamp01((progress.value - 0.28) / 0.42))
const supportProgress = computed(() => clamp01((progress.value - 0.62) / 0.38))

const deck = {
  x1: 250,
  x2: 750,
  y: 190,
}

const pillar = {
  top: 190,
  bottom: 410,
  width: 210,
  cardY: 218,
  cardHeight: 116,
}

const fromX = 40
const toX = 750

const enablers = computed(() =>
  (bridgeData.value.pillars ?? [])
    .map(label => String(label).trim())
    .filter(Boolean),
)

const supportBoxes = computed(() => {
  const labels = enablers.value
  const count = labels.length

  if (!count)
    return []

  const regionLeft = 278
  const regionRight = 722
  const regionWidth = regionRight - regionLeft
  const slotWidth = regionWidth / count
  const gap = Math.min(18, Math.max(8, slotWidth * 0.12))
  const width = Math.min(132, Math.max(48, slotWidth - gap))
  const height = 58
  const y = 282

  return labels.map((label, index) => {
    const center = regionLeft + slotWidth * (index + 0.5)
    return {
      label,
      x: center - width / 2,
      y,
      width,
      height,
      center,
    }
  })
})

const bridgePillWidth = computed(() =>
  Math.min(310, Math.max(176, bridgeData.value.label.length * 8.2 + 34)),
)

const bridgePillX = computed(() => 500 - bridgePillWidth.value / 2)

const titleLines = computed(() => {
  if (!props.title)
    return []

  const words = props.title.trim().split(/\s+/)
  const lines: string[] = []
  let line = ''

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (candidate.length > 72 && line) {
      lines.push(line)
      line = word
    }
    else {
      line = candidate
    }
  }

  if (line)
    lines.push(line)

  return lines.slice(0, 2)
})

function wrappedLines(text: string | undefined, maxChars = 25, maxLines = 3) {
  if (!text)
    return []

  const words = text.trim().split(/\s+/)
  const lines: string[] = []
  let line = ''

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (candidate.length > maxChars && line) {
      lines.push(line)
      line = word
      if (lines.length === maxLines - 1)
        break
    }
    else {
      line = candidate
    }
  }

  if (line && lines.length < maxLines)
    lines.push(line)

  return lines
}
</script>

<template>
  <div class="bridge-diagram">
    <div ref="src" style="display:none"><slot /></div>
    <svg
      class="bridge-svg"
      viewBox="0 0 1000 560"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      :aria-label="title || `${fromData.label} connected to ${toData.label} by ${bridgeData.label}`"
    >
      <title>{{ title || `${fromData.label} to ${toData.label}` }}</title>
      <desc>
        {{ bridgeData.label }} bridges {{ fromData.label }} and {{ toData.label }}.
      </desc>

      <g v-if="titleLines.length" class="diagram-title">
        <text
          v-for="(line, index) in titleLines"
          :key="line"
          x="500"
          :y="48 + index * 24"
          text-anchor="middle"
        >
          {{ line }}
        </text>
      </g>

      <!-- Subtle chasm, kept below all cards and supports. -->
      <path
        class="chasm"
        d="M270 430 C340 414 397 446 458 430 C520 414 581 446 642 430 C684 419 713 421 730 430"
      />
      <g v-if="gapLabel" class="gap-label">
        <line x1="340" y1="476" x2="450" y2="476" />
        <text x="500" y="481" text-anchor="middle">{{ gapLabel }}</text>
        <line x1="550" y1="476" x2="660" y2="476" />
      </g>

      <!-- Pillars rise independently in fixed outer slots. -->
      <g
        class="pillar-group"
        :style="{
          transform: `translateY(${(1 - pillarProgress) * (pillar.bottom - pillar.top)}px)`,
          opacity: pillarProgress,
        }"
      >
        <line
          class="pillar-stem pillar-stem--from"
          :x1="fromX + pillar.width / 2"
          :x2="fromX + pillar.width / 2"
          :y1="pillar.top"
          :y2="pillar.bottom"
        />
        <rect
          class="pillar-cap"
          :x="fromX + 22"
          :y="pillar.bottom - 8"
          :width="pillar.width - 44"
          height="16"
          rx="8"
        />

        <rect
          class="concept-card concept-card--from"
          :x="fromX"
          :y="pillar.cardY"
          :width="pillar.width"
          :height="pillar.cardHeight"
          rx="8"
        />
        <line
          class="integrated-border integrated-border--from"
          :x1="fromX + 1"
          :x2="fromX + 1"
          :y1="pillar.cardY + 8"
          :y2="pillar.cardY + pillar.cardHeight - 8"
        />
        <text
          class="concept-label"
          :x="fromX + 20"
          :y="pillar.cardY + 34"
        >
          {{ fromData.label }}
        </text>
        <text
          v-if="fromData.desc"
          class="concept-desc"
          :x="fromX + 20"
          :y="pillar.cardY + 60"
        >
          <tspan
            v-for="(line, index) in wrappedLines(fromData.desc)"
            :key="line"
            :x="fromX + 20"
            :dy="index === 0 ? 0 : 19"
          >
            {{ line }}
          </tspan>
        </text>
      </g>

      <g
        class="pillar-group"
        :style="{
          transform: `translateY(${(1 - pillarProgress) * (pillar.bottom - pillar.top)}px)`,
          opacity: pillarProgress,
        }"
      >
        <line
          class="pillar-stem pillar-stem--to"
          :x1="toX + pillar.width / 2"
          :x2="toX + pillar.width / 2"
          :y1="pillar.top"
          :y2="pillar.bottom"
        />
        <rect
          class="pillar-cap"
          :x="toX + 22"
          :y="pillar.bottom - 8"
          :width="pillar.width - 44"
          height="16"
          rx="8"
        />

        <rect
          class="concept-card concept-card--to"
          :x="toX"
          :y="pillar.cardY"
          :width="pillar.width"
          :height="pillar.cardHeight"
          rx="8"
        />
        <line
          class="integrated-border integrated-border--to"
          :x1="toX + 1"
          :x2="toX + 1"
          :y1="pillar.cardY + 8"
          :y2="pillar.cardY + pillar.cardHeight - 8"
        />
        <text
          class="concept-label"
          :x="toX + 20"
          :y="pillar.cardY + 34"
        >
          {{ toData.label }}
        </text>
        <text
          v-if="toData.desc"
          class="concept-desc"
          :x="toX + 20"
          :y="pillar.cardY + 60"
        >
          <tspan
            v-for="(line, index) in wrappedLines(toData.desc)"
            :key="line"
            :x="toX + 20"
            :dy="index === 0 ? 0 : 19"
          >
            {{ line }}
          </tspan>
        </text>
      </g>

      <!-- Deck draws across after the pillars rise. -->
      <line
        class="deck-shadow"
        :x1="deck.x1"
        :x2="deck.x2"
        :y1="deck.y + 5"
        :y2="deck.y + 5"
        :style="{
          strokeDasharray: deck.x2 - deck.x1,
          strokeDashoffset: (1 - deckProgress) * (deck.x2 - deck.x1),
          opacity: deckProgress,
        }"
      />
      <line
        class="deck"
        :x1="deck.x1"
        :x2="deck.x2"
        :y1="deck.y"
        :y2="deck.y"
        :style="{
          strokeDasharray: deck.x2 - deck.x1,
          strokeDashoffset: (1 - deckProgress) * (deck.x2 - deck.x1),
          opacity: deckProgress,
        }"
      />

      <g
        class="bridge-label"
        :style="{ opacity: deckProgress }"
      >
        <rect
          :x="bridgePillX"
          :y="deck.y - 22"
          :width="bridgePillWidth"
          height="44"
          rx="22"
        />
        <text x="500" :y="deck.y + 5" text-anchor="middle">
          {{ bridgeData.label }}
        </text>
      </g>

      <!-- Enablers occupy only the protected middle region. -->
      <g
        v-for="box in supportBoxes"
        :key="box.label"
        class="support"
        :style="{
          opacity: supportProgress,
          transform: `translateY(${(1 - supportProgress) * -10}px)`,
        }"
      >
        <line
          class="support-line"
          :x1="box.center"
          :x2="box.center"
          :y1="deck.y + 8"
          :y2="box.y"
        />
        <circle
          class="support-joint"
          :cx="box.center"
          :cy="deck.y + 8"
          r="4"
        />
        <rect
          class="support-card"
          :x="box.x"
          :y="box.y"
          :width="box.width"
          :height="box.height"
          rx="8"
        />
        <line
          class="support-accent"
          :x1="box.x + 1"
          :x2="box.x + 1"
          :y1="box.y + 8"
          :y2="box.y + box.height - 8"
        />
        <text
          class="support-label"
          :x="box.center"
          :y="box.y + box.height / 2 + 5"
          text-anchor="middle"
          :textLength="box.label.length > 14 ? box.width - 24 : undefined"
          :lengthAdjust="box.label.length > 14 ? 'spacingAndGlyphs' : undefined"
        >
          {{ box.label }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.bridge-diagram {
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.bridge-svg {
  display: block;
  width: 100%;
  height: auto;
  max-width: 100%;
  overflow: visible;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.diagram-title text {
  fill: #1C2530;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.pillar-group,
.support {
  transform-box: fill-box;
  transform-origin: center bottom;
}

.pillar-stem {
  stroke-width: 10;
  stroke-linecap: round;
}

.pillar-stem--from {
  stroke: #DFE3E8;
}

.pillar-stem--to {
  stroke: #28527A;
  opacity: 0.34;
}

.pillar-cap {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.concept-card,
.support-card {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.integrated-border,
.support-accent {
  stroke-width: 5;
  stroke-linecap: round;
}

.integrated-border--from {
  stroke: #5A6472;
}

.integrated-border--to {
  stroke: #28527A;
}

.concept-label {
  fill: #1C2530;
  font-size: 16px;
  font-weight: 650;
}

.concept-desc {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 400;
}

.deck-shadow {
  stroke: #DFE3E8;
  stroke-width: 12;
  stroke-linecap: round;
}

.deck {
  stroke: #28527A;
  stroke-width: 4;
  stroke-linecap: round;
}

.bridge-label rect {
  fill: #FFFFFF;
  stroke: #28527A;
  stroke-width: 1;
}

.bridge-label text {
  fill: #1D3E5E;
  font-size: 15px;
  font-weight: 650;
}

.support-line {
  stroke: #DFE3E8;
  stroke-width: 2;
}

.support-joint {
  fill: #FFFFFF;
  stroke: #3F7D74;
  stroke-width: 2;
}

.support-accent {
  stroke: #3F7D74;
  stroke-width: 4;
}

.support-label {
  fill: #1C2530;
  font-size: 13px;
  font-weight: 600;
}

.chasm {
  fill: none;
  stroke: #DFE3E8;
  stroke-width: 2;
  stroke-dasharray: 5 8;
}

.gap-label line {
  stroke: #DFE3E8;
  stroke-width: 1;
}

.gap-label text {
  fill: #5A6472;
  font-family: 'Spectral', Georgia, 'Times New Roman', serif;
  font-size: 14px;
  font-style: italic;
}
</style>
