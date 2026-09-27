/**
 * Turns one validated CV event into an incident, then uses the existing
 * nearest-responder assignment. This module does not decide that a collision
 * occurred and does not choose a responder on its own.
 */

import { assignNearestResponder, type AssignmentTools } from './assignment'
import { operationalPriority } from './priority'
import {
  CAMERA_COLLECTION,
  INCIDENT_COLLECTION,
  demoCameras,
  type Camera,
  type EvidenceStatus,
  type Incident,
  type IncidentObservation,
} from './demo-data'

export const CV_SCHEMA_VERSION = 1
export const CV_DETECTION_TYPE = 'possible_vehicle_collision'
const CAMERA_IDS = new Set(demoCameras.map((camera) => camera.cameraId))
const EVENT_ID = /^evt-[a-z0-9-]{8,80}$/

export type CvEvidence = {
  status: EvidenceStatus
  clipRef: string
  windowStart: number
  windowEnd: number
}

export type CvEvent = {
  schemaVersion: number
  eventId: string
  cameraId: string
  eventTimestamp: number
  detectionType: typeof CV_DETECTION_TYPE
  priority: 'low' | 'normal' | 'high'
  involvedTracks: string[]
  observableMetrics: Record<string, number | boolean | null>
  evidence: CvEvidence
  detectionMode: 'computer-vision' | 'demo_fallback'
  provenance: { pipeline: string; label: string }
}

type ToolFailure = { success: false; error: string }
type IngestData = {
  incidentId: string
  duplicate: boolean
  cameraId: string
  assignedResponderId: string
  routing: 'assigned' | 'unassigned'
  routingDetail: string
}

export type IngestResult = { success: true; data: IngestData } | ToolFailure

