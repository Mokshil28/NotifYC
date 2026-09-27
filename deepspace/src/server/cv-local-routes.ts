/**
 * Local-only intake for the Python CV runner.
 *
 * DeepSpace action routes require a signed-in caller. This demo adapter is
 * the documented app worker, not a new platform API. It is refused unless
 * the local debug flag is exactly "true", which `deepspace dev` sets and
 * production does not.
 */

import type { Hono } from 'hono'
import { buildTestCvEvent, ingestCvEvent } from '../domain/cv-ingest'
import { createActionTools } from './action-routes'
import type { AppContext, Env } from '../../worker'

function localTools(env: Env) {
  return createActionTools(env, env.OWNER_USER_ID, '')
}

export function registerLocalCvRoutes(app: Hono<AppContext>): void {
  app.post('/api/local/cv-events', async (c) => {
    if (c.env.ALLOW_DEBUG_ROUTES !== 'true') {
      return c.json({ success: false, error: 'CV ingestion is only available in the local demo.' }, 404)
    }
    let body: unknown
    try {
      body = await c.req.json()
    } catch {
      return c.json({ success: false, error: 'Request body must be JSON.' }, 400)
    }
    try {
      const result = await ingestCvEvent(localTools(c.env), body)
      return c.json(result, result.success ? 200 : 400)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'DeepSpace record room is unavailable.'
      return c.json({ success: false, error: message }, 503)
    }
  })

  app.post('/api/local/cv-events/test', async (c) => {
    if (c.env.ALLOW_DEBUG_ROUTES !== 'true') {
      return c.json({ success: false, error: 'Test events are only available in the local demo.' }, 404)
    }
    let cameraId = 'CAM-001'
    try {
      const body = await c.req.json<Record<string, unknown>>()
      if (typeof body.cameraId === 'string') cameraId = body.cameraId
    } catch {
      cameraId = 'CAM-001'
    }
    try {
      const result = await ingestCvEvent(localTools(c.env), buildTestCvEvent(cameraId))
      return c.json(result, result.success ? 200 : 400)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'DeepSpace record room is unavailable.'
      return c.json({ success: false, error: message }, 503)
    }
  })
}
