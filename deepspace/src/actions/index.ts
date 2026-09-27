import type { ActionHandler } from 'deepspace/worker'
import { assignNearestResponder, clearTestIncident, createTestIncident } from '../domain/assignment'
import { ensureDemoRecords } from '../domain/demo-data'
import type { Env } from '../../worker'

/**
 * Insert the simulated camera network and responders when their known ids are
 * missing. Re-running does not overwrite an existing row.
 */
export const seedDemoData: ActionHandler<Env> = async ({ tools }) => {
  return ensureDemoRecords(tools)
}

/**
 * Choose the nearest available simulated responder and write the assignment,
 * the incident, and that responder. There is no multi-record transaction in
 * this SDK, so the helper orders the writes and rolls back earlier writes
 * when a later one is refused.
 */
export const assignResponder: ActionHandler<Env> = async ({ params, tools }) => {
  const incidentId = params.incidentId
  if (typeof incidentId !== 'string' || incidentId.length === 0) {
    return { success: false, error: 'incidentId is required.' }
  }
  return assignNearestResponder(tools, incidentId)
}

function demoControls(env: Env): { success: false; error: string } | null {
  if (env.ALLOW_DEBUG_ROUTES !== 'true') {
    return { success: false, error: 'Test incidents are only available in the local demo.' }
  }
  return null
}

/** Development-only. Creates one labeled demo incident. It is not a CV detection. */
export const createDemoIncident: ActionHandler<Env> = async ({ tools, env }) => {
  const refused = demoControls(env)
  if (refused) return refused
  return createTestIncident(tools)
}

/** Development-only. Deletes the demo incident, its assignment, and frees the unit. */
export const resetDemoIncident: ActionHandler<Env> = async ({ tools, env }) => {
  const refused = demoControls(env)
  if (refused) return refused
  return clearTestIncident(tools)
}

export const actions: Record<string, ActionHandler<Env>> = {
  seedDemoData,
  assignResponder,
  createDemoIncident,
  resetDemoIncident,
}
