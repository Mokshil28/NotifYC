import { describe, expect, it } from 'vitest'
import { lintSchema } from 'deepspace/worker'
import { assignmentsSchema } from '../schemas/assignments-schema'
import { camerasSchema } from '../schemas/cameras-schema'
import { incidentsSchema } from '../schemas/incidents-schema'
import { respondersSchema } from '../schemas/responders-schema'
import {
  activeIncidents,
  countAvailableResponders,
  demoCameras,
  demoIncidents,
  demoResponders,
  ensureDemoRecords,
  type DemoSeedTools,
} from './demo-data'

describe('NotifYC demo schemas', () => {
  it('lint clean', () => {
    expect(lintSchema(camerasSchema)).toEqual([])
    expect(lintSchema(incidentsSchema)).toEqual([])
    expect(lintSchema(respondersSchema)).toEqual([])
    expect(lintSchema(assignmentsSchema)).toEqual([])
  })
})

describe('demo catalog', () => {
  it('seeds ten active simulated cameras and no incidents', () => {
    expect(demoCameras.map((camera) => camera.cameraId)).toEqual([
      'CAM-001', 'CAM-002', 'CAM-003', 'CAM-004', 'CAM-005',
      'CAM-006', 'CAM-007', 'CAM-008', 'CAM-009', 'CAM-010',
    ])
    expect(demoCameras.every((camera) => camera.simulation && camera.status === 'active')).toBe(true)
    expect(demoIncidents).toEqual([])
  })

  it('seeds five simulated responders with mixed availability', () => {
    expect(demoResponders.map((responder) => responder.responderId)).toEqual([
      'UNIT-12', 'UNIT-18', 'UNIT-27', 'UNIT-31', 'UNIT-42',
    ])
    expect(demoResponders.every((responder) => responder.simulation)).toBe(true)
    expect(countAvailableResponders(demoResponders.map((responder) => ({ data: responder })))).toBe(3)
    expect(demoResponders.some((responder) => responder.status === 'unavailable')).toBe(true)
  })

  it('counts active incidents from record status', () => {
    const records = [
      { data: { status: 'open' } },
      { data: { status: 'assigned' } },
      { data: { status: 'resolved' } },
    ]
    expect(activeIncidents(records)).toHaveLength(2)
    expect(activeIncidents([])).toEqual([])
  })
})

describe('ensureDemoRecords', () => {
  it('creates missing rows and leaves existing responder status untouched', async () => {
    const created: string[] = []
    const tools: DemoSeedTools = {
      async get(_collection, recordId) {
        if (recordId === 'UNIT-12') return { success: true }
        return { success: false, error: 'Record not found: responders/UNIT-12' }
      },
      async create(_collection, _data, recordId) {
        created.push(recordId)
        return { success: true }
      },
    }

    const result = await ensureDemoRecords(tools)
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.respondersCreated).toBe(4)
      expect(result.data.camerasCreated).toBe(10)
      expect(result.data.skipped).toBe(1)
    }
    expect(created).not.toContain('UNIT-12')
  })
})
