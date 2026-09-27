import { fileURLToPath } from 'node:url'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import generouted from '@generouted/react-router/plugin'
import { cloudflare } from '@cloudflare/vite-plugin'
import checker from 'vite-plugin-checker'
import { deepspaceBuild } from 'deepspace/build'

const appDir = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [
    react(),
    generouted(),
    cloudflare(),
    // The app id `define`, the preview-secret cleanup, and the client dedupe
    // hint — all shipped by the SDK so a fix to any of them arrives with a
    // version bump, not an app edit. The app id is read from the wrangler
    // config THIS build targets (wrangler.toml, or the env-flattened config
    // `deepspace deploy --env` generates); src/constants.ts is the only
    // consumer.
    deepspaceBuild({ appDir }),
    // Runs the Rules of Hooks lint (see eslint.config.js) automatically, so
    // there's no separate step to remember: a violation surfaces as an overlay
    // during `deepspace dev start` and fails the build during `deepspace deploy`.
    // That stops the cryptic "Minified React error #310 / #300" crash before
    // it can ship.
    checker({
      eslint: {
        lintCommand: 'eslint .',
        useFlatConfig: true,
      },
    }),
    demoClipDevServer(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    // generouted loads routes via `import.meta.glob`, which Vite's esbuild dep-scanner
    // does not evaluate — so every dep reachable only through the page tree (UI libs,
    // and deepspace via _app.tsx) is invisible to the cold scan, discovered late, and
    // triggers a re-optimize + full reload on first `dev` boot. That reload is where a
    // transient "Cannot read properties of null (reading 'useState')" can surface before
    // the error boundary recovers. Point the scanner at the route files (plus the html
    // entry) so the first optimize pass is complete and no late re-optimize fires.
    // Scoped to src/pages (NOT all of src) so worker-only modules — actions, cron, jobs,
    // ai, which import deepspace/worker — are not dragged into the client optimizer.
    // Dev-only; `vite build` ignores optimizeDeps.
    entries: ['./index.html', './src/pages/**/*.tsx'],
  },
})

/** Dev-server fallback for the local clip route. The worker process cwd is `/`,
 *  so it cannot see ../data/cameras. Vite itself can. */
function demoClipDevServer(): Plugin {
  return {
    name: 'notifyc-demo-clips',
    apply: 'serve',
    configureServer(server) {
      const handle = (req: import('node:http').IncomingMessage, res: import('node:http').ServerResponse, next: () => void) => {
        const match = /^\/api\/local\/cameras\/(CAM-\d{3})\/video$/.exec(req.url?.split('?')[0] ?? '')
        if (!match) return next()
        const number = Number(match[1].slice(4))
        if (number < 1 || number > 10) return next()
        const file = join(server.config.root, '..', 'data', 'cameras', `cam_${match[1].slice(4)}.mp4`)
        if (!existsSync(file)) return next()
        const size = statSync(file).size
        const range = req.headers.range
        res.setHeader('Content-Type', 'video/mp4')
        res.setHeader('Accept-Ranges', 'bytes')
        res.setHeader('Cache-Control', 'no-store')
        const send = (start: number, end: number, status: number) => {
          res.statusCode = status
          res.setHeader('Content-Length', String(end - start + 1))
          if (status === 206) res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`)
          createReadStream(file, { start, end }).pipe(res)
        }
        if (!range) return send(0, size - 1, 200)
        const parsed = /bytes=(\d+)-(\d*)/.exec(range)
        if (!parsed) {
          res.statusCode = 416
          res.end()
          return
        }
        const start = Number(parsed[1])
        const end = parsed[2] ? Number(parsed[2]) : size - 1
        if (!Number.isFinite(start) || start < 0 || start >= size || end < start || end >= size) {
          res.statusCode = 416
          res.end()
          return
        }
        send(start, end, 206)
      }
      server.middlewares.stack.unshift({ route: '', handle })
    },
  }
}
