import { describe, expect, it } from 'vitest'
import {
  assignNearestResponder,
  clearTestIncident,
  createTestIncident,
  progressPlan,
  TEST_INCIDENT_ID,
  type AssignmentTools,
} from './assignment'
import { demoCameras, demoResponders, type Assignment, type Camera, type Incident, type Responder } from './demo-data'

type Row = { recordId: string; data: Record<string, unknown> }

function memoryTools(seed: { cameras?: Camera[]; responders?: Responder[]; incidents?: Incident[]; assignments?: Assignment[] }) {
  const tables: Record<string, Row[]> = {
    cameras: (seed.cameras ?? []).map((data) => ({ recordId: data.cameraId, data: { ...data } })),
    responders: (seed.responders ?? []).map((data) => ({ recordId: data.responderId, data: { ...data } })),
    incidents: (seed.incidents ?? []).map((data) => ({ recordId: data.incidentId, data: { ...data } })),
    assignments: (seed.assignments ?? []).map((data) => ({ recordId: data.assignmentId, data: { ...data } })),
  }
  let sequence = 0

  const tools: AssignmentTools = {
    async get(collection, recordId) {
      const row = tables[collection]?.find((record) => record.recordId === recordId)
      if (!row) return { success: false, error: `Record not found: ${collection}/${recordId}` }
      return { success: true, data: { record: { recordId: row.recordId, data: row.data as never } } }
    },
    async query(collection, options) {
      const where = options?.where ?? {}
      const records = (tables[collection] ?? []).filter((record) =>
        Object.entries(where).every(([key, value]) => record.data[key] === value),
      )
      return { success: true, data: { records: records as never } }
    },
    async create(collection, data, recordId) {
      const incidentId = data.incidentId
      const rows = tables[collection] ?? []
      if (
        typeof incidentId === 'string' &&
        rows.some((record) => record.data.incidentId === incidentId && record.recordId !== recordId)
      ) {
        return { success: false, error: `Duplicate: a record with incidentId=${incidentId} already exists in ${collection}` }
      }
      const existing = recordId ? rows.find((record) => record.recordId === recordId) : undefined
      if (existing) {
        existing.data = { ...existing.data, ...data }
        return { success: true, data: { recordId: existing.recordId } }
      }
      sequence += 1
      const id = recordId ?? `${collection}-${sequence}`
      rows.push({ recordId: id, data: { ...data } })
      return { success: true, data: { recordId: id } }
    },
    async update(collection, recordId, data) {
      const row = tables[collection]?.find((record) => record.recordId === recordId)
      if (!row) return { success: false, error: `Record not found: ${collection}/${recordId}` }
      row.data = { ...row.data, ...data }
      return { success: true, data: { recordId } }
    },
    async remove(collection, recordId) {
      const rows = tables[collection] ?? []
      const index = rows.findIndex((record) => record.recordId === recordId)
      if (index < 0) return { success: false, error: `Record not found: ${collection}/${recordId}` }
      rows.splice(index, 1)
      return { success: true, data: { recordId } }
    },
  }

  return { tools, tables }
}

const openIncident: Incident = {
  incidentId: TEST_INCIDENT_ID,
  cameraId: 'CAM-007',
  type: 'possible_vehicle_collision',
  detectedAt: '2026-09-26T20:00:00.000Z',
  surfacedAt: '2026-09-26T20:00:00.000Z',
  locationName: 'Brooklyn Bridge',
  latitude: 40.7061,
  longitude: -73.9969,
  status: 'open',
  participantTrackIds: [],
  collisionEvidenceScore: 0,
  priority: 'high',
  evidenceClip: '',
  assignedResponderId: '',
  detectionMode: 'demo_fallback',
  observations: [],
}

