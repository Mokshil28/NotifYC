/**
 * Assignment and demo-incident orchestration.
 *
 * DeepSpace 0.33.1 has no transaction API. Each tools.create / tools.update /
 * tools.remove is its own record-room write. This module orders those writes
 * and refuses a second assignment when the incident is no longer open or an
 * assignment row for that incident already exists. The assignments schema
 * also declares uniqueOn: ['incidentId'], which the record room checks on
 * every write. A failure after the first write is reported; earlier writes
 * are rolled back one call at a time when that is still possible.
 */

import {
  ASSIGNMENT_COLLECTION,
  CAMERA_COLLECTION,
  INCIDENT_COLLECTION,
  RESPONDER_COLLECTION,
  type Assignment,
  type AssignmentStatus,
  type Camera,
  type Incident,
  type Responder,
  type ResponderStatus,
} from './demo-data'
import { selectNearestAvailable, type RoutableResponder } from './routing'

export const TEST_INCIDENT_ID = 'DEMO-TEST-INCIDENT'
export const TEST_INCIDENT_CAMERA_ID = 'CAM-007'

export type ProgressStep = 'accept' | 'en_route' | 'on_scene' | 'resolve'

type RecordEnvelope<T> = { recordId: string; data: T }

type ToolSuccess<T> = { success: true; data: T }
type ToolFailure = { success: false; error: string }
type ToolResult<T> = ToolSuccess<T> | ToolFailure

export interface AssignmentTools {
  get<T extends Record<string, unknown>>(collection: string, recordId: string): Promise<ToolResult<{ record: RecordEnvelope<T> }>>
  query<T extends Record<string, unknown>>(
    collection: string,
    options?: { where?: Record<string, unknown> },
  ): Promise<ToolResult<{ records: RecordEnvelope<T>[] }>>
  create(collection: string, data: Record<string, unknown>, recordId?: string): Promise<ToolResult<{ recordId: string }>>
  update(collection: string, recordId: string, data: Record<string, unknown>): Promise<ToolResult<{ recordId: string }>>
  remove(collection: string, recordId: string): Promise<ToolResult<{ recordId: string }>>
}

export type ProgressPlan = {
  expectedStatus: AssignmentStatus
  assignment: Partial<Assignment>
  incident: Partial<Incident>
  responder?: Partial<Responder>
}

const DISPATCH_RESPONDER_STATUSES: ReadonlySet<ResponderStatus> = new Set([
  'assigned',
  'responding',
  'on_scene',
])

export function progressPlan(step: ProgressStep, now: string): ProgressPlan {
  switch (step) {
    case 'accept':
      return {
        expectedStatus: 'assigned',
        assignment: { status: 'accepted', acceptedAt: now },
        incident: { status: 'accepted' },
      }
    case 'en_route':
      return {
        expectedStatus: 'accepted',
        assignment: { status: 'responding' },
        incident: { status: 'responding' },
        responder: { status: 'responding', updatedAt: now },
      }
    case 'on_scene':
      return {
        expectedStatus: 'responding',
        assignment: { status: 'on_scene' },
        incident: { status: 'on_scene' },
        responder: { status: 'on_scene', updatedAt: now },
      }
    case 'resolve':
      return {
        expectedStatus: 'on_scene',
        assignment: { status: 'resolved', resolvedAt: now },
        incident: { status: 'resolved' },
        responder: { status: 'available', updatedAt: now },
      }
  }
}

function failure(error: string): ToolFailure {
  return { success: false, error }
}

