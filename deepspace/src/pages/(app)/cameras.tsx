import { Link } from 'react-router-dom'
import { useQuery } from 'deepspace'
import { activeIncidents, type Camera, type Incident } from '../../domain/demo-data'

export default function CamerasPage() {
  const cameras = useQuery<Camera>('cameras', { orderBy: 'cameraId', orderDir: 'asc' })
  const incidents = useQuery<Incident>('incidents')
  const open = activeIncidents(incidents.records)

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 text-foreground">
      <h1 className="text-2xl font-semibold">Camera network</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Demo camera network — ten simulated views. Each tile opens that camera’s existing demo clip.
      </p>
      {cameras.status !== 'ready' && <p className="mt-4 text-sm">Loading cameras…</p>}
      <ul className="mt-6 grid gap-3 sm:grid-cols-2" data-testid="camera-network">
        {cameras.records.map((camera) => {
          const surfaced = open.some((incident) => incident.data.cameraId === camera.data.cameraId)
          return (
            <li key={camera.recordId}>
              <Link
                className="block rounded-lg border border-border p-4"
                data-testid={`camera-card-${camera.data.cameraId}`}
                to={`/cameras/${camera.data.cameraId}`}
              >
                <p className="font-semibold">{camera.data.cameraId}</p>
                <p className="text-sm">{camera.data.locationName}</p>
                <p className="mt-2 text-sm">Status: {camera.data.status}</p>
                <p className="text-sm" data-testid={`camera-monitoring-${camera.data.cameraId}`}>
                  Monitoring: {surfaced ? 'Possible collision surfaced' : 'Active'}
                </p>
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
