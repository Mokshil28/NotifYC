/**
 * Simulated demo catalog for the NotifYC prototype.
 *
 * These rows are fictional placements and simulated units. They are not a
 * connection to any emergency service.
 *
 * Seeding inserts a row only when its known record id is missing. A later
 * status change is left alone.
 */

export const DEMO_SEEDED_AT = '2026-09-26T16:00:00.000Z'

export const CAMERA_COLLECTION = 'cameras'
export const INCIDENT_COLLECTION = 'incidents'
export const RESPONDER_COLLECTION = 'responders'
export const ASSIGNMENT_COLLECTION = 'assignments'

export type CameraStatus = 'active' | 'inactive'
export type IncidentType = 'vehicle-pedestrian' | 'vehicle-cyclist' | 'vehicle-vehicle' | 'possible_vehicle_collision'
export type IncidentStatus = 'open' | 'assigned' | 'accepted' | 'responding' | 'on_scene' | 'resolved'
export type IncidentPriority = 'low' | 'normal' | 'high'
export type DetectionMode = 'simulated' | 'computer-vision' | 'demo_fallback'
export type EvidenceStatus = 'unavailable' | 'reference'
export type ResponderType = 'mobile' | 'support'
export type ResponderStatus = 'available' | 'unavailable' | 'assigned' | 'responding' | 'on_scene'
export type AssignmentStatus = 'assigned' | 'accepted' | 'responding' | 'on_scene' | 'resolved'

export type IncidentObservation = {
  observedAt: string
  summary: string
}

export type Camera = {
  cameraId: string
  name: string
  locationName: string
  latitude: number
  longitude: number
  status: CameraStatus
  simulation: boolean
  createdAt: string
}

export type Incident = {
  incidentId: string
  cameraId: string
  type: IncidentType
  detectedAt: string
  surfacedAt: string
  locationName: string
  latitude: number
  longitude: number
  status: IncidentStatus
  participantTrackIds: string[]
  collisionEvidenceScore: number
  priority: IncidentPriority
  evidenceClip: string
  evidenceStatus?: EvidenceStatus
  evidenceWindowStart?: string
  evidenceWindowEnd?: string
  sourceEventId?: string
  priorityReasons?: string[]
  assignedResponderId: string
  detectionMode: DetectionMode
  observations: IncidentObservation[]
}

export type Responder = {
  responderId: string
  name: string
  type: ResponderType
  status: ResponderStatus
  latitude: number
  longitude: number
  simulation: boolean
  updatedAt: string
}

export type Assignment = {
  assignmentId: string
  incidentId: string
  responderId: string
  status: AssignmentStatus
  assignedAt: string
  acceptedAt: string
  resolvedAt: string
}

const ACTIVE_INCIDENT_STATUSES: ReadonlySet<IncidentStatus> = new Set([
  'open',
  'assigned',
  'accepted',
  'responding',
  'on_scene',
])

