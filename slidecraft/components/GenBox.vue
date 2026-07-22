<!--
GenBox.vue

The ONE canonical "card" used by every structural diagram, so all boxes share the exact
FlowDiagram look: paper fill, 8px corner radius, 1px hairline frame on the top/right/bottom
sides, and a 3px accent that hugs the rounded corners on the LEFT (rendered as a clipped
fill — the SVG equivalent of CSS `border-left` + `border-radius`, so it sits flush inside the
outline instead of as a detached stroked bracket).

Props:
- x, y, w, h : box geometry (SVG user units).
- accent     : left-bar colour (default navy). Pass a theme token or hex.
- r          : corner radius (default 8, matching FlowDiagram).
- fill       : surface fill (default paper).
- bar        : left-bar width (default 3).
- emphasis   : Boolean — slightly stronger frame (accent-tinted) for a "primary"/root/current
               card, still the same shape/geometry.
-->
<script setup>
import { computed } from 'vue'
import { nextId } from './_slotAuthoring'

const props = defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  w: { type: Number, required: true },
  h: { type: Number, required: true },
  accent: { type: String, default: '#28527A' },
  r: { type: Number, default: 8 },
  fill: { type: String, default: '#F5F6F8' },
  bar: { type: Number, default: 3 },
  emphasis: { type: Boolean, default: false },
})

const clipId = nextId('genbox')

// Frame = top + right + bottom sides only (the left side is the accent bar), traced from the
// top-left tangent to the bottom-left tangent so it joins the accent seamlessly at the corners.
const framePath = computed(() => {
  const { x, y, w, h, r } = props
  return `M ${x + r} ${y} H ${x + w - r} A ${r} ${r} 0 0 1 ${x + w} ${y + r} `
    + `V ${y + h - r} A ${r} ${r} 0 0 1 ${x + w - r} ${y + h} H ${x + r}`
})
</script>

<template>
  <g>
    <defs>
      <clipPath :id="clipId">
        <rect :x="x" :y="y" :width="w" :height="h" :rx="r" />
      </clipPath>
    </defs>
    <rect class="genbox-surface" :x="x" :y="y" :width="w" :height="h" :rx="r" :fill="fill" />
    <rect :x="x" :y="y" :width="bar" :height="h" :fill="accent" :clip-path="`url(#${clipId})`" />
    <path
      class="genbox-frame"
      :class="{ 'is-emphasis': emphasis }"
      :d="framePath"
      :style="emphasis ? { stroke: accent } : null"
    />
  </g>
</template>

<style scoped>
.genbox-frame {
  fill: none;
  stroke: #DFE3E8;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.genbox-frame.is-emphasis {
  stroke-width: 1.5;
}
</style>
