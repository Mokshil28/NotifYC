/**
 * Local bridge for the presentation app.
 * The Cloudflare worker cannot open the Photon socket, so this process does.
 *
 *   node --experimental-strip-types src/server/notify-bridge.ts
 */

import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

function sendRankedAlert(): Promise<{ ok: boolean; cameraId: string; detail: string }> {
  const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
  const python = resolve(repo, '.venv/bin/python')
  return new Promise((resolveResult) => {
    const child = spawn(python, ['-m', 'briefing.run_p1'], { cwd: repo })
    let output = ''
    child.stdout.on('data', (chunk) => { output += String(chunk) })
    child.stderr.on('data', (chunk) => { output += String(chunk) })
    child.on('error', (error) => resolveResult({ ok: false, cameraId: 'CAM-001', detail: error.message }))
    child.on('close', (code) => {
      const line = output.trim().split('\n').find((item) => item.startsWith('{')) ?? ''
      try {
        const parsed = JSON.parse(line) as { ok?: boolean; detail?: string }
        resolveResult({ ok: code === 0 && parsed.ok === true, cameraId: 'CAM-001', detail: parsed.detail || output.trim() })
      } catch {
        resolveResult({ ok: false, cameraId: 'CAM-001', detail: output.trim() || 'P1 briefing did not return a result.' })
      }
    })
  })
}

const server = createServer((req, res) => {
  if (req.method !== 'POST' || req.url !== '/notify-first') {
    res.writeHead(404, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ success: false, error: 'Not found.' }))
    return
  }
  void sendRankedAlert()
    .then((result) => {
      res.writeHead(result.ok ? 200 : 503, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ success: result.ok, data: result, error: result.ok ? undefined : result.detail }))
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : 'Notification failed.'
      res.writeHead(503, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ success: false, error: message }))
    })
})

let sentAutomatically = false

async function sendWhenReady(): Promise<void> {
  if (sentAutomatically) return
  try {
    const result = await sendRankedAlert()
    if (!result.ok) {
      console.log(`[NotifYC] P1 is ranked. Waiting for the authorized phone conversation. ${result.detail}`)
      return
    }
    sentAutomatically = true
    console.log(`[NotifYC] P1 notification sent automatically for ${result.cameraId}.`)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Automatic notification failed.'
    console.log(`[NotifYC] P1 notification is waiting. ${message}`)
  }
}

server.listen(8788, '127.0.0.1', () => {
  console.log('[NotifYC] Automatic P1 notification is running.')
  void sendWhenReady()
  setInterval(() => { void sendWhenReady() }, 5000)
})
