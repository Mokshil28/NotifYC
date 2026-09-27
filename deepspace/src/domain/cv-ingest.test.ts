import { describe, expect, it } from 'vitest'
import { assignNearestResponder, progressPlan, TEST_INCIDENT_ID } from './assignment'
import { buildTestCvEvent, ingestCvEvent, validateCvEvent, type CvEvent } from './cv-ingest'
import { demoCameras, demoResponders, type Assignment, type Camera, type Incident, type Responder } from './demo-data'

type Row = { recordId: string; data: Record<string, unknown> }

function memoryTools(seed: { cameras?: Camera[]; responders?: Responder[]; incidents?: Incident[]; assignments?: Assignment[] }) {
  const tables: Record<string, Row[]> = {
    cameras: (seed.cameras ?? demoCameras).map((data) => ({ recordId: data.cameraId, data: { ...data } })),
    responders: (seed.responders ?? demoResponders).map((data) => ({ recordId: data.responderId, data: { ...data } })),
    incidents: (seed.incidents ?? []).map((data) => ({ recordId: data.incidentId, data: { ...data } })),
    assignments: (seed.assignments ?? []).map((data) => ({ recordId: data.assignmentId, data: { ...data } })),
  }

  return {
    tables,
    tools: {
      async get(collection: string, recordId: string) {
        const row = tables[collection]?.find((record) => record.recordId === recordId)
        if (!row) return { success: false as const, error: `Record not found: ${collection}/${recordId}` }
        return { success: true as const, data: { record: { recordId: row.recordId, data: row.data as never } } }
      },
      async query(collection: string, options?: { where?: Record<string, unknown> }) {
        const where = options?.where ?? {}
        const records = (tables[collection] ?? []).filter((record) =>
          Object.entries(where).every(([key, value]) => record.data[key] === value),
        )
        return { success: true as const, data: { records: records as never } }
      },
      async create(collection: string, data: Record<string, unknown>, recordId?: string) {
        const id = recordId ?? `${collection}-${tables[collection].length + 1}`
        if (tables[collection].some((record) => record.recordId === id)) {
          return { success: false as const, error: 'Duplicate record' }
        }
        tables[collection].push({ recordId: id, data: { ...data } })
        return { success: true as const, data: { recordId: id } }
      },
      async update(collection: string, recordId: string, data: Record<string, unknown>) {
        const row = tables[collection]?.find((record) => record.recordId === recordId)
        if (!row) return { success: false as const, error: `Record not found: ${collection}/${recordId}` }
        row.data = { ...row.data, ...data }
        return { success: true as const, data: { recordId } }
      },
      async remove(collection: string, recordId: string) {
        const rows = tables[collection] ?? []
        const index = rows.findIndex((record) => record.recordId === recordId)
        if (index < 0) return { success: false as const, error: `Record not found: ${collection}/${recordId}` }
        rows.splice(index, 1)
        return { success: true as const, data: { recordId } }
      },
    },
  }
}

function event(overrides: Partial<CvEvent> = {}): CvEvent {
  return {
    schemaVersion: 1,
    eventId: 'evt-cam-001-track-4-20',
    cameraId: 'CAM-001',
    eventTimestamp: 1.969,
    detectionType: 'possible_vehicle_collision',
    priority: 'normal',
    involvedTracks: ['4', '20'],
    observableMetrics: { collisionEvidenceScore: 70, closing_speed_px_s: 120 },
    evidence: { status: 'reference', clipRef: 'outputs/tracking/cam_001_tracked.mp4', windowStart: 1.2, windowEnd: 1.969 },
    detectionMode: 'computer-vision',
    provenance: { pipeline: 'cv/detect_collisions.py', label: 'Existing collision state machine' },
    ...overrides,
  }
}

describe('validateCvEvent', () => {
  it('rejects an unknown camera', () => {
    const result = validateCvEvent(event({ cameraId: 'CAM-099' }))
    expect(result.ok).toBe(false)
  })

  it('rejects a malformed event', () => {
    const result = validateCvEvent(event({ eventTimestamp: -1, evidence: { status: 'reference', clipRef: '', windowStart: 4, windowEnd: 1 } }))
    expect(result.ok).toBe(false)
  })
})

