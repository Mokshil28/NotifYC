import { Link } from 'react-router-dom'
import { useQuery } from 'deepspace'
import { activeIncidents, type Incident } from '../../domain/demo-data'
import { compareOperational, priorityLabel } from '../../domain/priority'

export default function IncidentsPage() {
  const incidents = useQuery<Incident>('incidents')
  const open = activeIncidents(incidents.records)
    .map((record) => record.data)
    .sort(compareOperational)

  return (
    <div className="mx-auto max-w-3xl px-6 py-8 text-foreground">
      <h1 className="text-2xl font-semibold">Active incidents</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Operational response priority from observable CV evidence. Simulated responders only.
      </p>
      {incidents.status !== 'ready' && <p className="mt-4 text-sm">Loading incidents…</p>}
      {incidents.status === 'ready' && open.length === 0 && (
        <p className="mt-4 text-sm" data-testid="incident-queue-empty">No surfaced incidents</p>
      )}
      <ol className="mt-6 space-y-3" data-testid="incident-queue">
        {open.map((incident) => (
          <li key={incident.incidentId}>
            <Link
              className="block rounded-lg border border-border p-4"
              data-testid={`queue-${incident.incidentId}`}
              to={`/incidents/${incident.incidentId}`}
            >
              <p className="font-semibold">{priorityLabel(incident.priority)}</p>
              <p>{incident.cameraId} · Possible collision</p>
              <p className="text-sm text-muted-foreground">{incident.locationName}</p>
              <p className="text-sm">Status: {incident.status === 'open' ? 'Awaiting available responder' : incident.status}</p>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  )
}
