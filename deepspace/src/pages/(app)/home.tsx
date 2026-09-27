/**
 * Temporary test dashboard. Counts and rows come from live record queries.
 * A responder status change is a confirmed mutation; every open client
 * receives it through the records subscription.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAuthToken, useAuthProfileReady, useMutations, useQuery, type RecordData } from 'deepspace'
import { Button, useToast } from '@/components/ui'
import { APP_NAME } from '../../constants'
import { TEST_INCIDENT_ID } from '../../domain/assignment'
import { callAppAction } from '../../domain/call-action'
import {
  activeIncidents,
  countAvailableResponders,
  nextResponderStatus,
  type Camera,
  type Incident,
  type Responder,
  type ResponderStatus,
} from '../../domain/demo-data'
import { formatKm, haversineKm } from '../../domain/routing'

type SeedState = 'idle' | 'seeding' | 'ready' | 'error'

export default function HomePage() {
  const { isLoaded, isSignedIn } = useAuthProfileReady({ requireUser: true })
  const cameras = useQuery<Camera>('cameras', { orderBy: 'cameraId', orderDir: 'asc' })
  const incidents = useQuery<Incident>('incidents', { orderBy: 'detectedAt', orderDir: 'desc' })
  const responders = useQuery<Responder>('responders', { orderBy: 'responderId', orderDir: 'asc' })
  const { putConfirmed, ready } = useMutations<Responder>('responders')
  const { error: toastError } = useToast()
  const [seedState, setSeedState] = useState<SeedState>('idle')
  const [seedError, setSeedError] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionPending, setActionPending] = useState(false)

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    let cancelled = false
    setSeedState('seeding')
    setSeedError(null)

    void (async () => {
      try {
        const token = await getAuthToken()
        if (!token) {
          if (!cancelled) setSeedState('error')
          if (!cancelled) setSeedError('Sign in again to load the demo network.')
          return
        }
        const res = await fetch('/api/actions/seedDemoData', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({}),
        })
        const body = (await res.json()) as { success?: boolean; error?: string }
        if (cancelled) return
        if (!res.ok || body.success === false) {
          setSeedState('error')
          setSeedError(body.error ?? `Could not seed demo data (${res.status})`)
          return
        }
        setSeedState('ready')
      } catch (err) {
        if (cancelled) return
        setSeedState('error')
        setSeedError(err instanceof Error ? err.message : 'Could not seed demo data')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [isLoaded, isSignedIn])

  const queriesReady =
    cameras.status === 'ready' && incidents.status === 'ready' && responders.status === 'ready'
  const queryError = cameras.error ?? incidents.error ?? responders.error
  const openIncidents = activeIncidents(incidents.records)
  const availableCount = countAvailableResponders(responders.records)
  const highPriorityCount = openIncidents.filter((record) => record.data.priority === 'high').length
  const testIncident = incidents.records.find((record) => record.data.incidentId === TEST_INCIDENT_ID) ?? null
  const assignedResponder = responders.records.find(
    (record) => record.data.responderId === testIncident?.data.assignedResponderId,
  )
  const assignmentDistance =
    testIncident && assignedResponder && testIncident.data.assignedResponderId
      ? formatKm(haversineKm(testIncident.data, assignedResponder.data))
      : null

  async function runDemoAction(name: string, params: Record<string, unknown> = {}) {
    setActionPending(true)
    setActionError(null)
    try {
      const result = await callAppAction(name, params)
      if (!result.success) setActionError(result.error)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setActionPending(false)
    }
  }

  async function toggleResponder(record: RecordData<Responder>) {
    const current = record.data.status
    if (current !== 'available' && current !== 'unavailable') return
    const next: ResponderStatus = nextResponderStatus(current)
    setPendingId(record.recordId)
    try {
      await putConfirmed(record.recordId, {
        status: next,
        updatedAt: new Date().toISOString(),
      })
    } catch (err) {
      toastError('Could not update responder', err instanceof Error ? err.message : String(err))
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 text-foreground">
      <h1 className="text-2xl font-semibold">{APP_NAME}</h1>
      <p className="mt-1 text-base">Traffic Incident Awareness Prototype</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Demo environment — simulated camera network and responders
      </p>
      <p className="mt-2 text-xs text-muted-foreground" data-testid="realtime-status">
        {queriesReady ? 'Realtime: connected' : 'Realtime: connecting'}
      </p>

      {!isSignedIn && isLoaded && (
        <p className="mt-4 text-sm">Sign in to load the simulated cameras and responders.</p>
      )}
      {seedState === 'seeding' && <p className="mt-4 text-sm">Loading demo data…</p>}
      {seedError && <p className="mt-4 text-sm text-destructive">{seedError}</p>}
      {queryError && <p className="mt-4 text-sm text-destructive">{queryError}</p>}

      <section className="mt-6 grid gap-3 sm:grid-cols-4">
        <SummaryCard label="Cameras" value={queriesReady ? String(cameras.records.length) : '…'} testId="camera-count" />
        <SummaryCard
          label="Active Incidents"
          value={queriesReady ? String(openIncidents.length) : '…'}
          testId="active-incident-count"
        />
        <SummaryCard
          label="Available Responders"
          value={queriesReady ? String(availableCount) : '…'}
          testId="available-responder-count"
        />
        <SummaryCard
          label="High Priority Incidents"
          value={queriesReady ? String(highPriorityCount) : '…'}
          testId="high-priority-count"
        />
      </section>
      <div className="mt-4 flex flex-wrap gap-3 text-sm">
        <Link className="underline" to="/cameras" data-testid="open-camera-network">Camera network</Link>
        <Link className="underline" to="/incidents" data-testid="open-incident-queue">Active incidents</Link>
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-wide">CAMERAS</h2>
        <table className="mt-2 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-2 pr-4 font-medium">ID</th>
              <th className="py-2 pr-4 font-medium">Location</th>
              <th className="py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {cameras.records.map((camera) => (
              <tr key={camera.recordId} data-testid={`camera-row-${camera.data.cameraId}`} className="border-b border-border">
                <td className="py-2 pr-4">{camera.data.cameraId}</td>
                <td className="py-2 pr-4">{camera.data.locationName}</td>
                <td className="py-2">{camera.data.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-wide">RESPONDERS</h2>
        <table className="mt-2 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-2 pr-4 font-medium">ID</th>
              <th className="py-2 pr-4 font-medium">Type</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 font-medium">Test</th>
            </tr>
          </thead>
          <tbody>
            {responders.records.map((responder) => (
              <tr key={responder.recordId} className="border-b border-border">
                <td className="py-2 pr-4">{responder.data.responderId}</td>
                <td className="py-2 pr-4">{responder.data.type}</td>
                <td className="py-2 pr-4" data-testid={`responder-status-${responder.data.responderId}`}>
                  {responder.data.status}
                </td>
                <td className="py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    {(responder.data.status === 'available' || responder.data.status === 'unavailable') && (
                      <Button
                        size="sm"
                        variant="outline"
                        data-testid={`toggle-status-${responder.data.responderId}`}
                        disabled={!ready || !isSignedIn || pendingId === responder.recordId}
                        onClick={() => void toggleResponder(responder)}
                      >
                        {responder.data.status === 'available' ? 'Set unavailable' : 'Set available'}
                      </Button>
                    )}
                    <Link className="text-sm underline" to={`/responder/${responder.data.responderId}`}>
                      Open
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-wide">INCIDENTS</h2>
        {import.meta.env.DEV && isSignedIn && !testIncident && (
          <Button
            className="mt-3"
            data-testid="create-test-incident"
            disabled={actionPending}
            onClick={() => void runDemoAction('createDemoIncident')}
          >
            Create Test Incident
          </Button>
        )}
        {actionError && <p className="mt-3 text-sm text-destructive">{actionError}</p>}
        {queriesReady && !testIncident && openIncidents.length === 0 && (
          <p className="mt-2 text-sm" data-testid="incidents-empty">No active incidents</p>
        )}
        {openIncidents
          .filter((record) => record.data.incidentId !== TEST_INCIDENT_ID)
          .map((record) => (
            <article
              key={record.recordId}
              className="mt-3 max-w-md rounded-lg border border-border p-4 text-sm"
              data-testid={`incident-${record.data.incidentId}`}
            >
              <IncidentFacts incident={record.data} />
            </article>
          ))}
        {testIncident && (
          <div className="mt-3 max-w-md rounded-lg border border-border p-4 text-sm" data-testid="test-incident">
            <p className="font-semibold" data-testid="test-incident-label">TEST / DEMO INCIDENT</p>
            <p data-testid="test-incident-camera">{testIncident.data.cameraId}</p>
            <IncidentFacts incident={testIncident.data} />
            <p>Status</p>
            <p data-testid="test-incident-status">{testIncident.data.status}</p>
            {testIncident.data.assignedResponderId && (
              <>
                <p className="mt-2" data-testid="test-incident-assignee">
                  Assigned: {testIncident.data.assignedResponderId}
                </p>
                {assignmentDistance && <p data-testid="test-incident-distance">Distance: {assignmentDistance}</p>}
              </>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {testIncident.data.status === 'open' && (
                <Button
                  data-testid="assign-nearest"
                  disabled={actionPending}
                  onClick={() => void runDemoAction('assignResponder', { incidentId: testIncident.recordId })}
                >
                  Assign Nearest Available Responder
                </Button>
              )}
              {import.meta.env.DEV && (
                <Button
                  variant="outline"
                  data-testid="reset-test-incident"
                  disabled={actionPending}
                  onClick={() => void runDemoAction('resetDemoIncident')}
                >
                  Reset test incident
                </Button>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

function IncidentFacts({ incident }: { incident: Incident }) {
  const tracks = incident.participantTrackIds.length > 0 ? incident.participantTrackIds.join(', ') : 'none recorded'
  const note = incident.observations[0]?.summary
  return (
    <>
      <p className="font-semibold">POSSIBLE COLLISION</p>
      {incident.detectionMode === 'demo_fallback' && <p className="text-xs font-semibold">TEST / DEMO EVENT</p>}
      <p>{incident.cameraId}</p>
      <p>{incident.locationName}</p>
      <p>Event time: {incident.detectedAt}</p>
      <p>Priority: {incident.priority}</p>
      <p>Status: {incident.status}</p>
      <p className="mt-2 font-medium">Visual Evidence</p>
      <p>Evidence status: {incident.evidenceStatus ?? 'unavailable'}</p>
      <p>Evidence window: {incident.evidenceWindowStart || '—'} – {incident.evidenceWindowEnd || '—'}</p>
      <p>Detection: {incident.detectionMode === 'computer-vision' ? 'CV pipeline' : incident.detectionMode}</p>
      <p>Tracks: {tracks}</p>
      {note && <p>Observable evidence: {note}</p>}
      {incident.assignedResponderId && <p>Assigned responder: {incident.assignedResponderId}</p>}
    </>
  )
}

function SummaryCard({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="rounded-lg border border-border px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold" data-testid={testId}>{value}</p>
    </div>
  )
}
