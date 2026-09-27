import type { CollectionSchema } from 'deepspace/schema'
import { demoPermissions } from './demo-permissions'

export const camerasSchema: CollectionSchema = {
  name: 'cameras',
  columns: [
    { name: 'cameraId', storage: 'text', interpretation: 'plain', required: true, immutable: true },
    { name: 'name', storage: 'text', interpretation: 'plain', required: true },
    { name: 'locationName', storage: 'text', interpretation: 'plain', required: true },
    { name: 'latitude', storage: 'number', interpretation: 'plain', required: true },
    { name: 'longitude', storage: 'number', interpretation: 'plain', required: true },
    {
      name: 'status',
      storage: 'text',
      interpretation: { kind: 'select', options: ['active', 'inactive'] },
      required: true,
    },
    {
      name: 'simulation',
      storage: 'number',
      interpretation: { kind: 'boolean' },
      required: true,
    },
    {
      name: 'createdAt',
      storage: 'text',
      interpretation: { kind: 'datetime' },
      required: true,
    },
  ],
  uniqueOn: ['cameraId'],
  permissions: demoPermissions,
}
