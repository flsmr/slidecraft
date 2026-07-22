<catalog>
use: Comparing one or more entities across several dimensions at once (e.g. a capability profile).
looks: A polygon per series plotted across radial axes on a shared spider-web grid.
fill: prop-only; :axes=[…], :series=[{name, values:[…]}].
</catalog>
<!--
RadarChart.vue

Props:
- axes: string[] — axis labels arranged clockwise.
- series: Array<{ name: string; color?: string; values: number[] }> — values aligned to axes.
- max: number — shared axis maximum; defaults to 100. Set to 0 for a nice auto maximum.
- unit: string — suffix used for numeric values and accessibility text.
- title: string — chart title.
- levels: number — number of concentric grid rings.
- animate: boolean — enables the subtle enter animation.

Usage:
<RadarChart
  title="Capability profile"
  :axes="['Strategy', 'Design', 'Delivery', 'Data', 'Operations', 'People']"
  :series="[
    { name: 'Current', values: [72, 84, 66, 58, 76, 69] },
    { name: 'Target', values: [90, 92, 86, 82, 88, 85] }
  ]"
  :max="100"
  unit="%"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type RadarSeries = {
  name: string
  color?: string
  values: number[]
}

const props = defineProps({
  axes: {
    type: Array as () => string[],
    default: () => ['Strategy', 'Design', 'Delivery', 'Data', 'Operations', 'People'],
  },
  series: {
    type: Array as () => RadarSeries[],
    default: () => [
      { name: 'Current', values: [72, 84, 66, 58, 76, 69] },
      { name: 'Target', values: [90, 92, 86, 82, 88, 85] },
    ],
  },
  max: {
    type: Number,
    default: 100,
  },
  unit: {
    type: String,
    default: '%',
  },
  title: {
    type: String,
    default: 'Capability profile',
  },
  levels: {
    type: Number,
    default: 4,
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

const width = 760
const height = 500
const centerX = 380
const centerY = 238
const radius = 154
const palette = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
  '#7FA8CF',
  '#9AA7B5',
  '#C9A66B',
]

const axisCount = computed(() => Math.max(3, props.axes.length))
const ringCount = computed(() => Math.max(1, Math.round(props.levels)))

function niceCeil(value: number) {
  if (!Number.isFinite(value) || value <= 0) return 100
  const exponent = Math.floor(Math.log10(value))
  const magnitude = 10 ** exponent
  const fraction = value / magnitude
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return nice * magnitude
}

const chartMax = computed(() => {
  if (Number.isFinite(props.max) && props.max > 0) return props.max
  const largest = Math.max(
    0,
    ...props.series.flatMap(item =>
      item.values.map(value => Number.isFinite(value) ? value : 0),
    ),
  )
  return niceCeil(largest)
})

function angleAt(index: number) {
  return -Math.PI / 2 + (index * Math.PI * 2) / axisCount.value
}

function pointAt(index: number, distance: number) {
  const angle = angleAt(index)
  return {
    x: centerX + Math.cos(angle) * distance,
    y: centerY + Math.sin(angle) * distance,
  }
}

function pointsString(points: Array<{ x: number; y: number }>) {
  return points.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')
}

const rings = computed(() =>
  Array.from({ length: ringCount.value }, (_, index) => {
    const ratio = (index + 1) / ringCount.value
    return {
      ratio,
      points: pointsString(
        Array.from({ length: axisCount.value }, (_, axis) =>
          pointAt(axis, radius * ratio),
        ),
      ),
    }
  }),
)

const spokes = computed(() =>
  Array.from({ length: axisCount.value }, (_, index) => ({
    end: pointAt(index, radius),
  })),
)

const labels = computed(() =>
  Array.from({ length: axisCount.value }, (_, index) => {
    const point = pointAt(index, radius + 31)
    const cosine = Math.cos(angleAt(index))
    const sine = Math.sin(angleAt(index))
    return {
      text: props.axes[index] ?? `Axis ${index + 1}`,
      x: point.x,
      y: point.y,
      anchor: cosine > 0.25 ? 'start' : cosine < -0.25 ? 'end' : 'middle',
      baseline: sine > 0.55 ? 'hanging' : sine < -0.55 ? 'auto' : 'middle',
    }
  }),
)

const renderedSeries = computed(() =>
  props.series.map((item, seriesIndex) => {
    const color = item.color || palette[seriesIndex % palette.length]
    const points = Array.from({ length: axisCount.value }, (_, axisIndex) => {
      const raw = Number(item.values[axisIndex] ?? 0)
      const value = Number.isFinite(raw) ? Math.max(0, Math.min(chartMax.value, raw)) : 0
      const ratio = chartMax.value > 0 ? value / chartMax.value : 0
      return {
        ...pointAt(axisIndex, radius * ratio * progress.value),
        value,
      }
    })
    return {
      name: item.name || `Series ${seriesIndex + 1}`,
      color,
      points,
      polygon: pointsString(points),
    }
  }),
)

const legendY = computed(() => height - 28)
const legendItems = computed(() => {
  const itemWidth = Math.min(180, width / Math.max(1, props.series.length))
  const totalWidth = itemWidth * props.series.length
  return renderedSeries.value.map((item, index) => ({
    ...item,
    x: (width - totalWidth) / 2 + index * itemWidth,
  }))
})

const description = computed(() =>
  renderedSeries.value
    .map(item =>
      `${item.name}: ${item.points
        .map((point, index) => `${props.axes[index] ?? `Axis ${index + 1}`} ${point.value}${props.unit}`)
        .join(', ')}`,
    )
    .join('. '),
)
</script>

<template>
  <div class="radar-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-labelledby="`${titleId} ${descriptionId}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <title :id="titleId">{{ title }}</title>
      <desc :id="descriptionId">{{ description }}</desc>

      <text
        v-if="title"
        class="chart-title"
        :x="width / 2"
        y="25"
        text-anchor="middle"
      >
        {{ title }}
      </text>

      <g class="grid">
        <polygon
          v-for="(ring, index) in rings"
          :key="`ring-${index}`"
          :points="ring.points"
        />
        <line
          v-for="(spoke, index) in spokes"
          :key="`spoke-${index}`"
          :x1="centerX"
          :y1="centerY"
          :x2="spoke.end.x"
          :y2="spoke.end.y"
        />
      </g>

      <g class="axis-labels">
        <text
          v-for="(label, index) in labels"
          :key="`label-${index}`"
          :x="label.x"
          :y="label.y"
          :text-anchor="label.anchor"
          :dominant-baseline="label.baseline"
        >
          {{ label.text }}
        </text>
      </g>

      <g
        v-for="(item, seriesIndex) in renderedSeries"
        :key="`${item.name}-${seriesIndex}`"
        class="series"
      >
        <polygon
          class="series-area"
          :points="item.polygon"
          :stroke="item.color"
          :fill="item.color"
          :fill-opacity="0.15 * progress"
        />
        <circle
          v-for="(point, pointIndex) in item.points"
          :key="`point-${pointIndex}`"
          class="vertex"
          :cx="point.x"
          :cy="point.y"
          :r="3.2 * progress"
          :fill="item.color"
        >
          <title>
            {{ item.name }} — {{ axes[pointIndex] ?? `Axis ${pointIndex + 1}` }}:
            {{ point.value }}{{ unit }}
          </title>
        </circle>
      </g>

      <g v-if="series.length > 1" class="legend">
        <g
          v-for="(item, index) in legendItems"
          :key="`legend-${index}`"
          :transform="`translate(${item.x} ${legendY})`"
        >
          <line x1="0" y1="0" x2="22" y2="0" :stroke="item.color" />
          <circle cx="11" cy="0" r="3" :fill="item.color" />
          <text x="30" y="0" dominant-baseline="middle">{{ item.name }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<script lang="ts">
let radarChartId = 0
export default {
  name: 'RadarChart',
  data() {
    const id = ++radarChartId
    return {
      titleId: `radar-chart-title-${id}`,
      descriptionId: `radar-chart-description-${id}`,
    }
  },
}
</script>

<style scoped>
.radar-chart {
  width: 100%;
  height: auto;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.chart-title {
  fill: #1C2530;
  font-size: 17px;
  font-weight: 650;
}

.grid polygon,
.grid line {
  fill: none;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.axis-labels text {
  fill: #5A6472;
  font-size: 13px;
  font-weight: 500;
}

.series-area {
  stroke-width: 2.25;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.vertex {
  stroke: #FFFFFF;
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.legend line {
  stroke-width: 2.25;
  vector-effect: non-scaling-stroke;
}

.legend text {
  fill: #5A6472;
  font-size: 12px;
}

text {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-variant-numeric: tabular-nums;
}
</style>