function failure(error: string): ToolFailure {
  return { success: false, error }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Clip-relative seconds, not a civil clock and not a dispatch time. */
export function clipSecondsToIso(seconds: number): string {
  const totalMs = Math.round(seconds * 1000)
  const date = new Date(totalMs)
  return date.toISOString().replace('.000Z', 'Z')
}

export function validateCvEvent(input: unknown): { ok: true; event: CvEvent } | { ok: false; error: string } {
  if (!isRecord(input)) return { ok: false, error: 'Event must be a JSON object.' }
  if (input.schemaVersion !== CV_SCHEMA_VERSION) {
    return { ok: false, error: `Unsupported schema version. Expected ${CV_SCHEMA_VERSION}.` }
  }
  if (typeof input.eventId !== 'string' || !EVENT_ID.test(input.eventId)) {
    return { ok: false, error: 'eventId must match evt- followed by 8–80 lowercase letters, numbers, or hyphens.' }
  }
  if (typeof input.cameraId !== 'string' || !CAMERA_IDS.has(input.cameraId)) {
    return { ok: false, error: 'cameraId must be one of the simulated cameras CAM-001 through CAM-010.' }
  }
  if (input.detectionType !== CV_DETECTION_TYPE) {
    return { ok: false, error: 'detectionType must be possible_vehicle_collision.' }
  }
  if (input.priority !== 'low' && input.priority !== 'normal' && input.priority !== 'high') {
    return { ok: false, error: 'priority must be low, normal, or high.' }
  }
  if (input.detectionMode !== 'computer-vision' && input.detectionMode !== 'demo_fallback') {
    return { ok: false, error: 'detectionMode must be computer-vision or demo_fallback.' }
  }
  if (typeof input.eventTimestamp !== 'number' || !Number.isFinite(input.eventTimestamp) || input.eventTimestamp < 0) {
    return { ok: false, error: 'eventTimestamp must be a non-negative number of seconds from the start of the clip.' }
  }
  if (!Array.isArray(input.involvedTracks) || input.involvedTracks.some((track) => typeof track !== 'string' || !/^\d+$/.test(track))) {
    return { ok: false, error: 'involvedTracks must be an array of numeric track id strings.' }
  }
  if (!isRecord(input.observableMetrics)) return { ok: false, error: 'observableMetrics must be an object.' }
  for (const [key, value] of Object.entries(input.observableMetrics)) {
    if (!/^[a-zA-Z][a-zA-Z0-9_]{0,40}$/.test(key)) return { ok: false, error: `Observable metric name is not allowed: ${key}` }
    if (typeof value !== 'number' && typeof value !== 'boolean' && value !== null) {
      return { ok: false, error: `Observable metric ${key} must be a number, boolean, or null.` }
    }
    if (typeof value === 'number' && !Number.isFinite(value)) {
      return { ok: false, error: `Observable metric ${key} is not a finite number.` }
    }
  }
  if (!isRecord(input.evidence)) return { ok: false, error: 'evidence is required.' }
  const evidence = input.evidence
  if (evidence.status !== 'unavailable' && evidence.status !== 'reference') {
    return { ok: false, error: 'evidence.status must be unavailable or reference.' }
  }
  if (typeof evidence.clipRef !== 'string') return { ok: false, error: 'evidence.clipRef must be a string.' }
  if (typeof evidence.windowStart !== 'number' || typeof evidence.windowEnd !== 'number') {
    return { ok: false, error: 'Evidence window start and end must be numbers.' }
  }
  if (!Number.isFinite(evidence.windowStart) || !Number.isFinite(evidence.windowEnd) || evidence.windowEnd < evidence.windowStart) {
    return { ok: false, error: 'Evidence window is invalid.' }
  }
  if (!isRecord(input.provenance) || typeof input.provenance.pipeline !== 'string' || typeof input.provenance.label !== 'string') {
    return { ok: false, error: 'provenance.pipeline and provenance.label are required strings.' }
  }
  return { ok: true, event: input as CvEvent }
}

function metricSummary(metrics: CvEvent['observableMetrics']): string {
  const parts = Object.entries(metrics)
    .filter((entry) => entry[1] !== null)
    .map(([key, value]) => `${key}=${value}`)
  return parts.length > 0 ? parts.join(', ') : 'no extra observable metrics'
}

function incidentFromEvent(event: CvEvent, camera: Camera): Incident {
  const observedAt = clipSecondsToIso(event.eventTimestamp)
  const decision = event.detectionMode === 'demo_fallback'
    ? {
        priority: event.priority,
        reasons: ['TEST / DEMO EVENT. Operational priority was not calculated from CV evidence.'],
      }
    : operationalPriority(event.observableMetrics, event.involvedTracks.length)
  const observations: IncidentObservation[] = [
    {
      observedAt,
      summary: [
        event.detectionMode === 'demo_fallback' ? 'TEST / DEMO EVENT' : 'Possible collision',
        `clip time ${event.eventTimestamp}s`,
        `tracks ${event.involvedTracks.join(', ') || 'none'}`,
        metricSummary(event.observableMetrics),
        event.provenance.label,
      ].join(' · '),
    },
  ]
  return {
    incidentId: event.eventId,
    cameraId: camera.cameraId,
    type: 'possible_vehicle_collision',
    detectedAt: observedAt,
    surfacedAt: observedAt,
    locationName: camera.locationName,
    latitude: camera.latitude,
    longitude: camera.longitude,
    status: 'open',
    participantTrackIds: event.involvedTracks,
    collisionEvidenceScore: typeof event.observableMetrics.collisionEvidenceScore === 'number' ? event.observableMetrics.collisionEvidenceScore : 0,
    priority: decision.priority,
    priorityReasons: decision.reasons,
    evidenceClip: event.evidence.clipRef,
    evidenceStatus: event.evidence.status,
    evidenceWindowStart: String(event.evidence.windowStart),
    evidenceWindowEnd: String(event.evidence.windowEnd),
    sourceEventId: event.eventId,
    assignedResponderId: '',
    detectionMode: event.detectionMode,
    observations,
  }
}

export function buildTestCvEvent(cameraId = 'CAM-001', nowSeconds = 1): CvEvent {
  return {
    schemaVersion: CV_SCHEMA_VERSION,
    eventId: `evt-test-demo-${cameraId.toLowerCase()}`,
    cameraId,
    eventTimestamp: nowSeconds,
    detectionType: CV_DETECTION_TYPE,
    priority: 'normal',
    involvedTracks: [],
    observableMetrics: { collisionEvidenceScore: 0 },
    evidence: { status: 'unavailable', clipRef: '', windowStart: 0, windowEnd: nowSeconds },
    detectionMode: 'demo_fallback',
    provenance: { pipeline: 'not-cv', label: 'TEST / DEMO EVENT. Not a computer-vision detection.' },
  }
}

export async function ingestCvEvent(tools: AssignmentTools, input: unknown): Promise<IngestResult> {
  const validated = validateCvEvent(input)
  if (!validated.ok) return failure(validated.error)
  const event = validated.event

  const existing = await tools.get<Incident>(INCIDENT_COLLECTION, event.eventId)
  if (existing.success) {
    const incident = existing.data.record.data
    return {
      success: true,
      data: {
        incidentId: incident.incidentId,
        duplicate: true,
        cameraId: incident.cameraId,
        assignedResponderId: incident.assignedResponderId ?? '',
        routing: incident.assignedResponderId ? 'assigned' : 'unassigned',
        routingDetail: 'This event was already ingested.',
      },
    }
  }
  if (!existing.error.includes('Record not found')) return existing

  const cameraResult = await tools.get<Camera>(CAMERA_COLLECTION, event.cameraId)
  if (!cameraResult.success) return failure(`Simulated camera ${event.cameraId} is not loaded yet.`)
  const incident = incidentFromEvent(event, cameraResult.data.record.data)
  const created = await tools.create(INCIDENT_COLLECTION, { ...incident }, event.eventId)
  if (!created.success) return created

  const routed = await assignNearestResponder(tools, event.eventId)
  if (!routed.success) {
    return {
      success: true,
      data: {
        incidentId: event.eventId,
        duplicate: false,
        cameraId: event.cameraId,
        assignedResponderId: '',
        routing: 'unassigned',
        routingDetail: routed.error,
      },
    }
  }
  return {
    success: true,
    data: {
      incidentId: event.eventId,
      duplicate: false,
      cameraId: event.cameraId,
      assignedResponderId: routed.data.responderId,
      routing: 'assigned',
      routingDetail: `Assigned simulated responder ${routed.data.responderId}.`,
    },
  }
}
