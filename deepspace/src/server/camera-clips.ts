/**
 * Serves the ten existing demo clips for local playback.
 * Available only when the local debug flag is on. Missing media returns 404
 * and does not affect incident records.
 */

import { existsSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import type { Hono } from 'hono'
import { demoClipName } from '../domain/clips'
import type { AppContext } from '../../worker'

function clipPath(cameraId: string): string | null {
  const name = demoClipName(cameraId)
  if (!name) return null
  const roots = [
    process.env.NOTIFYC_CLIPS_DIR,
    join(process.cwd(), '..', 'data', 'cameras'),
    join(process.cwd(), 'data', 'cameras'),
  ].filter((root): root is string => Boolean(root))
  for (const root of roots) {
    const path = join(root, name)
    if (existsSync(path)) return path
  }
  return null
}

export function registerCameraClips(app: Hono<AppContext>): void {
  app.get('/api/local/cameras/:cameraId/video', (c) => {
    if (c.env.ALLOW_DEBUG_ROUTES !== 'true') {
      return c.json({ error: 'Demo clips are only served in the local demo.' }, 404)
    }
    const cameraId = c.req.param('cameraId').toUpperCase()
    const file = clipPath(cameraId)
    if (!file) return c.json({ error: `No demo clip is available for ${cameraId}.` }, 404)
    const size = statSync(file).size
    const bytes = readFileSync(file)
    const range = c.req.header('range')
    const headers = {
      'Content-Type': 'video/mp4',
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'no-store',
    }
    const payload = (chunk: Uint8Array) => chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength) as ArrayBuffer
    if (!range) {
      return new Response(payload(bytes), { headers: { ...headers, 'Content-Length': String(size) } })
    }
    const match = /bytes=(\d+)-(\d*)/.exec(range)
    if (!match) return c.body(null, 416)
    const start = Number(match[1])
    const end = match[2] ? Number(match[2]) : size - 1
    if (!Number.isFinite(start) || start < 0 || start >= size || end < start || end >= size) {
      return c.body(null, 416)
    }
    const slice = bytes.subarray(start, end + 1)
    return new Response(payload(slice), {
      status: 206,
      headers: {
        ...headers,
        'Content-Range': `bytes ${start}-${end}/${size}`,
        'Content-Length': String(slice.byteLength),
      },
    })
  })
}
