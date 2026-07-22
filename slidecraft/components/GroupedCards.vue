<!--
GroupedCards.vue

Props:
- cards: Array<{ title: string; desc?: string; items?: string[]; icon?: string; color?: string; badge?: string }>
- columns: Number — 0 auto-fits by card count; otherwise fixed to 2, 3, or 4.
- title: String — optional diagram heading.
- numbered: Boolean — shows a numbered badge on each card.
- animate: Boolean — enables the subtle staggered entrance animation.

Usage:
<GroupedCards
  title="Programme pillars"
  :columns="3"
  :numbered="true"
  :cards="[
    { title: 'Discover', desc: 'Frame the opportunity.', items: ['Interview users', 'Map constraints'], icon: '🔎', badge: 'Week 1' },
    { title: 'Design', desc: 'Shape the response.', items: ['Prototype flows', 'Test assumptions'], icon: '✏️' },
    { title: 'Deliver', desc: 'Launch with confidence.', items: ['Prepare rollout', 'Measure impact'], icon: '🚀', color: '#3F7D74' }
  ]"
/>
-->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel } from './_slotAuthoring'

const props = defineProps({
  cards: {
    type: Array,
    default: () => [
      {
        title: 'Discover',
        desc: 'Build a shared view of the opportunity.',
        items: ['Interview key users', 'Map needs and constraints'],
        icon: '🔎',
        badge: 'Explore',
      },
      {
        title: 'Define',
        desc: 'Turn evidence into a focused brief.',
        items: ['Frame the core problem', 'Agree success measures'],
        icon: '🎯',
        badge: 'Align',
      },
      {
        title: 'Design',
        desc: 'Develop clear, testable responses.',
        items: ['Sketch candidate flows', 'Prototype key moments'],
        icon: '✏️',
        badge: 'Create',
      },
      {
        title: 'Validate',
        desc: 'Test assumptions before committing.',
        items: ['Run user sessions', 'Prioritise improvements'],
        icon: '🧪',
        badge: 'Learn',
      },
      {
        title: 'Deliver',
        desc: 'Move the preferred solution into use.',
        items: ['Coordinate the rollout', 'Support adoption'],
        icon: '🚀',
        badge: 'Launch',
      },
      {
        title: 'Measure',
        desc: 'Track outcomes and guide iteration.',
        items: ['Review performance', 'Plan the next cycle'],
        icon: '📈',
        badge: 'Improve',
      },
    ],
  },
  columns: {
    type: Number,
    default: 0,
    validator: value => [0, 2, 3, 4].includes(value),
  },
  title: {
    type: String,
    default: '',
  },
  numbered: {
    type: Boolean,
    default: false,
  },
  animate: {
    type: Boolean,
    default: true,
  },
})

// Nested-list authoring: each top <li> is a card (emoji=icon, "| badge"), nested = items.
const { src, parsed } = useSlotTree()
function mapToShape(tree) {
  return tree.map(node => {
    const { icon, color, parts } = parseLabel(node.text)
    const card = { title: parts[0] || '' }
    if (icon) card.icon = icon
    if (parts[1]) card.badge = parts[1]
    if (color) card.color = color
    if (node.children.length) card.items = node.children.map(c => c.text)
    return card
  })
}
const cardsData = computed(() => (parsed.value ? mapToShape(parsed.value) : props.cards))

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0

