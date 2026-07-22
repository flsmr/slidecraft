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

async function count(sid: string): Promise<number> {
  try {
    const r = await fetch(`/__variants?slide=${encodeURIComponent(sid)}`)
    if (!r.ok) return 1
    return (await r.json()).count ?? 1
  } catch { return 1 }
}

export default defineShortcutsSetup((nav: any, base: any[]) => {
  async function cycle(dir: 'up' | 'down', fallback: () => void) {
    const sid = sidOf(nav)
    if (!sid || (await count(sid)) < 2) return fallback()   // normal nav
    await fetch('/__variant', {
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