describe('ingestCvEvent', () => {
  it('creates one incident for a valid event and keeps the camera', async () => {
    const { tools, tables } = memoryTools({})
    const result = await ingestCvEvent(tools, event())
    expect(result.success).toBe(true)
    const row = tables.incidents.find((item) => item.recordId === 'evt-cam-001-track-4-20')
    expect(row?.data.cameraId).toBe('CAM-001')
    expect(row?.data.type).toBe('possible_vehicle_collision')
    expect(row?.data.locationName).toBe('Times Square')
  })

  it('does not create a second incident for the same event', async () => {
    const { tools, tables } = memoryTools({})
    await ingestCvEvent(tools, event())
    const again = await ingestCvEvent(tools, event())
    expect(again.success).toBe(true)
    if (again.success) expect(again.data.duplicate).toBe(true)
    expect(tables.incidents).toHaveLength(1)
    expect(tables.assignments).toHaveLength(1)
  })

  it('assigns the nearest available simulated responder', async () => {
    const { tools } = memoryTools({})
    const result = await ingestCvEvent(tools, event())
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.routing).toBe('assigned')
      expect(result.data.assignedResponderId).toBe('UNIT-12')
    }
  })

  it('does not assign a responder who is already on another incident', async () => {
    const { tools, tables } = memoryTools({})
    await ingestCvEvent(tools, event())
    const second = await ingestCvEvent(tools, event({
      eventId: 'evt-cam-003-second-event',
      cameraId: 'CAM-003',
      involvedTracks: ['1', '2'],
      observableMetrics: { collisionEvidenceScore: 10 },
    }))
    expect(second.success).toBe(true)
    if (second.success) {
      expect(second.data.assignedResponderId).not.toBe('UNIT-12')
      expect(second.data.routing).toBe('assigned')
    }
    expect(tables.incidents).toHaveLength(2)
    expect(tables.responders.find((row) => row.recordId === 'UNIT-12')?.data.status).toBe('assigned')
  })

  it('keeps the incident when no responder is available', async () => {
    const responders = demoResponders.map((responder) => ({ ...responder, status: 'unavailable' as const }))
    const { tools, tables } = memoryTools({ responders })
    const result = await ingestCvEvent(tools, event())
    expect(result.success).toBe(true)
    if (result.success) expect(result.data.routing).toBe('unassigned')
    expect(tables.incidents).toHaveLength(1)
    expect(tables.incidents[0]?.data.status).toBe('open')
    expect(tables.assignments).toHaveLength(0)
  })

  it('creates the incident when evidence is unavailable', async () => {
    const { tools, tables } = memoryTools({})
    const result = await ingestCvEvent(tools, event({
      evidence: { status: 'unavailable', clipRef: '', windowStart: 0, windowEnd: 1 },
    }))
    expect(result.success).toBe(true)
    expect(tables.incidents[0]?.data.evidenceStatus).toBe('unavailable')
  })

  it('makes the incident and assignment readable by the existing queries', async () => {
    const { tools } = memoryTools({})
    const ingested = await ingestCvEvent(tools, event())
    expect(ingested.success).toBe(true)
    const assignments = await tools.query('assignments', { where: { incidentId: 'evt-cam-001-track-4-20' } })
    expect(assignments.success).toBe(true)
    if (assignments.success) expect(assignments.data.records).toHaveLength(1)
  })

  it('labels a development test event without replacing the manual demo incident', async () => {
    const { tools, tables } = memoryTools({})
    const result = await ingestCvEvent(tools, buildTestCvEvent())
    expect(result.success).toBe(true)
    const row = tables.incidents[0]
    expect(row?.data.detectionMode).toBe('demo_fallback')
    const observations = row?.data.observations as { summary?: string }[]
    expect(observations[0]?.summary).toContain('TEST / DEMO EVENT')
    expect(row?.recordId).not.toBe(TEST_INCIDENT_ID)
  })
})

describe('existing demo incident flow', () => {
  it('still routes and walks accept, en route, on scene, and resolve', () => {
    expect(progressPlan('accept', '2026-09-27T00:00:00.000Z').assignment.status).toBe('accepted')
    expect(progressPlan('en_route', '2026-09-27T00:00:00.000Z').incident.status).toBe('responding')
    expect(progressPlan('on_scene', '2026-09-27T00:00:00.000Z').incident.status).toBe('on_scene')
    expect(progressPlan('resolve', '2026-09-27T00:00:00.000Z').responder?.status).toBe('available')
    expect(assignNearestResponder).toBeTypeOf('function')
  })
})
