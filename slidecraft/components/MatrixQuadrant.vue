<!--
MatrixQuadrant.vue

Props:
- title?: string
- xAxis: { label: string; lowLabel?: string; highLabel?: string }
- yAxis: { label: string; lowLabel?: string; highLabel?: string }
- quadrants: exactly four { title: string; desc?: string; color?: string }, ordered
  [top-left, top-right, bottom-left, bottom-right]
- items?: Array<{ label: string; x: number; y: number }> where x/y are clamped to 0..1
- animate?: boolean

Usage:
<MatrixQuadrant
  title="Initiative portfolio"
  :x-axis="{ label: 'Effort', lowLabel: 'Low', highLabel: 'High' }"
  :y-axis="{ label: 'Impact', lowLabel: 'Low', highLabel: 'High' }"
  :quadrants="[
    { title: 'Quick wins', desc: 'Prioritise now' },
    { title: 'Major projects', desc: 'Plan carefully' },
    { title: 'Fill-ins', desc: 'Do when capacity allows' },
    { title: 'Reconsider', desc: 'High cost, limited return' }
  ]"
  :items="[
    { label: 'Onboarding', x: 0.28, y: 0.82 },
    { label: 'Platform', x: 0.73, y: 0.76 }
  ]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type Axis = {
  label: string
  lowLabel?: string
  highLabel?: string
}

type Quadrant = {
  title: string
  desc?: string
  color?: string
}

type MatrixItem = {
  label: string
  x: number
  y: number
}

