<catalog>
use: Showing a project schedule of tasks across lanes over time, with milestones and progress.
looks: Horizontal task bars positioned on a time axis, grouped into lanes, with progress fill and diamond milestones.
fill: prop-only; :tasks=[{name, start, end, lane, progress}], :milestones=[{label, at}].
</catalog>
<!--
GanttChart.vue

Props:
- tasks: Array<{ name, start, end, lane?, color?, progress?: number }> — task rows;
  start/end may be numbers or ISO dates ('YYYY-MM-DD').
- start: number|string — optional explicit timeline start.
- end: number|string — optional explicit timeline end.
- title: string — chart title.
- unit: string — suffix for numeric tick labels, e.g. 'wk'.
- milestones: Array<{ label, at }> — diamond markers.
- today: number|string|null — optional dashed vertical marker.
- animate: boolean — enables the subtle enter animation.

Example:
<GanttChart
  title="Website launch"
  unit="wk"
  :tasks="[
    { name: 'Discovery', start: 1, end: 2.5, lane: 'Plan', progress: 1 },
    { name: 'Design', start: 2, end: 5, lane: 'Build', progress: 0.7 },
    { name: 'Development', start: 4, end: 9, lane: 'Build', progress: 0.35 }
  ]"
  :milestones="[{ label: 'Design sign-off', at: 5 }]"
  :today="6"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'

type TimeValue = number | string
type Task = {
  name: string
  start: TimeValue
  end: TimeValue
  lane?: string
  color?: string
  progress?: number
}
type Milestone = {
  label: string
  at: TimeValue
}

