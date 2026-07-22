<!--
HierarchyTree.vue

Props:
- root: Nested hierarchy node:
  { label: string, desc?: string, color?: string, children?: Node[] }
- title?: Optional diagram title.
- animate?: Enables the subtle level-by-level reveal.

Usage:
<HierarchyTree
  title="Product organisation"
  :root="{
    label: 'VP Product',
    desc: 'Portfolio direction',
    children: [
      { label: 'Platform', desc: 'Core services' },
      {
        label: 'Experience',
        desc: 'Customer journeys',
        children: [
          { label: 'Web', desc: 'Browser experience' },
          { label: 'Mobile', desc: 'Native applications' }
        ]
      },
      { label: 'Operations', desc: 'Delivery systems' }
    ]
  }"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

type TreeNode = {
  label: string
  desc?: string
  color?: string
  children?: TreeNode[]
}

type LayoutNode = {
  id: number
  node: TreeNode
  x: number
  y: number
  depth: number
}

type Connector = {
  id: string
  path: string
  depth: number
}

const props = defineProps({
  root: {
    type: Object as () => TreeNode,
    default: () => ({
      label: 'Executive Director',
      desc: 'Strategy and stewardship',
      children: [
        {
          label: 'Operations',
          desc: 'Delivery and systems',
        },
        {
          label: 'Programmes',
          desc: 'Portfolio leadership',
          children: [
            {
              label: 'Research',
              desc: 'Evidence and insight',
            },
            {
              label: 'Delivery',
              desc: 'Implementation',
            },
          ],
        },
        {
          label: 'Partnerships',
          desc: 'External relationships',
        },
      ],
    }),
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

// Nested-list authoring: the nested list IS the tree ("label | desc"; recurse).
const { src, parsed } = useSlotTree()
function toNode(n): TreeNode {
  const { color, parts } = parseLabel(n.text)
  const out: TreeNode = { label: parts[0] || '' }
  if (parts[1]) out.desc = parts[1]
  if (color) out.color = color
  if (n.children.length) out.children = n.children.map(toNode)
  return out
}
function mapToShape(tree): TreeNode {
  return tree.length === 1 ? toNode(tree[0]) : { label: props.title || 'Overview', children: tree.map(toNode) }
}
const rootData = computed<TreeNode>(() => (parsed.value ? mapToShape(parsed.value) : props.root))

const NODE_W = 190
const NODE_H = 72
const GAP_X = 34
const GAP_Y = 76
const PAD_X = 24
const PAD_TOP = 18
const PAD_BOTTOM = 24

const layout = computed(() => {
  let nextId = 0
  let leafCursor = 0
  let maxDepth = 0
  const nodes: LayoutNode[] = []
  const edges: Array<{ parent: LayoutNode; child: LayoutNode }> = []

  function place(node: TreeNode, depth: number): LayoutNode {
    maxDepth = Math.max(maxDepth, depth)
    const children = node.children ?? []
    const placedChildren = children.map(child => place(child, depth + 1))

    let center: number
    if (placedChildren.length) {
      center =
        (placedChildren[0].x +
          placedChildren[placedChildren.length - 1].x) /
        2
    } else {
      center = leafCursor * (NODE_W + GAP_X) + NODE_W / 2
      leafCursor += 1
    }

    const placed: LayoutNode = {
      id: nextId++,
      node,
      x: center,
      y: PAD_TOP + depth * (NODE_H + GAP_Y),
      depth,
    }

    nodes.push(placed)
    placedChildren.forEach(child => edges.push({ parent: placed, child }))
    return placed
  }

  place(rootData.value, 0)

  const minCenter = Math.min(...nodes.map(node => node.x))
  const maxCenter = Math.max(...nodes.map(node => node.x))
  const contentWidth = Math.max(
    NODE_W,
    maxCenter - minCenter + NODE_W,
  )
  const shiftX = PAD_X + NODE_W / 2 - minCenter

  nodes.forEach(node => {
    node.x += shiftX
  })

  const connectors: Connector[] = edges.map(({ parent, child }) => {
    const startX = parent.x
    const startY = parent.y + NODE_H
    const endX = child.x
    const endY = child.y
    const elbowY = startY + GAP_Y / 2

    return {
      id: `${parent.id}-${child.id}`,
      depth: child.depth,
      path: `M ${startX} ${startY} V ${elbowY} H ${endX} V ${endY}`,
    }
  })

  return {
    nodes,
    connectors,
    maxDepth,
    width: contentWidth + PAD_X * 2,
    height:
      PAD_TOP +
      (maxDepth + 1) * NODE_H +
      maxDepth * GAP_Y +
      PAD_BOTTOM,
  }
})

const progress = ref(0)
const { currentPage } = useNav()
const ctx = useSlideContext()
const reduced =
  typeof window !== 'undefined' &&
  window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

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
    if (!started) started = time
    const t = Math.min(1, (time - started) / duration)
    progress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) raf = requestAnimationFrame(frame)
  }

  raf = requestAnimationFrame(frame)
}

onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) })
watch(
  () => currentPage.value === unref(ctx.$page),
  (a, w) => {
    if (a && !w) animate()
  },
)
onBeforeUnmount(() => cancelAnimationFrame(raf))

function levelProgress(depth: number, connector = false) {
  const levels = Math.max(1, layout.value.maxDepth + 1)
  const stagger = 0.16
  const start = depth * stagger + (connector ? -0.07 : 0)
  const available = Math.max(0.2, 1 - (levels - 1) * stagger)
  return Math.max(0, Math.min(1, (progress.value - start) / available))
}

function nodeStyle(item: LayoutNode) {
  const p = levelProgress(item.depth)
  return {
    opacity: p,
    transform: `translate(${item.x - NODE_W / 2}px, ${item.y + (1 - p) * 9}px)`,
  }
}

function connectorStyle(item: Connector) {
  return {
    opacity: levelProgress(item.depth, true),
  }
}

function nodeAccent(item: LayoutNode) {
  if (item.depth === 0) return '#28527A'
  return item.node.color || '#28527A'
}
</script>

<template>
  <div class="hierarchy-tree">
    <div ref="src" style="display:none"><slot /></div>
    <div v-if="title" class="diagram-title">{{ title }}</div>

    <svg
      class="tree-canvas"
      :viewBox="`0 0 ${layout.width} ${layout.height}`"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      :aria-label="title || `${rootData.label} hierarchy`"
    >
      <g class="connectors" aria-hidden="true">
        <path
          v-for="connector in layout.connectors"
          :key="connector.id"
          :d="connector.path"
          :style="connectorStyle(connector)"
        />
      </g>

      <g
        v-for="item in layout.nodes"
        :key="item.id"
        class="tree-node"
        :class="{ 'tree-node--root': item.depth === 0 }"
        :style="nodeStyle(item)"
      >
        <GenBox
          :x="0"
          :y="0"
          :w="NODE_W"
          :h="NODE_H"
          :accent="nodeAccent(item)"
          :fill="item.depth === 0 ? '#FFFFFF' : '#F5F6F8'"
          :emphasis="item.depth === 0"
        />

        <foreignObject
          x="14"
          y="10"
          :width="NODE_W - 27"
          :height="NODE_H - 18"
        >
          <div xmlns="http://www.w3.org/1999/xhtml" class="node-copy">
            <div class="node-label">{{ item.node.label }}</div>
            <div v-if="item.node.desc" class="node-desc">
              {{ item.node.desc }}
            </div>
          </div>
        </foreignObject>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.hierarchy-tree {
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
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.tree-canvas {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
}

.connectors path {
  fill: none;
  stroke: #5A6472;
  stroke-width: 1.25;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.node-surface {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.node-accent {
  fill: none;
  stroke-width: 3;
}

.tree-node--root .node-surface {
  fill: #FFFFFF;
  stroke: #28527A;
}

.node-copy {
  display: flex;
  height: 100%;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  box-sizing: border-box;
  overflow: hidden;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.node-label {
  overflow: hidden;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.18;
  text-overflow: ellipsis;
}

.node-desc {
  display: -webkit-box;
  margin-top: 4px;
  overflow: hidden;
  color: #5A6472;
  font-size: 12.5px;
  font-weight: 400;
  line-height: 1.22;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
</style>
