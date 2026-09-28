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

type RankedIncident = {
  incidentId: string
  cameraId: string
  locationName: string
  priority: 'high' | 'normal' | 'low'
  score: number
  detectedAt?: string
  tracks?: string[]
  reasons?: string[]
  responder?: string
}

async function rankedIncident(): Promise<RankedIncident> {
  const response = await fetch('http://127.0.0.1:5173/api/local/cv-events/notify-first', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  const payload = await response.json() as {
    success?: boolean
    error?: string
    data?: {
      incidentId: string
      cameraId: string
      locationName: string
      priority: 'high' | 'normal' | 'low'
      queue: RankedIncident[]
    }
  }
  if (!response.ok || !payload.success || !payload.data) {
    throw new Error(payload.error || 'The ranked incident could not be loaded.')
  }
  const first = payload.data.queue[0]
  if (!first || first.cameraId !== 'CAM-001' || first.priority !== 'high') {
    throw new Error('CAM-001 is not the current P1 incident.')
  }
  return {
    ...first,
    incidentId: payload.data.incidentId,
    detectedAt: new Date().toISOString(),
    tracks: ['20', '1'],
    reasons: ['a tracked vehicle flipped over', 'rollover is the first location sent to the authorized phone'],
    responder: 'UNIT-12',
  }
}

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
