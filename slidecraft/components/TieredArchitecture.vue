<!--
TieredArchitecture.vue

A horizontal-band layered/tiered architecture (stack) diagram, top tier to bottom, with
optional cross-cutting sidebars.
(Renamed from LayeredArchitecture — that name collides with the Iconify `la` icon collection
under Slidev's icon auto-resolver.)

Props:
- title?: string — optional diagram heading.
- layers: Array<{ name: string; desc?: string; items?: string[]; color?: string }>
  — architecture bands ordered top to bottom. `color` accepts any CSS colour.
- sidebars: Array<{ label: string }> — optional cross-cutting bands on the right.
- animate: boolean — enables the subtle enter animation.

Usage:
<TieredArchitecture
  title="Platform architecture"
  :layers="[
    { name: 'Experience', desc: 'User-facing channels', items: ['Web', 'Mobile'] },
    { name: 'Services', items: ['API', 'Workflows', 'Jobs'], color: '#3F7D74' },
    { name: 'Core', items: ['Rules', 'Entities'] },
    { name: 'Data', items: ['PostgreSQL', 'Object storage'] }
  ]"
  :sidebars="[{ label: 'Security' }, { label: 'Telemetry' }]"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

type Layer = {
  name: string
  desc?: string
  items?: string[]
  color?: string
}

