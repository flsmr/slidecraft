<!--
  MindMap.vue — reusable Slidev component wrapping `simple-mind-map`.

  The mind-map-expert agent copies this file into a deck's `components/` folder
  (Slidev auto-registers it) and then uses it in a slide:

      <MindMap :data="treeData" layout="mindMap" />

  WHY a live component (not inlined SVG): Slidev's markdown→Vue compiler mangles
  raw inlined <svg>, and `/figures/...` <img> paths break the import-guard on
  Windows. A registered Vue component renders cleanly inside a theme slot.

  simple-mind-map is browser-only, so it is imported dynamically inside onMounted
  (never at module top) to survive Slidev's build/SSR pass.

  Dependency (run once per deck):  npm i simple-mind-map

  Exact theme keys / layout names: https://wanglin2.github.io/mind-map-docs/
-->
<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  // simple-mind-map tree: { data: { text, uid? }, children: [ ... ] }
  // cross-links: give nodes a `uid` and the source node
  // `data.associativeLineTargets: [targetUid, ...]`
  data: { type: Object, required: true },
  // logicalStructure | logicalStructureLeft | mindMap | organizationStructure
  // | catalogOrganization | fishbone | timeline | timeline2 | verticalTimeline
  layout: { type: String, default: 'mindMap' },
  // brand palette (overridable per slide)
  accent: { type: String, default: '#FF4757' },
  ink: { type: String, default: '#1D1D1F' },
})

const el = ref(null)
let mindMap = null

async function render() {
  if (!el.value) return
  // client-only imports
  const { default: MindMap } = await import('simple-mind-map')
  try {
    const { default: AssociativeLine } = await import('simple-mind-map/src/plugins/AssociativeLine.js')
    MindMap.usePlugin(AssociativeLine)
  } catch (e) { /* cross-links optional; ignore if plugin path differs in your version */ }

  if (mindMap) { try { mindMap.destroy() } catch (e) {} mindMap = null }

  mindMap = new MindMap({
    el: el.value,
    data: props.data,
    layout: props.layout,
    readonly: true,          // presentation, not editing
    enableFreeDrag: false,
    themeConfig: {
      backgroundColor: 'transparent',
      lineStyle: 'curve',    // organic curved connectors
      lineColor: props.ink,
      lineWidth: 2,
      rootLineKeepSameInCurve: true,
      paddingX: 14,
      paddingY: 8,
      fontFamily: "'Source Sans Pro', system-ui, sans-serif",
      root:   { fillColor: props.accent, color: '#FFFFFF', fontSize: 22, borderRadius: 10, borderWidth: 0, paddingX: 18, paddingY: 10 },
      second: { fillColor: props.ink,    color: '#FFFFFF', fontSize: 16, borderRadius: 8,  borderWidth: 0, paddingX: 12, paddingY: 6 },
      node:   { fillColor: 'transparent', color: props.ink, fontSize: 14, borderWidth: 0 },
    },
  })

  // fit the whole map into the slot after each (re)render.
  // fit(getRbox, enlarge, padding): enlarge=true also scales a small map UP to fill.
  const doFit = () => { try { mindMap.view.fit(undefined, true, 16) } catch (e) {} }
  mindMap.on('node_tree_render_end', doFit)
  setTimeout(doFit, 150)
}

onMounted(render)
watch(() => [props.data, props.layout], render, { deep: true })
onBeforeUnmount(() => { try { mindMap && mindMap.destroy() } catch (e) {} })
</script>

<template>
  <div ref="el" class="mindmap-canvas"></div>
</template>

<style scoped>
.mindmap-canvas { width: 100%; height: 100%; min-height: 200px; }
</style>