export async function assignNearestResponder(
  tools: AssignmentTools,
  incidentId: string,
  now = new Date().toISOString(),
): Promise<ToolResult<{ assignmentRecordId: string; responderId: string; distanceKm: number }>> {
  const incidentResult = await tools.get<Incident>(INCIDENT_COLLECTION, incidentId)
  if (!incidentResult.success) return incidentResult
  const incident = incidentResult.data.record
  if (incident.data.status !== 'open') {
    return failure('This incident already has a responder.')
  }

  const existing = await tools.query<Assignment>(ASSIGNMENT_COLLECTION, { where: { incidentId } })
  if (!existing.success) return existing
  if (existing.data.records.length > 0) {
    return failure('This incident already has an assignment.')
  }

  const responders = await tools.query<Responder>(RESPONDER_COLLECTION, { where: { status: 'available' } })
  if (!responders.success) return responders
  const candidates: RoutableResponder[] = responders.data.records.map((record) => ({
    responderId: record.data.responderId,
    status: record.data.status,
    latitude: record.data.latitude,
    longitude: record.data.longitude,
  }))
  const nearest = selectNearestAvailable(incident.data, candidates)
  if (!nearest) return failure('No available simulated responder.')
  const chosen = responders.data.records.find((record) => record.data.responderId === nearest.responder.responderId)
  if (!chosen) return failure('No available simulated responder.')

  const assignmentId = `ASG-${incidentId}`
  const created = await tools.create(ASSIGNMENT_COLLECTION, {
    assignmentId,
    incidentId,
    responderId: chosen.data.responderId,
    status: 'assigned',
    assignedAt: now,
    acceptedAt: '',
    resolvedAt: '',
  })
  if (!created.success) return created

  const incidentUpdate = await tools.update(INCIDENT_COLLECTION, incident.recordId, {
    status: 'assigned',
    assignedResponderId: chosen.data.responderId,
  })
  if (!incidentUpdate.success) {
    await tools.remove(ASSIGNMENT_COLLECTION, created.data.recordId)
    return incidentUpdate
  }

  const responderUpdate = await tools.update(RESPONDER_COLLECTION, chosen.recordId, {
    status: 'assigned',
    updatedAt: now,
  })
  if (!responderUpdate.success) {
    await tools.update(INCIDENT_COLLECTION, incident.recordId, {
      status: 'open',
      assignedResponderId: '',
    })
    await tools.remove(ASSIGNMENT_COLLECTION, created.data.recordId)
    return responderUpdate
  }

  return {
    success: true,
    data: {
      assignmentRecordId: created.data.recordId,
      responderId: chosen.data.responderId,
      distanceKm: nearest.distanceKm,
    },
  }
}

export async function createTestIncident(
  tools: AssignmentTools,
  now = new Date().toISOString(),
): Promise<ToolResult<{ incidentId: string }>> {
  const existing = await tools.get<Incident>(INCIDENT_COLLECTION, TEST_INCIDENT_ID)
  if (existing.success) return failure('A test incident already exists. Reset it before creating another.')
  if (!existing.error.includes('Record not found')) return existing

  const cameraResult = await tools.get<Camera>(CAMERA_COLLECTION, TEST_INCIDENT_CAMERA_ID)
  if (!cameraResult.success) return failure('Simulated camera CAM-007 is not loaded yet.')
  const camera = cameraResult.data.record.data

  const created = await tools.create(
    INCIDENT_COLLECTION,
    {
      incidentId: TEST_INCIDENT_ID,
      cameraId: camera.cameraId,
      type: 'possible_vehicle_collision',
      detectedAt: now,
      surfacedAt: now,
      locationName: camera.locationName,
      latitude: camera.latitude,
      longitude: camera.longitude,
      status: 'open',
      participantTrackIds: [],
      collisionEvidenceScore: 0,
      priority: 'high',
      evidenceClip: '',
      evidenceStatus: 'unavailable',
      evidenceWindowStart: '',
      evidenceWindowEnd: '',
      sourceEventId: '',
      priorityReasons: [],
      assignedResponderId: '',
      detectionMode: 'demo_fallback',
      observations: [],
    },
    TEST_INCIDENT_ID,
  )
  if (!created.success) return created
  return { success: true, data: { incidentId: TEST_INCIDENT_ID } }
}

export async function clearTestIncident(tools: AssignmentTools, now = new Date().toISOString()): Promise<ToolResult<{ cleared: boolean }>> {
  const incident = await tools.get<Incident>(INCIDENT_COLLECTION, TEST_INCIDENT_ID)
  if (!incident.success) {
    if (incident.error.includes('Record not found')) return { success: true, data: { cleared: false } }
    return incident
  }

  const assignments = await tools.query<Assignment>(ASSIGNMENT_COLLECTION, { where: { incidentId: TEST_INCIDENT_ID } })
  if (!assignments.success) return assignments

  for (const assignment of assignments.data.records) {
    const responder = await tools.get<Responder>(RESPONDER_COLLECTION, assignment.data.responderId)
    if (responder.success && DISPATCH_RESPONDER_STATUSES.has(responder.data.record.data.status)) {
      const restored = await tools.update(RESPONDER_COLLECTION, assignment.data.responderId, {
        status: 'available',
        updatedAt: now,
      })
      if (!restored.success) return restored
    }
    const removed = await tools.remove(ASSIGNMENT_COLLECTION, assignment.recordId)
    if (!removed.success) return removed
  }

  const removedIncident = await tools.remove(INCIDENT_COLLECTION, TEST_INCIDENT_ID)
  if (!removedIncident.success) return removedIncident
  return { success: true, data: { cleared: true } }
}
