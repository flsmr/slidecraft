<!--
DecisionTree.vue

Props:
- root: Nested tree node:
  {
    text: string,
    type?: 'decision' | 'outcome',
    color?: string,
    branches?: Array<{ label: string, node: TreeNode }>
  }
- title?: Optional heading shown above the tree.
- animate?: Enables the subtle level-by-level reveal.

Usage:
<DecisionTree
  title="Funding decision"
  :root="{
    text: 'Budget approved?',
    branches: [
      { label: 'No', node: { text: 'Revise proposal', type: 'outcome' } },
      {
        label: 'Yes',
        node: {
          text: 'Resources available?',
          branches: [
            { label: 'No', node: { text: 'Schedule later', type: 'outcome' } },
            { label: 'Yes', node: { text: 'Start project', type: 'outcome', color: '#3F7D74' } }
          ]
        }
      }
    ]
  }"
/>
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, unref } from 'vue'
import { useNav, useSlideContext } from '@slidev/client'
import { useSlotTree, parseLabel, leftBorderPath } from './_slotAuthoring'

type TreeNode = {
  text: string
  type?: 'decision' | 'outcome'
  color?: string
  branches?: TreeBranch[]
}

type TreeBranch = {
  label: string
  node: TreeNode
}

type LayoutNode = {
  id: string
  node: TreeNode
  type: 'decision' | 'outcome'
  depth: number
  x: number
  y: number
}

type LayoutEdge = {
  id: string
  label: string
  depth: number
  x1: number
  y1: number
  x2: number
  y2: number
}

