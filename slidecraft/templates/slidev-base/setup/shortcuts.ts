// Slidecraft: remap ArrowUp/ArrowDown to audition slide variants in place (D47).
// On a slide with >1 rendering, Up/Down POST a cycle and Slidev reloads the
// swapped include; on a normal slide they fall through to Slidev's default nav.
import { defineShortcutsSetup } from '@slidev/types'

function sidOf(nav: any): string | null {
  // Task 0 assumption (b): current slide's source file path -> <sid>.
  const fp = nav?.currentSlideRoute?.meta?.slide?.filepath as string | undefined
  if (!fp) return null           // fallback: use the composer-emitted marker (spike result)
  const m = fp.replace(/\\/g, '/').match(/slides\/(.+?)\.md$/)
  return m ? m[1] : null
}

// Per-sid variant-count cache: populated lazily in the background so a
// keypress on a normal (uncached, no-variant) slide never blocks on the
// `/__variants` subprocess spawn. Only once a count >= 2 is cached for a sid
// does a later keypress intercept navigation and cycle instead.
const countCache = new Map<string, number>()

function refreshCount(sid: string): void {
  fetch(`/__variants?slide=${encodeURIComponent(sid)}`)
    .then((r) => (r.ok ? r.json() : { count: 1 }))
    .then((j) => countCache.set(sid, j.count ?? 1))
    .catch(() => {})   // leave uncached; a later keypress will retry
}

export default defineShortcutsSetup((nav: any, base: any[]) => {
  function cycle(dir: 'up' | 'down', fallback: () => void) {
    const sid = sidOf(nav)
    if (!sid) return fallback()   // no sid resolved: normal nav

    const cached = countCache.get(sid)
    if (cached === undefined) {
      // Count not yet known: never block this keypress waiting on the
      // subprocess — navigate immediately and warm the cache in the
      // background for the next keypress on this slide.
      fallback()
      refreshCount(sid)
      return
    }
    if (cached < 2) return fallback()   // known normal slide: no variants

    fetch('/__variant', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slide: sid, dir }),
    })
    // Slidev reloads on the file swap; URL keeps the slide index. If the spike
    // found it jumps to slide 1, uncomment: nav.go(nav.currentPage)
  }
  return [
    ...base,
    { key: 'up', fn: () => cycle('up', () => nav.prevSlide()), autoRepeat: true },
    { key: 'down', fn: () => cycle('down', () => nav.nextSlide()), autoRepeat: true },
  ]
})