const props = defineProps({
  title: {
    type: String,
    default: 'Impact–Effort Matrix',
  },
  xAxis: {
    type: Object as () => Axis,
    default: () => ({
      label: 'Effort',
      lowLabel: 'Low',
      highLabel: 'High',
    }),
  },
  yAxis: {
    type: Object as () => Axis,
    default: () => ({
      label: 'Impact',
      lowLabel: 'Low',
      highLabel: 'High',
    }),
  },
  quadrants: {
    type: Array as () => Quadrant[],
    default: () => [
      { title: 'Quick wins', desc: 'High impact · low effort' },
      { title: 'Major projects', desc: 'High impact · high effort' },
      { title: 'Fill-ins', desc: 'Low impact · low effort' },
      { title: 'Reconsider', desc: 'Low impact · high effort' },
    ],
    validator: (value: Quadrant[]) => value.length === 4,
  },
  items: {
    type: Array as () => MatrixItem[],
    default: () => [
      { label: 'Simplify signup', x: 0.22, y: 0.78 },
      { label: 'New platform', x: 0.76, y: 0.82 },
      { label: 'Template refresh', x: 0.31, y: 0.28 },
      { label: 'Legacy migration', x: 0.79, y: 0.34 },
    ],
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

const quadrantDefaults = [
  { title: 'Quick wins', desc: 'High impact · low effort' },
  { title: 'Major projects', desc: 'High impact · high effort' },
  { title: 'Fill-ins', desc: 'Low impact · low effort' },
  { title: 'Reconsider', desc: 'Low impact · high effort' },
]

const normalizedQuadrants = computed(() =>
  quadrantDefaults.map((fallback, index) => props.quadrants[index] ?? fallback),
)

const quadrantColors = [
  '#3F7D74',
  '#28527A',
  '#B07D2B',
  '#9AA7B5',
]

const quadrantStyle = (quadrant: Quadrant, index: number) => {
  const start = index * 0.09
  const local = Math.max(0, Math.min(1, (progress.value - start) / 0.58))
  return {
    '--quadrant-color': quadrant.color || quadrantColors[index],
    opacity: local,
    transform: `scale(${0.975 + local * 0.025})`,
  }
}

const axisProgress = computed(() =>
  Math.max(0, Math.min(1, (progress.value - 0.12) / 0.62)),
)

const axisStyle = computed(() => ({
  strokeDashoffset: `${1 - axisProgress.value}`,
  opacity: axisProgress.value,
}))

const itemStyle = (item: MatrixItem, index: number) => {
  const start = 0.64 + index * 0.045
  const local = Math.max(0, Math.min(1, (progress.value - start) / 0.25))
  const x = Math.max(0.04, Math.min(0.96, Number(item.x) || 0))
  const y = Math.max(0.04, Math.min(0.96, Number(item.y) || 0))
  return {
    left: `${x * 100}%`,
    top: `${(1 - y) * 100}%`,
    opacity: local,
    transform: `translate(-50%, -50%) scale(${0.55 + local * 0.45})`,
  }
}
</script>

<template>
  <div class="matrix-quadrant">
    <h3 v-if="title" class="matrix-title">{{ title }}</h3>

    <div class="diagram">
      <div class="y-axis">
        <span class="axis-high">{{ yAxis.highLabel || 'High' }}</span>
        <strong>{{ yAxis.label }}</strong>
        <span class="axis-low">{{ yAxis.lowLabel || 'Low' }}</span>
      </div>

      <div class="plane-wrap">
        <div class="plane">
          <div
            v-for="(quadrant, index) in normalizedQuadrants"
            :key="`${quadrant.title}-${index}`"
            class="quadrant"
            :class="{ emphasized: index === 1 }"
            :style="quadrantStyle(quadrant, index)"
          >
            <span class="quadrant-bar" />
            <strong>{{ quadrant.title }}</strong>
            <span v-if="quadrant.desc">{{ quadrant.desc }}</span>
          </div>

          <svg class="axes" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <marker
                id="matrix-arrow"
                markerWidth="5"
                markerHeight="5"
                refX="4.2"
                refY="2.5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M0,0 L5,2.5 L0,5 Z" class="arrow-head" />
              </marker>
            </defs>
            <path
              d="M 0 50 H 99"
              class="axis-line"
              pathLength="1"
              marker-end="url(#matrix-arrow)"
              :style="axisStyle"
            />
            <path
              d="M 50 100 V 1"
              class="axis-line"
              pathLength="1"
              marker-end="url(#matrix-arrow)"
              :style="axisStyle"
            />
          </svg>

          <div class="items">
            <div
              v-for="(item, index) in items"
              :key="`${item.label}-${index}`"
              class="item"
              :style="itemStyle(item, index)"
            >
              <i />
              <span>{{ item.label }}</span>
            </div>
          </div>
        </div>

        <div class="x-axis">
          <span>{{ xAxis.lowLabel || 'Low' }}</span>
          <strong>{{ xAxis.label }}</strong>
          <span>{{ xAxis.highLabel || 'High' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.matrix-quadrant {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.matrix-title {
  margin: 0 0 0.65rem;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 1.05rem;
  font-weight: 650;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.diagram {
  display: grid;
  grid-template-columns: 3.5rem minmax(0, 1fr);
  align-items: stretch;
  width: 100%;
  max-width: 42rem;
  margin-inline: auto;
}

.plane-wrap {
  min-width: 0;
}

.plane {
  position: relative;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  width: min(100%, 34rem);
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-radius: 8px;
  background: #FFFFFF;
  box-shadow: 0 1px 2px color-mix(in srgb, #1C2530 5%, transparent);
}

.quadrant {
  position: relative;
  z-index: 1;
  min-width: 0;
  padding: clamp(0.7rem, 2.2vw, 1.15rem);
  overflow: hidden;
  border-right: 1px solid #DFE3E8;
  border-bottom: 1px solid #DFE3E8;
  background:
    linear-gradient(
      color-mix(in srgb, var(--quadrant-color) 8%, #F5F6F8),
      color-mix(in srgb, var(--quadrant-color) 4%, #F5F6F8)
    );
  transform-origin: center;
  will-change: opacity, transform;
}

.quadrant:nth-child(2n) {
  border-right: 0;
}

.quadrant:nth-child(n + 3) {
  border-bottom: 0;
}

.quadrant.emphasized {
  background:
    linear-gradient(
      color-mix(in srgb, #28527A 13%, #F5F6F8),
      color-mix(in srgb, #28527A 7%, #F5F6F8)
    );
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #28527A 18%, transparent);
}

.quadrant-bar {
  display: block;
  width: 2.1rem;
  height: 3px;
  margin-bottom: 0.55rem;
  border-radius: 999px;
  background: var(--quadrant-color);
}

.quadrant strong {
  display: block;
  max-width: 85%;
  font-size: clamp(0.82rem, 1.8vw, 1rem);
  font-weight: 650;
  line-height: 1.2;
}

.quadrant > span:last-child:not(.quadrant-bar) {
  display: block;
  max-width: 86%;
  margin-top: 0.3rem;
  color: #5A6472;
  font-size: clamp(0.72rem, 1.45vw, 0.84rem);
  line-height: 1.35;
}

.axes,
.items {
  position: absolute;
  z-index: 2;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.axis-line {
  fill: none;
  stroke: #28527A;
  stroke-width: 1.4;
  vector-effect: non-scaling-stroke;
}

.arrow-head {
  fill: #28527A;
}

.item {
  position: absolute;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 0.28rem;
  max-width: 42%;
  transform-origin: center;
  will-change: opacity, transform;
}

.item i {
  flex: 0 0 auto;
  width: 0.62rem;
  height: 0.62rem;
  border: 2px solid #FFFFFF;
  border-radius: 50%;
  background: #1D3E5E;
  box-shadow: 0 0 0 1px color-mix(in srgb, #1D3E5E 35%, transparent);
}

.item span {
  overflow: hidden;
  padding: 0.14rem 0.32rem;
  border: 1px solid color-mix(in srgb, #DFE3E8 80%, transparent);
  border-radius: 4px;
  background: color-mix(in srgb, #FFFFFF 90%, transparent);
  color: #1C2530;
  font-size: clamp(0.68rem, 1.35vw, 0.78rem);
  font-weight: 550;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-shadow: 0 1px 2px color-mix(in srgb, #1C2530 7%, transparent);
}

.x-axis {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  width: min(100%, 34rem);
  padding-top: 0.55rem;
  color: #5A6472;
  font-size: 0.78rem;
  line-height: 1;
}

.x-axis strong {
  color: #1C2530;
  font-size: 0.88rem;
  font-weight: 650;
}

.x-axis span:last-child {
  text-align: right;
}

.y-axis {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  margin-bottom: 1.85rem;
  color: #5A6472;
  font-size: 0.78rem;
}

.y-axis strong {
  color: #1C2530;
  font-size: 0.88rem;
  font-weight: 650;
  transform: rotate(-90deg);
  white-space: nowrap;
}

.y-axis span {
  position: absolute;
  left: 50%;
  white-space: nowrap;
  transform: translateX(-50%) rotate(-90deg);
}

.axis-high {
  top: 0.15rem;
}

.axis-low {
  bottom: 0.15rem;
}

@media (max-width: 520px) {
  .diagram {
    grid-template-columns: 2.8rem minmax(0, 1fr);
  }

  .quadrant {
    padding: 0.62rem;
  }

  .quadrant > span:last-child:not(.quadrant-bar) {
    display: none;
  }

  .item span {
    max-width: 6.5rem;
  }
}
</style>