type Sidebar = {
  label: string
}

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  layers: {
    type: Array as () => Layer[],
    default: () => [
      {
        name: 'Presentation',
        desc: 'Interfaces and delivery channels',
        items: ['Web', 'Mobile', 'Admin'],
        color: '#28527A',
      },
      {
        name: 'Application',
        desc: 'Use cases and orchestration',
        items: ['API services', 'Workflows', 'Jobs'],
        color: '#B07D2B',
      },
      {
        name: 'Domain',
        desc: 'Business rules and core models',
        items: ['Entities', 'Policies', 'Events'],
        color: '#3F7D74',
      },
      {
        name: 'Infrastructure',
        desc: 'Persistence and external systems',
        items: ['Database', 'Messaging', 'Integrations'],
        color: '#7FA8CF',
      },
    ],
  },
  sidebars: {
    type: Array as () => Sidebar[],
    default: () => [
      { label: 'Security' },
      { label: 'Observability' },
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

function animate(){
  if(!props.animate||reduced){progress.value=1;return}
  cancelAnimationFrame(raf)
  progress.value = 0
  const duration = 700
  let started = 0
  const frame = (time: number) => {
    if (!started) started = time
    const t = Math.min(1, (time - started) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)
}

onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: each top <li> is a layer ("name | desc"), nested = item chips.
// A top <li> whose label is "Cross-cutting" / "Sidebars" / "Aside" is special: its
// children become the right-hand cross-cutting sidebars instead of a layer.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  const layers: Layer[] = []
  let sidebars: Sidebar[] | null = null
  tree.forEach(node => {
    const label = parseLabel(node.text).text.trim()
    if (/^(side\s?bars?|cross[-\s]?cutting|aside)$/i.test(label)) {
      sidebars = (node.children || []).map(c => ({ label: parseLabel(c.text).parts[0] || c.text }))
      return
    }
    const { color, parts } = parseLabel(node.text)
    const layer: Layer = { name: parts[0] || '' }
    if (parts[1]) layer.desc = parts[1]
    if (color) layer.color = color
    if (node.children.length) layer.items = node.children.map(c => c.text)
    layers.push(layer)
  })
  return { layers, sidebars }
}
const model = computed(() => (parsed.value ? mapToShape(parsed.value) : null))
const layersData = computed<Layer[]>(() => (model.value ? model.value.layers : props.layers))
const sidebarsData = computed<Sidebar[]>(() => (model.value && model.value.sidebars !== null ? model.value.sidebars : props.sidebars))

const layerCount = computed(() => Math.max(layersData.value.length, 1))

function stagedValue(index: number, total: number, start = 0, span = 0.82) {
  const stagger = total > 1 ? 0.34 / (total - 1) : 0
  const local = (progress.value - start - index * stagger) / span
  return Math.max(0, Math.min(1, local))
}

function layerStyle(index: number) {
  const value = stagedValue(index, layerCount.value)
  return {
    opacity: value,
    transform: `translateY(${(1 - value) * -8}px) scale(${0.992 + value * 0.008})`,
    borderLeftColor: layersData.value[index]?.color || '#28527A',
  }
}

function sidebarStyle(index: number) {
  const count = Math.max(sidebarsData.value.length, 1)
  const local = Math.max(
    0,
    Math.min(1, (progress.value - 0.68 - index * (0.08 / count)) / 0.24),
  )
  return {
    opacity: local,
    transform: `translateX(${(1 - local) * 7}px)`,
  }
}
</script>

<template>
  <div class="layered-architecture">
    <div ref="src" style="display:none"><slot /></div>
    <div v-if="title" class="diagram-title">{{ title }}</div>

    <div class="architecture-frame">
      <div class="layers">
        <section
          v-for="(layer, index) in layersData"
          :key="`${layer.name}-${index}`"
          class="layer"
          :style="layerStyle(index)"
        >
          <div class="layer-copy">
            <div class="layer-name">{{ layer.name }}</div>
            <div v-if="layer.desc" class="layer-desc">{{ layer.desc }}</div>
          </div>

          <div v-if="layer.items?.length" class="chips">
            <span
              v-for="(item, itemIndex) in layer.items"
              :key="`${item}-${itemIndex}`"
              class="chip"
            >
              {{ item }}
            </span>
          </div>
        </section>
      </div>

      <aside v-if="sidebarsData.length" class="sidebars" aria-label="Cross-cutting concerns">
        <div
          v-for="(sidebar, index) in sidebarsData"
          :key="`${sidebar.label}-${index}`"
          class="sidebar"
          :style="sidebarStyle(index)"
        >
          <span>{{ sidebar.label }}</span>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.layered-architecture {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.diagram-title {
  margin: 0 0 0.65rem;
  color: #1C2530;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.architecture-frame {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: stretch;
  gap: 0.55rem;
}

.layers {
  display: grid;
  flex: 1 1 auto;
  min-width: 0;
  gap: 0.42rem;
}

.layer {
  display: grid;
  grid-template-columns: minmax(9.5rem, 0.8fr) minmax(0, 1.7fr);
  align-items: center;
  min-height: 4.25rem;
  padding: 0.65rem 0.8rem;
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid #DFE3E8;
  border-left: 3px solid #28527A;
  border-radius: 8px;
  background: #F5F6F8;
  will-change: opacity, transform;
}

.layer-copy {
  min-width: 0;
  padding-right: 0.75rem;
}

.layer-name {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
}

.layer-desc {
  margin-top: 0.2rem;
  color: #5A6472;
  font-size: 13px;
  line-height: 1.3;
}

.chips {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.35rem;
}

.chip {
  max-width: 100%;
  padding: 0.25rem 0.48rem;
  overflow-wrap: anywhere;
  border: 1px solid #DFE3E8;
  border-radius: 999px;
  background: #FFFFFF;
  color: #1C2530;
  font-size: 13px;
  line-height: 1.15;
}

.sidebars {
  display: flex;
  flex: 0 0 auto;
  align-items: stretch;
  gap: 0.35rem;
}

.sidebar {
  display: flex;
  width: clamp(2.35rem, 4.5vw, 3.15rem);
  min-height: 100%;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  border: 1px solid #DFE3E8;
  border-radius: 8px;
  background: color-mix(in srgb, #5A6472 9%, #FFFFFF);
  color: #5A6472;
  will-change: opacity, transform;
}

.sidebar span {
  display: block;
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.025em;
  line-height: 1;
  white-space: nowrap;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}

@media (max-width: 640px) {
  .layer {
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }

  .layer-copy {
    padding-right: 0;
  }

  .chips {
    justify-content: flex-start;
  }

  .sidebar {
    width: 2.25rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .layer,
  .sidebar {
    will-change: auto;
  }
}
</style>
