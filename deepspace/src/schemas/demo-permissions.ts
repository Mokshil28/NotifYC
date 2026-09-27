import type { RolePermissions } from 'deepspace/schema'

/**
 * Hackathon demo collections. Signed-in members can read and update the
 * shared simulated network. The app owner remains admin. Anonymous callers
 * have no rule, so they receive nothing.
 */
export const demoPermissions: Record<string, RolePermissions> = {
  viewer: { read: true, create: false, update: false, delete: false },
  member: { read: true, create: true, update: true, delete: false },
  admin: { read: true, create: true, update: true, delete: true },
}
