// Slidecraft variant-cycling endpoint (D47). Slidev merges this Vite config.
// GET  /__variants?slide=<sid>   -> km get-variants
// POST /__variant  {slide, dir}  -> km cycle-variant  (rename in place)
// km path: SLIDECRAFT_KM env, else the default install location.
import { defineConfig } from 'vite'
import { spawnSync } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'

const KM = process.env.SLIDECRAFT_KM
  || join(homedir(), '.claude', 'slidecraft', 'scripts', 'km.py')

function km(args: string[]) {
  const r = spawnSync('python', [KM, '--deck', process.cwd(), ...args],
    { encoding: 'utf-8' })
  return { code: r.status ?? 1, out: (r.stdout || '').trim(), err: r.stderr || '' }
}

export default defineConfig({
  plugins: [{
    name: 'slidecraft-variants',
    configureServer(server) {
      server.middlewares.use('/__variants', (req, res) => {
        const slide = new URL(req.url || '', 'http://x').searchParams.get('slide') || ''
        const r = km(['get-variants', '--slide', slide])
        res.setHeader('Content-Type', 'application/json')
        res.statusCode = r.code === 0 ? 200 : 404
        res.end(r.code === 0 ? r.out : JSON.stringify({ ok: false, err: r.err }))
      })
      server.middlewares.use('/__variant', (req, res) => {
        if (req.method !== 'POST') { res.statusCode = 405; return res.end() }
        let body = ''
        req.on('data', (c) => (body += c))
        req.on('end', () => {
          let slide: string, dir: string
          try {
            ({ slide, dir } = JSON.parse(body || '{}'))
          } catch {
            res.setHeader('Content-Type', 'application/json')
            res.statusCode = 400
            res.end(JSON.stringify({ ok: false, err: 'bad request body' }))
            return
          }
          const r = km(['cycle-variant', '--slide', slide, '--dir', dir])
          res.setHeader('Content-Type', 'application/json')
          res.statusCode = r.code === 0 ? 200 : 400
          res.end(r.code === 0 ? r.out : JSON.stringify({ ok: false, err: r.err }))
        })
      })
    },
  }],
})

// Task 0 fallback A: if the spike found the deck does not reload on rename,
// append a touch of slides.md after a successful cycle — simplest:
//   spawnSync('node', ['-e', 'require("fs").utimesSync("slides.md", new Date(), new Date())'])
// Add only if the spike required it.
