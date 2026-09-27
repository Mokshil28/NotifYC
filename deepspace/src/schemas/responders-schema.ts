import type { CollectionSchema } from 'deepspace/schema'
import { demoPermissions } from './demo-permissions'

export const respondersSchema: CollectionSchema = {
  name: 'responders',
  columns: [
    { name: 'responderId', storage: 'text', interpretation: 'plain', required: true, immutable: true },
    { name: 'name', storage: 'text', interpretation: 'plain', required: true },
    {
      name: 'type',
      storage: 'text',
      interpretation: { kind: 'select', options: ['mobile', 'support'] },
      required: true,
    },
    {
      name: 'status',
      storage: 'text',
      interpretation: {
        kind: 'select',
        options: ['available', 'unavailable', 'assigned', 'responding', 'on_scene'],
      },
      required: true,
    },
    { name: 'latitude', storage: 'number', interpretation: 'plain', required: true },
    { name: 'longitude', storage: 'number', interpretation: 'plain', required: true },
    {
      name: 'simulation',
      storage: 'number',
      interpretation: { kind: 'boolean' },
      required: true,
    },
    {
      name: 'updatedAt',
      storage: 'text',
      interpretation: { kind: 'datetime' },
      required: true,
    },
  ],
  uniqueOn: ['responderId'],
  permissions: demoPermissions,
}
