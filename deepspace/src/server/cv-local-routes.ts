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
import type { Assignment, Incident, Responder } from '../domain/demo-data'
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

  app.post('/api/local/cv-events/reset-demo', async (c) => {
    if (c.env.ALLOW_DEBUG_ROUTES !== 'true') {
      return c.json({ success: false, error: 'Demo reset is only available in the local demo.' }, 404)
    }
    try {
      const tools = localTools(c.env)
      const incidents = await tools.query<Incident>('incidents')
      if (!incidents.success) return c.json(incidents, 400)
      const assignments = await tools.query<Assignment>('assignments')
      if (!assignments.success) return c.json(assignments, 400)
      const responders = await tools.query<Responder>('responders')
      if (!responders.success) return c.json(responders, 400)
      const now = new Date().toISOString()
      for (const assignment of assignments.data.records) await tools.remove('assignments', assignment.recordId)
      for (const incident of incidents.data.records) await tools.remove('incidents', incident.recordId)
      for (const responder of responders.data.records) {
        if (responder.data.status !== 'unavailable') {
          await tools.update('responders', responder.recordId, { status: 'available', updatedAt: now })
        }
      }
      return c.json({ success: true, data: { clearedIncidents: incidents.data.records.length } })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'DeepSpace record room is unavailable.'
      return c.json({ success: false, error: message }, 503)
    }
  })

  app.post('/api/local/responders/one-officer', async (c) => {
    if (c.env.ALLOW_DEBUG_ROUTES !== 'true') {
      return c.json({ success: false, error: 'Responder setup is only available in the local demo.' }, 404)
    }
    try {
      const tools = localTools(c.env)
      const responders = await tools.query<Responder>('responders')
      if (!responders.success) return c.json(responders, 400)
      const now = new Date().toISOString()
      for (const responder of responders.data.records) {
        const available = responder.data.responderId === 'UNIT-12'
        await tools.update('responders', responder.recordId, {
          status: available ? 'available' : 'unavailable',
          name: available ? 'Officer 12' : responder.data.name,
          updatedAt: now,
        })
      }
      return c.json({ success: true, data: { availableOfficer: 'UNIT-12' } })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'DeepSpace record room is unavailable.'
      return c.json({ success: false, error: message }, 503)
    }
  })

  app.post('/api/local/cv-events/notify-first', async (c) => {
    if (c.env.ALLOW_DEBUG_ROUTES !== 'true') {
      return c.json({ success: false, error: 'Notifications are only available in the local demo.' }, 404)
    }
    try {
      const tools = localTools(c.env)
      const incidents = await tools.query<Incident>('incidents')
      if (!incidents.success) return c.json(incidents, 400)
      const ranked = incidents.data.records
        .map((record) => record.data)
        .filter((incident) => incident.status !== 'resolved')
        .sort((left, right) => {
          const order = { high: 0, normal: 1, low: 2 }
          return order[left.priority] - order[right.priority] || right.collisionEvidenceScore - left.collisionEvidenceScore
        })
      const first = ranked[0]
      if (!first) return c.json({ success: false, error: 'No active incident to notify.' }, 400)
      return c.json({
        success: true,
        data: {
          incidentId: first.incidentId,
          cameraId: first.cameraId,
          locationName: first.locationName,
          priority: first.priority,
          queue: ranked.map((incident) => ({
            cameraId: incident.cameraId,
            locationName: incident.locationName,
            priority: incident.priority,
            score: incident.collisionEvidenceScore,
          })),
          detail: 'P1 rollover is selected for the Photon phone notification.',
        },
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'DeepSpace record room is unavailable.'
      return c.json({ success: false, error: message }, 503)
    }
  })
}