const props = defineProps({
  root: {
    type: Object as () => TreeNode,
    default: (): TreeNode => ({
      text: 'Budget approved?',
      type: 'decision',
      branches: [
        {
          label: 'No',
          node: {
            text: 'Revise proposal',
            type: 'outcome',
          },
        },
        {
          label: 'Yes',
          node: {
            text: 'Resources available?',
            type: 'decision',
            branches: [
              {
                label: 'No',
                node: {
                  text: 'Schedule later',
                  type: 'outcome',
                },
              },
              {
                label: 'Yes',
                node: {
                  text: 'Start project',
                  type: 'outcome',
                  color: '#3F7D74',
                },
              },
            ],
          },
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

const progress = ref(0); const { currentPage } = useNav(); const ctx = useSlideContext()
const reduced = typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let raf = 0
function animate(){ if(!props.animate||reduced){progress.value=1;return} cancelAnimationFrame(raf); const start=performance.now(); const duration=700; progress.value=0; const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration); progress.value=1-Math.pow(1-t,3); if(t<1)raf=requestAnimationFrame(tick)}; raf=requestAnimationFrame(tick) }
onMounted(() => { animate(); setTimeout(() => { progress.value = 1 }, 850) }); watch(()=>currentPage.value===unref(ctx.$page),(a,w)=>{if(a&&!w)animate()}); onBeforeUnmount(()=>cancelAnimationFrame(raf))

// Nested-list authoring: the nested list IS the tree. A label ending in "?" is a decision
// node (else an outcome); a child bullet starting "Yes:" / "No:" sets that edge's label.
const { src, parsed } = useSlotTree()
function parseEdge(text) {
  const m = String(text).match(/^\s*(Yes|No)\s*:\s*(.*)$/i)
  return m ? { label: m[1], rest: m[2].trim() } : { label: '', rest: String(text).trim() }
}
function toTreeNode(item): TreeNode {
  const { color, parts, text } = parseLabel(item.text)
  const nodeText = (parts[0] || text || '').trim()
  const hasChildren = item.children && item.children.length > 0
  const isDecision = /\?\s*$/.test(nodeText) || hasChildren
  const node: TreeNode = { text: nodeText, type: isDecision ? 'decision' : 'outcome' }
  if (color) node.color = color
  if (hasChildren) {
    node.branches = item.children.slice(0, 2).map(ch => {
      const e = parseEdge(ch.text)
      return { label: e.label, node: toTreeNode({ text: e.rest, children: ch.children }) }
    })
  }
  return node
}
function mapToShape(tree): TreeNode {
  return tree.length ? toTreeNode(tree[0]) : props.root
}
const rootData = computed<TreeNode>(() => (parsed.value ? mapToShape(parsed.value) : props.root))

const WIDTH = 1000
const TOP = 60
const LEVEL_GAP = 180
const DECISION_W = 210
const DECISION_H = 96
const OUTCOME_W = 190
const OUTCOME_H = 72
const SIDE_PAD = 115

function nodeType(node: TreeNode): 'decision' | 'outcome' {
  return node.type || (node.branches?.length ? 'decision' : 'outcome')
}

function leafCount(node: TreeNode): number {
  const branches = node.branches?.slice(0, 2) || []
  if (nodeType(node) === 'outcome' || !branches.length)
    return 1
  return branches.reduce((sum, branch) => sum + leafCount(branch.node), 0)
}

function treeDepth(node: TreeNode, depth = 0): number {
  const branches = node.branches?.slice(0, 2) || []
  if (!branches.length || nodeType(node) === 'outcome')
    return depth
  return Math.max(...branches.map(branch => treeDepth(branch.node, depth + 1)))
}

const layout = computed(() => {
  const nodes: LayoutNode[] = []
  const edges: LayoutEdge[] = []
  const leaves = Math.max(1, leafCount(rootData.value))
  const usableWidth = WIDTH - SIDE_PAD * 2
  const columnWidth = usableWidth / leaves
  let nextLeaf = 0

  function visit(node: TreeNode, depth: number, path: string): number {
    const branches = nodeType(node) === 'decision'
      ? (node.branches?.slice(0, 2) || [])
      : []

    let x: number
    const childPositions: Array<{ x: number; node: TreeNode; label: string; path: string }> = []

    if (!branches.length) {
      x = SIDE_PAD + columnWidth * (nextLeaf + 0.5)
      nextLeaf += 1
    }
    else {
      for (let i = 0; i < branches.length; i++) {
        const branch = branches[i]
        const childPath = `${path}-${i}`
        const childX = visit(branch.node, depth + 1, childPath)
        childPositions.push({
          x: childX,
          node: branch.node,
          label: branch.label,
          path: childPath,
        })
      }
      x = childPositions.reduce((sum, child) => sum + child.x, 0) / childPositions.length
    }

    const type = nodeType(node)
    const y = TOP + depth * LEVEL_GAP
    nodes.push({ id: path, node, type, depth, x, y })

    const parentHalfHeight = type === 'decision' ? DECISION_H / 2 : OUTCOME_H / 2
    for (const child of childPositions) {
      const childType = nodeType(child.node)
      const childY = TOP + (depth + 1) * LEVEL_GAP
      const childHalfHeight = childType === 'decision' ? DECISION_H / 2 : OUTCOME_H / 2
      edges.push({
        id: `${path}:${child.path}`,
        label: child.label,
        depth: depth + 1,
        x1: x,
        y1: y + parentHalfHeight,
        x2: child.x,
        y2: childY - childHalfHeight,
      })
    }

    return x
  }

  visit(rootData.value, 0, 'root')
  const maxDepth = treeDepth(rootData.value)
  return {
    nodes,
    edges,
    maxDepth,
    height: TOP + maxDepth * LEVEL_GAP + OUTCOME_H / 2 + 42,
  }
})

function reveal(depth: number, edge = false) {
  const maxDepth = Math.max(1, layout.value.maxDepth)
  const stages = maxDepth + 1
  const stage = edge ? Math.max(0.5, depth - 0.35) : depth
  const start = (stage / stages) * 0.62
  const end = Math.min(1, start + 0.38)
  const value = Math.max(0, Math.min(1, (progress.value - start) / Math.max(0.01, end - start)))
  return 1 - Math.pow(1 - value, 3)
}

function nodeStyle(item: LayoutNode) {
  const value = reveal(item.depth)
  return {
    opacity: value,
    transform: `translate(0 ${8 * (1 - value)}px) scale(${0.985 + value * 0.015})`,
    transformOrigin: `${item.x}px ${item.y}px`,
  }
}

function edgeStyle(edge: LayoutEdge) {
  const value = reveal(edge.depth, true)
  return {
    opacity: value,
    transform: `translateY(${5 * (1 - value)}px)`,
  }
}

function decisionPoints(item: LayoutNode) {
  const halfW = DECISION_W / 2
  const halfH = DECISION_H / 2
  return `${item.x},${item.y - halfH} ${item.x + halfW},${item.y} ${item.x},${item.y + halfH} ${item.x - halfW},${item.y}`
}

function connectorPath(edge: LayoutEdge) {
  const middleY = edge.y1 + 50   // fixed elbow per parent so sibling horizontals align
  return `M ${edge.x1} ${edge.y1} V ${middleY} H ${edge.x2} V ${edge.y2}`
}

function labelPosition(edge: LayoutEdge) {
  const middleY = edge.y1 + 50   // fixed elbow per parent so sibling horizontals align
  const horizontal = Math.abs(edge.x2 - edge.x1)
  return {
    x: horizontal > 30 ? (edge.x1 + edge.x2) / 2 : edge.x1 + 18,
    y: horizontal > 30 ? middleY - 9 : (edge.y1 + edge.y2) / 2,
  }
}

function accent(node: TreeNode) {
  return node.color || '#28527A'
}
</script>

<template>
  <div class="decision-tree">
    <div ref="src" style="display:none"><slot /></div>
    <div
      v-if="title"
      class="decision-tree__title"
      :style="{ opacity: reveal(0), transform: `translateY(${5 * (1 - reveal(0))}px)` }"
    >
      {{ title }}
    </div>

    <svg
      class="decision-tree__svg"
      :viewBox="`0 0 ${WIDTH} ${layout.height}`"
      role="img"
      :aria-label="title || 'Decision tree'"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker
          id="decision-tree-arrow"
          markerWidth="8"
          markerHeight="8"
          refX="7"
          refY="4"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 8 4 L 0 8 Z" class="arrow-head" />
        </marker>
      </defs>

      <g class="edges">
        <g
          v-for="edge in layout.edges"
          :key="edge.id"
          class="edge"
          :style="edgeStyle(edge)"
        >
          <path
            :d="connectorPath(edge)"
            class="connector"
            marker-end="url(#decision-tree-arrow)"
          />
          <g
            class="edge-label"
            :transform="`translate(${labelPosition(edge).x} ${labelPosition(edge).y})`"
          >
            <rect
              x="-29"
              y="-12"
              width="58"
              height="24"
              rx="12"
            />
            <text text-anchor="middle" dominant-baseline="central">
              {{ edge.label }}
            </text>
          </g>
        </g>
      </g>

      <g class="nodes">
        <g
          v-for="item in layout.nodes"
          :key="item.id"
          class="node"
          :style="nodeStyle(item)"
        >
          <template v-if="item.type === 'decision'">
            <polygon
              :points="decisionPoints(item)"
              class="decision-shape"
              :style="{ stroke: accent(item.node) }"
            />
            <foreignObject
              :x="item.x - 72"
              :y="item.y - 31"
              width="144"
              height="62"
            >
              <div xmlns="http://www.w3.org/1999/xhtml" class="node-copy decision-copy">
                {{ item.node.text }}
              </div>
            </foreignObject>
          </template>

          <template v-else>
            <GenBox
              :x="item.x - OUTCOME_W / 2"
              :y="item.y - OUTCOME_H / 2"
              :w="OUTCOME_W"
              :h="OUTCOME_H"
              :accent="accent(item.node)"
            />
            <foreignObject
              :x="item.x - OUTCOME_W / 2 + 18"
              :y="item.y - OUTCOME_H / 2 + 8"
              :width="OUTCOME_W - 30"
              :height="OUTCOME_H - 16"
            >
              <div xmlns="http://www.w3.org/1999/xhtml" class="node-copy outcome-copy">
                {{ item.node.text }}
              </div>
            </foreignObject>
          </template>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.decision-tree {
  width: 100%;
  max-width: 100%;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
}

.decision-tree__title {
  margin: 0 0 0.45rem;
  color: #1C2530;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.decision-tree__svg {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  overflow: visible;
}

.connector {
  fill: none;
  stroke: #5A6472;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.arrow-head {
  fill: #5A6472;
}

.edge-label rect {
  fill: #FFFFFF;
  stroke: #DFE3E8;
  stroke-width: 1;
}

.edge-label text {
  fill: #5A6472;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 13px;
  font-weight: 600;
}

.decision-shape,
.outcome-shape {
  fill: #F5F6F8;
  stroke: #DFE3E8;
  stroke-width: 1.25;
  stroke-linejoin: round;
}

.decision-shape {
  stroke-width: 1.5;
}

.outcome-accent {
  fill: none;
  stroke-width: 3;
}

.decision-accent {
  stroke-width: 3;
  stroke-linecap: round;
}

.node-copy {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  color: #1C2530;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif, sans-serif;
  font-size: 14px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.decision-copy {
  justify-content: center;
  text-align: center;
  font-weight: 650;
}

.outcome-copy {
  justify-content: flex-start;
  text-align: left;
  font-weight: 550;
}
</style>