describe('assignNearestResponder', () => {
  it('creates one assignment for the nearest available unit and marks both sides', async () => {
    const { tools, tables } = memoryTools({ responders: demoResponders, incidents: [openIncident] })
    const result = await assignNearestResponder(tools, TEST_INCIDENT_ID, '2026-09-26T20:01:00.000Z')
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.responderId).toBe('UNIT-42')
    expect(result.data.distanceKm).toBe(0)
    expect(tables.incidents[0]?.data.status).toBe('assigned')
    expect(tables.incidents[0]?.data.assignedResponderId).toBe('UNIT-42')
    expect(tables.assignments).toHaveLength(1)
    expect(tables.responders.find((row) => row.recordId === 'UNIT-42')?.data.status).toBe('assigned')
    expect(tables.responders.find((row) => row.recordId === 'UNIT-18')?.data.status).toBe('unavailable')
  })

  it('does not assign an unavailable closer unit', async () => {
    const responders = demoResponders.map((responder) =>
      responder.responderId === 'UNIT-42' ? { ...responder, status: 'unavailable' as const } : responder,
    )
    const { tools } = memoryTools({ responders, incidents: [openIncident] })
    const result = await assignNearestResponder(tools, TEST_INCIDENT_ID)
    expect(result.success).toBe(true)
    if (result.success) expect(result.data.responderId).not.toBe('UNIT-42')
  })

  it('refuses when no responder is available', async () => {
    const responders = demoResponders.map((responder) => ({ ...responder, status: 'unavailable' as const }))
    const { tools, tables } = memoryTools({ responders, incidents: [openIncident] })
    const result = await assignNearestResponder(tools, TEST_INCIDENT_ID)
    expect(result.success).toBe(false)
    expect(tables.assignments).toHaveLength(0)
    expect(tables.incidents[0]?.data.status).toBe('open')
  })

  it('refuses a second assignment for an incident that is already assigned', async () => {
    const { tools, tables } = memoryTools({ responders: demoResponders, incidents: [openIncident] })
    const first = await assignNearestResponder(tools, TEST_INCIDENT_ID)
    const second = await assignNearestResponder(tools, TEST_INCIDENT_ID)
    expect(first.success).toBe(true)
    expect(second.success).toBe(false)
    if (!second.success) expect(second.error).toMatch(/already/)
    expect(tables.assignments).toHaveLength(1)
  })
})

describe('demo incident lifecycle', () => {
  it('creates one fallback incident and reset frees the assigned unit', async () => {
    const camera = demoCameras.find((row) => row.cameraId === 'CAM-007')
    const { tools, tables } = memoryTools({ cameras: camera ? [camera] : [], responders: demoResponders })
    const created = await createTestIncident(tools, '2026-09-26T20:02:00.000Z')
    expect(created.success).toBe(true)
    expect(tables.incidents[0]?.data.detectionMode).toBe('demo_fallback')
    expect(tables.incidents[0]?.data.type).toBe('possible_vehicle_collision')

    const again = await createTestIncident(tools)
    expect(again.success).toBe(false)

    const assigned = await assignNearestResponder(tools, TEST_INCIDENT_ID)
    expect(assigned.success).toBe(true)
    const cleared = await clearTestIncident(tools, '2026-09-26T20:03:00.000Z')
    expect(cleared.success).toBe(true)
    expect(tables.incidents).toHaveLength(0)
    expect(tables.assignments).toHaveLength(0)
    expect(tables.responders.find((row) => row.recordId === 'UNIT-42')?.data.status).toBe('available')
  })
})

describe('progressPlan', () => {
  const now = '2026-09-26T20:04:00.000Z'

  it('accepts, then moves through responding and on scene, then frees the unit', () => {
    expect(progressPlan('accept', now)).toMatchObject({
      expectedStatus: 'assigned',
      assignment: { status: 'accepted', acceptedAt: now },
      incident: { status: 'accepted' },
    })
    expect(progressPlan('accept', now).responder).toBeUndefined()

    expect(progressPlan('en_route', now)).toMatchObject({
      expectedStatus: 'accepted',
      assignment: { status: 'responding' },
      incident: { status: 'responding' },
      responder: { status: 'responding', updatedAt: now },
    })
    expect(progressPlan('on_scene', now)).toMatchObject({
      expectedStatus: 'responding',
      assignment: { status: 'on_scene' },
      incident: { status: 'on_scene' },
      responder: { status: 'on_scene' },
    })
    expect(progressPlan('resolve', now)).toMatchObject({
      expectedStatus: 'on_scene',
      assignment: { status: 'resolved', resolvedAt: now },
      incident: { status: 'resolved' },
      responder: { status: 'available', updatedAt: now },
    })
  })
})