function animate(){
  if(!props.animate||reduced){progress.value=1;return}
  cancelAnimationFrame(raf)
  progress.value = 0
  const duration = 700
  let start = 0
  const frame = time => {
    if (!start) start = time
    const t = Math.min(1, (time - start) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)
}
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

const accents = [
  '#28527A',
  '#B07D2B',
  '#3F7D74',
]

const safeColumns = computed(() =>
  [2, 3, 4].includes(props.columns) ? props.columns : 0
)

const autoMinimum = computed(() => {
  const count = cardsData.value.length
  if (count <= 2) return '17rem'
  if (count <= 4) return '14rem'
  return '12.5rem'
})

const gridStyle = computed(() => ({
  gridTemplateColumns: safeColumns.value
    ? `repeat(${safeColumns.value}, minmax(0, 1fr))`
    : `repeat(auto-fit, minmax(min(100%, ${autoMinimum.value}), 1fr))`,
}))

function cardColor(card, index) {
  return card.color || accents[index % accents.length]
}

function itemStyle(index) {
  const stagger = Math.min(index * 0.075, 0.42)
  const span = Math.max(0.58, 1 - stagger)
  const local = Math.max(0, Math.min(1, (progress.value - stagger) / span))
  return {
    opacity: local,
    transform: `translateY(${(1 - local) * 8}px) scale(${0.985 + local * 0.015})`,
  }
}
</script>

<template>
  <section class="grouped-cards" :aria-label="title || 'Grouped cards'">
    <div ref="src" style="display:none"><slot /></div>
    <h2 v-if="title" class="diagram-title">{{ title }}</h2>

    <div class="cards-grid" :style="gridStyle">
      <article
        v-for="(card, index) in cardsData"
        :key="`${card.title}-${index}`"
        class="card"
        :style="[itemStyle(index), { '--card-accent': cardColor(card, index) }]"
      >
        <div class="card-rule" aria-hidden="true"></div>

        <header class="card-header">
          <div v-if="card.icon" class="icon-chip" aria-hidden="true">
            {{ card.icon }}
          </div>

          <div class="heading-block">
            <div class="title-row">
              <h3>{{ card.title }}</h3>
              <span v-if="card.badge" class="label-badge">{{ card.badge }}</span>
            </div>
          </div>

          <span v-if="numbered" class="number-badge" aria-hidden="true">
            {{ index + 1 }}
          </span>
        </header>

        <p v-if="card.desc" class="description">{{ card.desc }}</p>

        <ul v-if="card.items?.length" class="item-list">
          <li v-for="(item, itemIndex) in card.items" :key="`${item}-${itemIndex}`">
            {{ item }}
          </li>
        </ul>
      </article>
    </div>
  </section>
</template>

<style scoped>
.grouped-cards {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.diagram-title {
  margin: 0 0 0.8rem;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: clamp(1.05rem, 2.1vw, 1.4rem);
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.015em;
}

.cards-grid {
  display: grid;
  align-items: stretch;
  gap: clamp(0.65rem, 1.5vw, 1rem);
  width: 100%;
  max-width: 100%;
}

.card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  padding: clamp(0.8rem, 1.5vw, 1.05rem);
  border: 1px solid #DFE3E8;
  border-radius: 8px;
  background: #F5F6F8;
  transform-origin: center bottom;
  will-change: opacity, transform;
}

.card-rule {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--card-accent);
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  min-width: 0;
}

.icon-chip {
  display: grid;
  width: 2rem;
  height: 2rem;
  flex: 0 0 2rem;
  place-items: center;
  box-sizing: border-box;
  border: 1px solid color-mix(in srgb, var(--card-accent) 36%, #DFE3E8);
  border-radius: 7px;
  background: color-mix(in srgb, var(--card-accent) 10%, #FFFFFF);
  font-size: 1rem;
  line-height: 1;
}

.heading-block {
  min-width: 0;
  flex: 1;
}

.title-row {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
}

.title-row h3 {
  min-width: 0;
  margin: 0;
  color: #1C2530;
  font-size: clamp(0.88rem, 1.45vw, 1rem);
  font-weight: 700;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.label-badge {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 0.15rem 0.42rem;
  border: 1px solid #DFE3E8;
  border-radius: 999px;
  background: #FFFFFF;
  color: #5A6472;
  font-size: 0.68rem;
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.number-badge {
  display: grid;
  width: 1.55rem;
  height: 1.55rem;
  flex: 0 0 1.55rem;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--card-accent) 45%, #DFE3E8);
  border-radius: 999px;
  background: #FFFFFF;
  color: var(--card-accent);
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1;
}

.description {
  margin: 0.65rem 0 0;
  color: #5A6472;
  font-size: clamp(0.78rem, 1.25vw, 0.9rem);
  line-height: 1.45;
}

.item-list {
  display: grid;
  gap: 0.32rem;
  margin: 0.65rem 0 0;
  padding: 0;
  list-style: none;
  color: #1C2530;
  font-size: clamp(0.76rem, 1.2vw, 0.86rem);
  line-height: 1.4;
}

.item-list li {
  position: relative;
  padding-left: 0.85rem;
  overflow-wrap: anywhere;
}

.item-list li::before {
  position: absolute;
  top: 0.56em;
  left: 0;
  width: 0.3rem;
  height: 0.3rem;
  border-radius: 50%;
  background: var(--card-accent);
  content: '';
}

@media (max-width: 560px) {
  .cards-grid {
    grid-template-columns: 1fr !important;
  }
}
</style>
