import type { CollectionSchema } from 'deepspace/schema'
import { demoPermissions } from './demo-permissions'

export const incidentsSchema: CollectionSchema = {
  name: 'incidents',
  columns: [
    { name: 'incidentId', storage: 'text', interpretation: 'plain', required: true, immutable: true },
    {
      name: 'cameraId',
      storage: 'text',
      interpretation: { kind: 'reference', targetTable: 'cameras', displayColumn: 'name' },
      required: true,
    },
    {
      name: 'type',
      storage: 'text',
      interpretation: {
        kind: 'select',
        options: ['vehicle-pedestrian', 'vehicle-cyclist', 'vehicle-vehicle', 'possible_vehicle_collision'],
      },
      required: true,
    },
    { name: 'detectedAt', storage: 'text', interpretation: { kind: 'datetime' }, required: true },
    { name: 'surfacedAt', storage: 'text', interpretation: { kind: 'datetime' }, required: true },
    { name: 'locationName', storage: 'text', interpretation: 'plain', required: true },
    { name: 'latitude', storage: 'number', interpretation: 'plain', required: true },
    { name: 'longitude', storage: 'number', interpretation: 'plain', required: true },
    {
      name: 'status',
      storage: 'text',
      interpretation: {
        kind: 'select',
        options: ['open', 'assigned', 'accepted', 'responding', 'on_scene', 'resolved'],
      },
      required: true,
    },
    { name: 'participantTrackIds', storage: 'text', interpretation: { kind: 'json' }, required: true },
    { name: 'collisionEvidenceScore', storage: 'number', interpretation: 'plain', required: true },
    {
      name: 'priority',
      storage: 'text',
      interpretation: { kind: 'select', options: ['low', 'normal', 'high'] },
      required: true,
    },
    { name: 'evidenceClip', storage: 'text', interpretation: 'plain', default: '' },
    {
      name: 'assignedResponderId',
      storage: 'text',
      interpretation: { kind: 'reference', targetTable: 'responders', displayColumn: 'name' },
      default: '',
    },
    {
      name: 'detectionMode',
      storage: 'text',
      interpretation: { kind: 'select', options: ['simulated', 'computer-vision', 'demo_fallback'] },
      required: true,
    },
    { name: 'observations', storage: 'text', interpretation: { kind: 'json' }, required: true },
  ],
  uniqueOn: ['incidentId'],
  permissions: demoPermissions,
}
