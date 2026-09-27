import { Link, useParams } from 'react-router-dom'
import { useQuery } from 'deepspace'
import { DemoClip } from '../../../components/DemoClip'
import { activeIncidents, type Camera, type Incident } from '../../../domain/demo-data'
import { priorityLabel } from '../../../domain/priority'

export default function CameraDetailPage() {
  const { cameraId = '' } = useParams()
  const cameras = useQuery<Camera>('cameras', { where: { cameraId } })
  const incidents = useQuery<Incident>('incidents', { where: { cameraId } })
  const camera = cameras.records[0]?.data
  const surfaced = activeIncidents(incidents.records)[0]?.data

  return (
    <div className="mx-auto max-w-4xl px-6 py-8 text-foreground">
      <Link className="text-sm underline" to="/cameras">Camera network</Link>
      <h1 className="mt-3 text-2xl font-semibold">{cameraId}</h1>
      <p className="text-sm text-muted-foreground">{camera?.locationName ?? 'Simulated location'}</p>
      <p className="mt-2 text-xs tracking-wide text-muted-foreground">DEMO FEED</p>
      <div className="mt-3">
        <DemoClip
          cameraId={cameraId}
          endSeconds={surfaced ? Number(surfaced.evidenceWindowEnd) : undefined}
          startSeconds={surfaced ? Number(surfaced.evidenceWindowStart) : undefined}
        />
      </div>
      <p className="mt-4 text-sm">Monitoring: {camera?.status === 'active' ? 'Active' : camera?.status ?? '…'}</p>
      <p className="mt-2 text-sm">CV pipeline: vehicle detection, tracking, motion analysis, incident detection.</p>
      {!surfaced && cameras.status === 'ready' && incidents.status === 'ready' && (
        <section className="mt-4 rounded-lg border border-border p-4 text-sm" data-testid="no-incident">
          <p className="font-semibold">No incident surfaced</p>
          <p>Continue monitoring. A responder is notified only after the CV system surfaces a possible collision.</p>
        </section>
      )}
      {surfaced && (
        <section className="mt-4 rounded-lg border border-border p-4 text-sm" data-testid="surfaced-incident">
          <p className="font-semibold">Possible collision surfaced</p>
          <p>Event time: {surfaced.detectedAt}</p>
          <p>Operational priority: {priorityLabel(surfaced.priority)}</p>
          <p>Tracks: {surfaced.participantTrackIds.join(', ') || 'none recorded'}</p>
          <p>Evidence window: {surfaced.evidenceWindowStart || '—'} – {surfaced.evidenceWindowEnd || '—'}</p>
          <Link className="mt-2 inline-block underline" to={`/incidents/${surfaced.incidentId}`}>
            Open incident
          </Link>
        </section>
      )}
    </div>
  )
}