export const demoCameras: Camera[] = [
  { cameraId: 'CAM-001', name: 'CAM-001', locationName: 'Times Square', latitude: 40.758, longitude: -73.9855, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-002', name: 'CAM-002', locationName: 'Herald Square', latitude: 40.7496, longitude: -73.9877, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-003', name: 'CAM-003', locationName: 'Union Square', latitude: 40.7359, longitude: -73.9911, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-004', name: 'CAM-004', locationName: 'Washington Square', latitude: 40.7308, longitude: -73.9973, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-005', name: 'CAM-005', locationName: 'Columbus Circle', latitude: 40.7681, longitude: -73.9819, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-006', name: 'CAM-006', locationName: 'Grand Central', latitude: 40.7527, longitude: -73.9772, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-007', name: 'CAM-007', locationName: 'Brooklyn Bridge', latitude: 40.7061, longitude: -73.9969, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-008', name: 'CAM-008', locationName: 'Astor Place', latitude: 40.7299, longitude: -73.9906, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-009', name: 'CAM-009', locationName: 'Lincoln Center', latitude: 40.7725, longitude: -73.9835, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
  { cameraId: 'CAM-010', name: 'CAM-010', locationName: 'Houston Street', latitude: 40.725, longitude: -73.9965, status: 'active', simulation: true, createdAt: DEMO_SEEDED_AT },
]

export const demoResponders: Responder[] = [
  { responderId: 'UNIT-12', name: 'Officer 12', type: 'mobile', status: 'available', latitude: 40.758, longitude: -73.9855, simulation: true, updatedAt: DEMO_SEEDED_AT },
  { responderId: 'UNIT-18', name: 'Unit 18', type: 'support', status: 'unavailable', latitude: 40.7496, longitude: -73.9877, simulation: true, updatedAt: DEMO_SEEDED_AT },
  { responderId: 'UNIT-27', name: 'Unit 27', type: 'mobile', status: 'unavailable', latitude: 40.7359, longitude: -73.9911, simulation: true, updatedAt: DEMO_SEEDED_AT },
  { responderId: 'UNIT-31', name: 'Unit 31', type: 'support', status: 'unavailable', latitude: 40.7527, longitude: -73.9772, simulation: true, updatedAt: DEMO_SEEDED_AT },
  { responderId: 'UNIT-42', name: 'Unit 42', type: 'mobile', status: 'unavailable', latitude: 40.7061, longitude: -73.9969, simulation: true, updatedAt: DEMO_SEEDED_AT },
]

/** No collision incidents are seeded in this phase. */
export const demoIncidents: Incident[] = []

export function countAvailableResponders(records: ReadonlyArray<{ data: { status: string } }>): number {
  return records.filter((record) => record.data.status === 'available').length
}

export function activeIncidents<T extends { data: { status: string } }>(records: ReadonlyArray<T>): T[] {
  return records.filter((record) => ACTIVE_INCIDENT_STATUSES.has(record.data.status as IncidentStatus))
}

export function nextResponderStatus(status: 'available' | 'unavailable'): 'available' | 'unavailable' {
  return status === 'available' ? 'unavailable' : 'available'
}

type SeedToolResult = { success: true } | { success: false; error: string }

export interface DemoSeedTools {
  get(collection: string, recordId: string): Promise<SeedToolResult>
  create(collection: string, data: Record<string, unknown>, recordId: string): Promise<SeedToolResult>
}

export type DemoSeedSummary = {
  camerasCreated: number
  respondersCreated: number
  skipped: number
}

function isMissing(error: string): boolean {
  return error.includes('Record not found')
}

async function ensureRow(
  tools: DemoSeedTools,
  collection: string,
  recordId: string,
  data: Record<string, unknown>,
): Promise<{ created: boolean } | { error: string }> {
  const existing = await tools.get(collection, recordId)
  if (existing.success) return { created: false }
  if (!isMissing(existing.error)) return { error: existing.error }

  const created = await tools.create(collection, data, recordId)
  if (!created.success) return { error: created.error }
  return { created: true }
}

function asRecord(row: object): Record<string, unknown> {
  return { ...row }
}

/**
 * Insert missing demo cameras and responders. Existing rows are not rewritten,
 * so a simulated status toggle survives a later page load.
 */
export async function ensureDemoRecords(tools: DemoSeedTools): Promise<
  { success: true; data: DemoSeedSummary } | { success: false; error: string }
> {
  let camerasCreated = 0
  let respondersCreated = 0
  let skipped = 0

  for (const camera of demoCameras) {
    const result = await ensureRow(tools, CAMERA_COLLECTION, camera.cameraId, asRecord(camera))
    if ('error' in result) return { success: false, error: result.error }
    if (result.created) camerasCreated += 1
    else skipped += 1
  }

  for (const responder of demoResponders) {
    const result = await ensureRow(tools, RESPONDER_COLLECTION, responder.responderId, asRecord(responder))
    if ('error' in result) return { success: false, error: result.error }
    if (result.created) respondersCreated += 1
    else skipped += 1
  }

  return { success: true, data: { camerasCreated, respondersCreated, skipped } }
}