const props = defineProps({
  tasks: {
    type: Array as () => Task[],
    default: () => [
      { name: 'Research', start: 1, end: 2.5, lane: 'Planning', progress: 1 },
      { name: 'Requirements', start: 1.8, end: 3.5, lane: 'Planning', progress: 0.85 },
      { name: 'UX & visual design', start: 3, end: 5.5, lane: 'Delivery', progress: 0.65 },
      { name: 'Core development', start: 4.5, end: 8.5, lane: 'Delivery', progress: 0.4 },
      { name: 'QA & accessibility', start: 7.5, end: 9.5, lane: 'Validation', progress: 0.15 },
      { name: 'Launch', start: 9.2, end: 10, lane: 'Validation', progress: 0 },
    ] as Task[],
  },
  start: {
    type: [Number, String] as unknown as () => TimeValue | undefined,
    default: undefined,
  },
  end: {
    type: [Number, String] as unknown as () => TimeValue | undefined,
    default: undefined,
  },
  title: {
    type: String,
    default: 'Project delivery plan',
  },
  unit: {
    type: String,
    default: 'wk',
  },
  milestones: {
    type: Array as () => Milestone[],
    default: () => [{ label: 'Design approved', at: 5.5 }],
  },
  today: {
    type: [Number, String] as unknown as () => TimeValue | null,
    default: 6.5,
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const started=performance.now(); const duration=700; progress.value=0; const frame=(now:number)=>{const t=Math.min(1,(now-started)/duration);progress.value=1-Math.pow(1-t,3);if(t<1)raf=requestAnimationFrame(frame)};raf=requestAnimationFrame(frame) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const W = 1000
const gutter = 220
const right = 28
const top = 84
const rowH = 48
const barH = 18
const plotW = W - gutter - right

const isDateMode = computed(() => {
  const values: TimeValue[] = [
    ...props.tasks.flatMap(task => [task.start, task.end]),
    ...props.milestones.map(item => item.at),
  ]
  if (props.start !== undefined) values.push(props.start)
  if (props.end !== undefined) values.push(props.end)
  if (props.today !== null) values.push(props.today)
  return values.some(value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value))
})

function toValue(value: TimeValue): number {
  if (isDateMode.value) {
    if (typeof value === 'number') return value
    const parsed = Date.parse(`${value}T00:00:00Z`)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return Number(value)
}

const taskValues = computed(() =>
  props.tasks.flatMap(task => [toValue(task.start), toValue(task.end)]),
)

const domain = computed(() => {
  const extras = [
    ...props.milestones.map(item => toValue(item.at)),
    ...(props.today === null ? [] : [toValue(props.today)]),
  ]
  const all = [...taskValues.value, ...extras].filter(Number.isFinite)
  let min = props.start === undefined ? Math.min(...all) : toValue(props.start)
  let max = props.end === undefined ? Math.max(...all) : toValue(props.end)
  if (!Number.isFinite(min)) min = 0
  if (!Number.isFinite(max)) max = min + 1
  if (max <= min) max = min + (isDateMode.value ? 86400000 : 1)
  return { min, max }
})

function x(value: TimeValue): number {
  const v = toValue(value)
  return gutter + ((v - domain.value.min) / (domain.value.max - domain.value.min)) * plotW
}

const tickCount = 6
const ticks = computed(() => {
  const { min, max } = domain.value
  return Array.from({ length: tickCount }, (_, index) => {
    const ratio = index / (tickCount - 1)
    const value = min + (max - min) * ratio
    return { value, x: gutter + ratio * plotW, label: formatTick(value) }
  })
})

function formatTick(value: number): string {
  if (isDateMode.value) {
    const date = new Date(value)
    return new Intl.DateTimeFormat('en', {
      month: 'short',
      day: 'numeric',
      timeZone: 'UTC',
    }).format(date)
  }
  const rounded = Math.round(value * 10) / 10
  return `${rounded}${props.unit ? ` ${props.unit}` : ''}`
}

const rows = computed(() => props.tasks.map((task, index) => {
  const startX = x(task.start)
  const endX = x(task.end)
  const width = Math.max(2, endX - startX)
  const completion = Math.min(1, Math.max(0, task.progress ?? 0))
  return {
    ...task,
    index,
    y: top + index * rowH,
    startX,
    width,
    animatedWidth: width * progress.value,
    completionWidth: width * completion * progress.value,
    showLane: Boolean(task.lane) && (index === 0 || props.tasks[index - 1]?.lane !== task.lane),
  }
}))

const chartHeight = computed(() => top + props.tasks.length * rowH + 30)
const plotBottom = computed(() => top + props.tasks.length * rowH)
const markerOpacity = computed(() => Math.max(0, (progress.value - 0.35) / 0.65))
const todayX = computed(() => props.today === null ? null : x(props.today))
const milestonePoints = (cx: number, cy: number) =>
  `${cx},${cy - 7} ${cx + 7},${cy} ${cx},${cy + 7} ${cx - 7},${cy}`
</script>

<template>
  <div class="gantt-chart">
    <svg
      :viewBox="`0 0 ${W} ${chartHeight}`"
      role="img"
      :aria-label="`${title}: Gantt chart with ${tasks.length} tasks`"
    >
      <title>{{ title }}</title>

      <text class="chart-title" x="0" y="27">{{ title }}</text>
      <text class="axis-caption" :x="gutter" y="52">
        {{ isDateMode ? 'Timeline' : `Timeline${unit ? ` (${unit})` : ''}` }}
      </text>

      <g class="grid">
        <line
          v-for="tick in ticks"
          :key="`grid-${tick.value}`"
          :x1="tick.x"
          :x2="tick.x"
          y1="62"
          :y2="plotBottom"
        />
        <line :x1="gutter" :x2="W - right" y1="62" y2="62" />
      </g>

      <g class="axis">
        <text
          v-for="(tick, index) in ticks"
          :key="`tick-${tick.value}`"
          :x="tick.x"
          y="55"
          :text-anchor="index === 0 ? 'start' : index === ticks.length - 1 ? 'end' : 'middle'"
        >
          {{ tick.label }}
        </text>
      </g>

      <g v-for="row in rows" :key="`${row.name}-${row.index}`">
        <rect
          v-if="row.index % 2 === 1"
          class="zebra"
          x="0"
          :y="row.y"
          :width="W"
          :height="rowH"
        />
        <line
          class="row-rule"
          x1="0"
          :x2="W - right"
          :y1="row.y + rowH"
          :y2="row.y + rowH"
        />

        <text
          v-if="row.showLane"
          class="lane"
          x="0"
          :y="row.y + 13"
        >
          {{ row.lane }}
        </text>
        <text
          class="task-name"
          x="0"
          :y="row.y + (row.lane ? 34 : 29)"
        >
          {{ row.name }}
        </text>

        <rect
          class="task-bar"
          :style="{ fill: row.color || '#28527A' }"
          :x="row.startX"
          :y="row.y + 15"
          :width="row.animatedWidth"
          :height="barH"
          rx="6"
        />
        <rect
          v-if="row.progress !== undefined"
          class="task-progress"
          :x="row.startX"
          :y="row.y + 15"
          :width="row.completionWidth"
          :height="barH"
          rx="6"
        />
      </g>

      <g
        v-if="todayX !== null"
        class="today"
        :opacity="markerOpacity"
      >
        <line :x1="todayX" :x2="todayX" y1="62" :y2="plotBottom" />
        <rect :x="todayX - 25" y="66" width="50" height="20" rx="10" />
        <text :x="todayX" y="80" text-anchor="middle">Today</text>
      </g>

      <g
        v-for="(milestone, index) in milestones"
        :key="`${milestone.label}-${index}`"
        class="milestone"
        :opacity="markerOpacity"
      >
        <polygon
          :points="milestonePoints(x(milestone.at), plotBottom + 8)"
        />
        <text
          :x="x(milestone.at)"
          :y="plotBottom + 27"
          text-anchor="middle"
        >
          {{ milestone.label }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.gantt-chart {
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
  font-size: 20px;
  font-weight: 700;
}

.axis-caption,
.axis text,
.lane,
.milestone text {
  fill: #5A6472;
}

.axis-caption {
  font-size: 12px;
  font-weight: 600;
}

.axis text {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.grid line,
.row-rule {
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.zebra {
  fill: #F5F6F8;
}

.lane {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.task-name {
  fill: #1C2530;
  font-size: 14px;
  font-weight: 500;
}

.task-bar {
  fill: #28527A;
}

.task-progress {
  fill: #1D3E5E;
  pointer-events: none;
}

.today line {
  stroke: #B07D2B;
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
  vector-effect: non-scaling-stroke;
}

.today rect {
  fill: #FFFFFF;
  stroke: #B07D2B;
  stroke-width: 1;
}

.today text {
  fill: #B07D2B;
  font-size: 11px;
  font-weight: 700;
}

.milestone polygon {
  fill: #B07D2B;
}

.milestone text {
  font-size: 11px;
  font-weight: 600;
}
</style>
