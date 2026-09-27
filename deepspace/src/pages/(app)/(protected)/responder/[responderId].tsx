/**
 * Simulated responder screen. Assignment and status changes arrive through
 * the same record subscription the command-center dashboard uses.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutations, useQuery } from 'deepspace'
import { Button, useToast } from '@/components/ui'
import { progressPlan, type ProgressStep } from '../../../../domain/assignment'
import type { Assignment, Incident, Responder } from '../../../../domain/demo-data'
import { formatKm, haversineKm } from '../../../../domain/routing'
import { priorityLabel } from '../../../../domain/priority'

const NEXT_STEP: Partial<Record<Assignment['status'], { step: ProgressStep; label: string; testId: string }>> = {
  assigned: { step: 'accept', label: 'ACCEPT', testId: 'accept-assignment' },
  accepted: { step: 'en_route', label: 'EN ROUTE', testId: 'en-route' },
  responding: { step: 'on_scene', label: 'ON SCENE', testId: 'on-scene' },
  on_scene: { step: 'resolve', label: 'RESOLVE', testId: 'resolve-assignment' },
}

export default function ResponderPage() {
  const { responderId = '' } = useParams()
  const responders = useQuery<Responder>('responders', { where: { responderId } })
  const assignments = useQuery<Assignment>('assignments', { where: { responderId } })
  const incidents = useQuery<Incident>('incidents', { where: { assignedResponderId: responderId } })
  const assignmentWrites = useMutations<Assignment>('assignments')
  const incidentWrites = useMutations<Incident>('incidents')
  const responderWrites = useMutations<Responder>('responders')
  const { error: toastError } = useToast()
  const [pending, setPending] = useState(false)

  const responder = responders.records[0] ?? null
  const assignment =
    assignments.records.find((record) => record.data.status !== 'resolved') ??
    null
  const incident =
    incidents.records.find((record) => record.data.incidentId === assignment?.data.incidentId) ??
    incidents.records.find((record) => record.data.status !== 'resolved') ??
    null
  const ready = assignmentWrites.ready && incidentWrites.ready && responderWrites.ready
  const queriesReady = responders.status === 'ready' && assignments.status === 'ready' && incidents.status === 'ready'
  const next = assignment ? NEXT_STEP[assignment.data.status] : undefined
  const distance =
    responder && incident ? formatKm(haversineKm(incident.data, responder.data)) : null

  async function advance(step: ProgressStep) {
    if (!assignment || !incident || !responder) return
    const plan = progressPlan(step, new Date().toISOString())
    if (assignment.data.status !== plan.expectedStatus) {
      toastError('Status is out of date', 'Wait for the latest update, then try again.')
      return
    }
    setPending(true)
    try {
      await assignmentWrites.putConfirmed(assignment.recordId, plan.assignment)
      await incidentWrites.putConfirmed(incident.recordId, plan.incident)
      if (plan.responder) await responderWrites.putConfirmed(responder.recordId, plan.responder)
    } catch (err) {
      toastError('Could not update status', err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-full w-full max-w-md flex-col px-4 py-6 text-foreground">
      <p className="text-sm font-semibold">NotifYC</p>
      <h1 className="mt-4 text-xs tracking-wide text-muted-foreground">SIMULATED RESPONDER</h1>
      <p className="mt-1 text-3xl font-semibold" data-testid="responder-id">{responderId}</p>
      <p className="mt-2 text-sm text-muted-foreground">Demo environment — simulated responder</p>
      <p className="mt-6 text-sm text-muted-foreground">Current Status</p>
      <p className="text-xl font-semibold" data-testid="responder-current-status">
        {responder ? responder.data.status : queriesReady ? 'not found' : '…'}
      </p>
      <p className="mt-1 text-xs text-muted-foreground" data-testid="responder-realtime">
        {queriesReady ? 'Realtime: connected' : 'Realtime: connecting'}
      </p>

      {assignment && incident && (
        <section className="mt-6 rounded-lg border border-border p-4" data-testid="active-assignment">
          <h2 className="text-lg font-semibold">POSSIBLE COLLISION</h2>
          {incident.data.detectionMode === 'demo_fallback' && (
            <p className="mt-1 text-xs font-semibold">TEST / DEMO EVENT</p>
          )}
          <dl className="mt-4 space-y-2 text-sm">
            <div>
              <dt className="text-muted-foreground">Location</dt>
              <dd>{incident.data.locationName}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Camera</dt>
              <dd>{incident.data.cameraId}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Operational priority</dt>
              <dd>{priorityLabel(incident.data.priority)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Time</dt>
              <dd>{incident.data.detectedAt}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Visual evidence</dt>
              <dd>
                {incident.data.evidenceStatus ?? 'unavailable'}
                {' · '}
                {incident.data.evidenceWindowStart || '—'} – {incident.data.evidenceWindowEnd || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Tracks</dt>
              <dd>{incident.data.participantTrackIds.length > 0 ? incident.data.participantTrackIds.join(', ') : 'none recorded'}</dd>
            </div>
            {incident.data.observations[0]?.summary && (
              <div>
                <dt className="text-muted-foreground">Observable evidence</dt>
                <dd>{incident.data.observations[0].summary}</dd>
              </div>
            )}
            {(incident.data.priorityReasons ?? []).length > 0 && (
              <div>
                <dt className="text-muted-foreground">Why this priority</dt>
                <dd>{incident.data.priorityReasons?.join('; ')}</dd>
              </div>
            )}
            {distance && (
              <div>
                <dt className="text-muted-foreground">Distance</dt>
                <dd data-testid="responder-distance">{distance}</dd>
              </div>
            )}
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd data-testid="responder-incident-status">{incident.data.status}</dd>
            </div>
          </dl>
          {next && (
            <Button
              className="mt-6 h-12 w-full"
              data-testid={next.testId}
              disabled={!ready || pending}
              onClick={() => void advance(next.step)}
            >
              {next.label}
            </Button>
          )}
        </section>
      )}

      {queriesReady && !assignment && (
        <p className="mt-6 text-sm" data-testid="no-active-assignment">No active assignment</p>
      )}

      <Link className="mt-8 text-sm underline" to="/home">
        Back to dashboard
      </Link>
    </div>
  )
}
