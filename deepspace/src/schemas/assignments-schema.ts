import type { CollectionSchema } from 'deepspace/schema'
import { demoPermissions } from './demo-permissions'

export const assignmentsSchema: CollectionSchema = {
  name: 'assignments',
  columns: [
    { name: 'assignmentId', storage: 'text', interpretation: 'plain', required: true, immutable: true },
    {
      name: 'incidentId',
      storage: 'text',
      interpretation: { kind: 'reference', targetTable: 'incidents', displayColumn: 'incidentId' },
      required: true,
    },
    {
      name: 'responderId',
      storage: 'text',
      interpretation: { kind: 'reference', targetTable: 'responders', displayColumn: 'name' },
      required: true,
    },
    {
      name: 'status',
      storage: 'text',
      interpretation: {
        kind: 'select',
        options: ['assigned', 'accepted', 'responding', 'on_scene', 'resolved'],
      },
      required: true,
    },
    { name: 'assignedAt', storage: 'text', interpretation: { kind: 'datetime' }, required: true },
    { name: 'acceptedAt', storage: 'text', interpretation: { kind: 'datetime' }, default: '' },
    { name: 'resolvedAt', storage: 'text', interpretation: { kind: 'datetime' }, default: '' },
  ],
  // One assignment row per incident. The record room checks this on every write.
  uniqueOn: ['incidentId'],
  permissions: demoPermissions,
}
