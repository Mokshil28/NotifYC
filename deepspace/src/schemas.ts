/**
 * Collection Schemas
 *
 * All collections with columns and RBAC permissions.
 * Single source of truth — imported by both worker and frontend.
 *
 * Add schemas by creating a file in src/schemas/ and importing it here.
 */

import type { CollectionSchema } from 'deepspace/schema'
import { usersSchema } from './schemas/users-schema'
import { settingsSchema } from './schemas/admin-schema'
import { camerasSchema } from './schemas/cameras-schema'
import { incidentsSchema } from './schemas/incidents-schema'
import { respondersSchema } from './schemas/responders-schema'
import { assignmentsSchema } from './schemas/assignments-schema'

export const schemas: CollectionSchema[] = [
  usersSchema,
  settingsSchema,
  camerasSchema,
  incidentsSchema,
  respondersSchema,
  assignmentsSchema,
]
