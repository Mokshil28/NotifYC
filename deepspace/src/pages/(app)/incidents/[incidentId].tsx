import { Link, useParams } from 'react-router-dom'
import { useQuery } from 'deepspace'
import { DemoClip } from '../../../components/DemoClip'
import { type Incident, type Responder } from '../../../domain/demo-data'
import { formatKm, haversineKm } from '../../../domain/routing'
import { priorityLabel } from '../../../domain/priority'

export default function IncidentDetailPage() {
  const { incidentId = '' } = useParams()
  const incidents = useQuery<Incident>('incidents', { where: { incidentId } })
  const responders = useQuery<Responder>('responders')
  const incident = incidents.records[0]?.data
  const responder = responders.records.find((record) => record.data.responderId === incident?.assignedResponderId)
  const distance = incident && responder ? formatKm(haversineKm(incident, responder.data)) : null
  const start = incident?.evidenceWindowStart ? Number(incident.evidenceWindowStart) : undefined
  const end = incident?.evidenceWindowEnd ? Number(incident.evidenceWindowEnd) : undefined
  const reasons = incident?.priorityReasons ?? []

  return (
    <div className="mx-auto max-w-4xl px-6 py-8 text-foreground">
      <Link className="text-sm underline" to="/incidents">Active incidents</Link>
      {!incident && incidents.status === 'ready' && <p className="mt-4 text-sm">Incident not found.</p>}
      {incident && (
        <>
          <h1 className="mt-3 text-2xl font-semibold">Possible collision</h1>
          {incident.detectionMode === 'demo_fallback' && <p className="text-xs font-semibold">TEST / DEMO EVENT</p>}
          <p className="mt-2 text-sm">{incident.cameraId} · {incident.locationName}</p>
          <p className="text-sm">Event time: {incident.detectedAt}</p>
          <p className="text-sm" data-testid="incident-priority">Operational priority: {priorityLabel(incident.priority)}</p>
          <p className="text-sm">Status: {incident.status === 'open' ? 'Awaiting available responder' : incident.status}</p>

          <h2 className="mt-6 text-sm font-semibold tracking-wide">VISUAL EVIDENCE</h2>
          <p className="mt-1 text-sm">Evidence status: {incident.evidenceStatus ?? 'unavailable'}</p>
          {incident.cameraId && (
            <div className="mt-3">
              <DemoClip
                cameraId={incident.cameraId}
                endSeconds={Number.isFinite(end) ? end : undefined}
                startSeconds={Number.isFinite(start) ? start : undefined}
              />
            </div>
          )}
          <p className="mt-2 text-sm">Detection: {incident.detectionMode === 'computer-vision' ? 'CV pipeline' : incident.detectionMode}</p>
          <p className="text-sm">Tracks: {incident.participantTrackIds.join(', ') || 'none recorded'}</p>
          {incident.observations[0]?.summary && <p className="mt-2 text-sm">{incident.observations[0].summary}</p>}

          <h2 className="mt-6 text-sm font-semibold tracking-wide">WHY THIS PRIORITY?</h2>
          <ul className="mt-2 list-disc pl-5 text-sm" data-testid="priority-reasons">
            {reasons.length === 0 && <li>No extra observable reasons were stored.</li>}
            {reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>

          <h2 className="mt-6 text-sm font-semibold tracking-wide">SIMULATED RESPONDER</h2>
          {incident.assignedResponderId ? (
            <p className="mt-2 text-sm">
              Assigned: {incident.assignedResponderId}
              {distance ? ` · ${distance}` : ''}
              {responder ? ` · ${responder.data.status}` : ''}
            </p>
          ) : (
            <p className="mt-2 text-sm" data-testid="awaiting-responder">Awaiting available responder</p>
          )}
        </>
      )}
    </div>
  )
}
