import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutations, useQuery, useAuthProfileReady, type RecordData } from "deepspace";
import { callAppAction } from "@notifyc/domain/call-action";
import { progressPlan, type ProgressStep } from "@notifyc/domain/assignment";
import {
  activeIncidents,
  countAvailableResponders,
  type Assignment,
  type Camera,
  type Incident,
  type Responder,
} from "@notifyc/domain/demo-data";
import { compareOperational, priorityLabel } from "@notifyc/domain/priority";
import { SignInButton } from "./live-shell";

type Page = "home" | "map" | "channel";
type IconName =
  | "arrow"
  | "bell"
  | "camera"
  | "car"
  | "chevron"
  | "clock"
  | "location"
  | "phone"
  | "play"
  | "shield"
  | "spark"
  | "users";

type ViewCamera = {
  id: string
  name: string
  borough: string
  status: "Incident" | "Monitoring" | "Offline"
  detail: string
  risk: "critical" | "clear" | "offline"
  latitude: number
  longitude: number
}

const STEPS: Partial<Record<Assignment["status"], { step: ProgressStep; label: string }>> = {
  assigned: { step: "accept", label: "ACCEPT" },
  accepted: { step: "en_route", label: "EN ROUTE" },
  responding: { step: "on_scene", label: "ON SCENE" },
  on_scene: { step: "resolve", label: "RESOLVE" },
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    camera: <><path d="M3 7h4l2-3h6l2 3h4v12H3z" /><circle cx="12" cy="13" r="3.5" /></>,
    car: <><path d="m5 11 2-5h10l2 5v7H5z" /><path d="M7 18v2m10-2v2M5 13h14" /><circle cx="8" cy="15" r="1" /><circle cx="16" cy="15" r="1" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    location: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></>,
    phone: <path d="M8 3H5a2 2 0 0 0-2 2c0 8.8 7.2 16 16 16a2 2 0 0 0 2-2v-3l-4-1-1.5 2a13 13 0 0 1-8.5-8.5L9 7z" />,
    play: <path d="m9 7 8 5-8 5Z" />,
    shield: <path d="M12 3 5 6v5c0 4.6 3 8 7 10 4-2 7-5.4 7-10V6zM9 12l2 2 4-4" />,
    spark: <><path d="m12 3 1.3 4.2L17 9l-3.7 1.8L12 15l-1.3-4.2L7 9l3.7-1.8Z" /><path d="m19 15 .7 2.2L22 18l-2.3.8L19 21l-.7-2.2L16 18l2.3-.8Z" /></>,
    users: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-4 2-6 6-6s6 2 6 6" /><circle cx="17" cy="9" r="2" /><path d="M16 15c3 0 5 2 5 5" /></>,
  };
  return <svg aria-hidden="true" className="icon" height={size} viewBox="0 0 24 24" width={size}>{paths[name]}</svg>;
}

function Button({ children, className = "", onClick, disabled }: { children: ReactNode; className?: string; onClick?: () => void; disabled?: boolean }) {
  return <button className={`button ${className}`} disabled={disabled} onClick={onClick} type="button">{children}</button>;
}

function Brand() {
  return <div className="brand"><div className="brand-mark"><span /><span /></div><span>nearmiss</span></div>;
}

function pinPosition(latitude: number, longitude: number) {
  const latMin = 40.7;
  const latMax = 40.78;
  const lngMin = -74.01;
  const lngMax = -73.97;
  const x = ((longitude - lngMin) / (lngMax - lngMin)) * 68 + 14;
  const y = ((latMax - latitude) / (latMax - latMin)) * 68 + 12;
  return { left: `${Math.min(86, Math.max(8, x))}%`, top: `${Math.min(82, Math.max(8, y))}%` };
}

function Header({ page, setPage, monitoring, signedIn }: { page: Page; setPage: (page: Page) => void; monitoring: number; signedIn: boolean }) {
  return (
    <header className="site-header">
      <button aria-label="Go to home" className="brand-button" onClick={() => setPage("home")}><Brand /></button>
      <nav aria-label="Primary navigation">
        <button className={page === "home" ? "nav-item active" : "nav-item"} onClick={() => setPage("home")}>Overview</button>
        <button className={page === "map" ? "nav-item active" : "nav-item"} onClick={() => setPage("map")}>Live map</button>
        <button className={page === "channel" ? "nav-item active" : "nav-item"} onClick={() => setPage("channel")}>Active incident</button>
      </nav>
      <div className="header-actions">
        <span className="city-pill"><span className="status-dot" /> {monitoring} cameras monitoring</span>
        {!signedIn && <SignInButton />}
        <Button className="button-compact button-light" onClick={() => setPage("map")}>Open operations <Icon name="arrow" size={16} /></Button>
      </div>
    </header>
  );
}

function CityMap({
  cameras,
  alert,
  activeId,
  onHover,
  onSelect,
  preview = false,
}: {
  cameras: ViewCamera[]
  alert: Incident | null
  activeId?: string
  onHover?: (id?: string) => void
  onSelect?: (camera: ViewCamera) => void
  preview?: boolean
}) {
  return (
    <div className={preview ? "city-map preview-map" : "city-map"} aria-label="Demo camera network map">
      <div className="map-grid" />
      <div className="water-shape water-east">EAST RIVER</div>
      <div className="water-shape water-hudson">HUDSON</div>
      <div className="map-borough borough-manhattan">MANHATTAN</div>
      <div className="map-borough borough-brooklyn">BROOKLYN</div>
      <div className="map-borough borough-queens">QUEENS</div>
      <div className="map-borough borough-bronx">BRONX</div>
      <div className="map-borough borough-staten">STATEN ISLAND</div>
      <div className="map-road map-road-a" /><div className="map-road map-road-b" /><div className="map-road map-road-c" /><div className="map-road map-road-d" />
      {cameras.map((camera) => (
        <button
          aria-label={`Open ${camera.name} camera`}
          className={`camera-pin ${camera.risk} ${activeId === camera.id ? "pin-active" : ""}`}
          data-testid={`map-pin-${camera.id}`}
          key={camera.id}
          onClick={() => onSelect?.(camera)}
          onMouseEnter={() => onHover?.(camera.id)}
          onMouseLeave={() => onHover?.()}
          style={pinPosition(camera.latitude, camera.longitude)}
        >
          <span className="pin-ripple" /><span className="pin-core"><Icon name="camera" size={14} /></span>
          <span className="pin-label"><b>{camera.id}</b>{camera.name}</span>
        </button>
      ))}
      <div className="map-controls"><button type="button">+</button><button type="button">−</button></div>
      <div className="map-status"><span><i className="map-dot live" /> Monitoring</span><span><i className="map-dot incident" /> Possible collision</span><span><i className="map-dot unavailable" /> Inactive</span></div>
      {preview && alert && (
        <div className="map-alert-card">
          <div><span className="alert-pulse" /><span>POSSIBLE COLLISION SURFACED</span></div>
          <strong>{alert.locationName}</strong>
          <p>{alert.cameraId} · {priorityLabel(alert.priority)}</p>
        </div>
      )}
      {preview && !alert && (
        <div className="map-alert-card">
          <div><span>DEMO CAMERA NETWORK</span></div>
          <strong>No incident surfaced</strong>
          <p>Monitoring continues. No detection is shown until the working system surfaces one.</p>
        </div>
      )}
    </div>
  );
}

function HomePage({
  setPage,
  cameras,
  active,
  available,
  highPriority,
  alert,
}: {
  setPage: (page: Page) => void
  cameras: ViewCamera[]
  active: number
  available: number
  highPriority: number
  alert: Incident | null
}) {
  return (
    <main>
      <section className="hero response-hero">
        <div className="hero-copy">
          <div className="eyebrow hero-eyebrow"><span className="eyebrow-line" /> DEMO CAMERA NETWORK</div>
          <h1>See the impact.<br /><em>Review it faster.</em></h1>
          <p className="hero-lede">NotifYC shows possible collisions the working system has already surfaced, with visual evidence and an operational response priority. Simulated responders only.</p>
          <div className="hero-actions">
            <Button className="button-primary" onClick={() => setPage("map")}>Open live map <Icon name="arrow" /></Button>
            <Button className="button-ghost" onClick={() => setPage("channel")}><span className="play-chip"><Icon name="play" size={14} /></span> View active incident</Button>
          </div>
          <div className="trust-row">
            <span><Icon name="shield" size={16} /> Observable evidence</span>
            <span><Icon name="bell" size={16} /> Simulated responder</span>
          </div>
        </div>
        <div className="hero-map">
          <div className="map-kicker"><span>DEMO / LIVE OPERATIONS</span><span>{cameras.length} CAMERAS</span></div>
          <CityMap alert={alert} cameras={cameras} preview />
        </div>
      </section>
      <section className="impact-section">
        <div className="impact-intro">
          <span className="eyebrow">CURRENT STATE</span>
          <p>Counts come from the working camera, incident, and responder records.</p>
        </div>
        <div className="impact-metrics">
          <div><strong data-testid="camera-count">{cameras.length}</strong><span>cameras</span></div>
          <div><strong data-testid="active-incident-count">{active}</strong><span>active incidents</span></div>
          <div><strong data-testid="available-responder-count">{available}</strong><span>available responders</span></div>
          <div><strong data-testid="high-priority-count">{highPriority}</strong><span>high priority incidents</span></div>
        </div>
      </section>
      <section className="workflow-section">
        <div className="section-heading">
          <span className="eyebrow">FROM REVIEW TO RESPONSE</span>
          <h2>One possible collision. The recorded evidence.</h2>
          <p>The computer-vision system decides whether a possible collision is surfaced. This screen only presents that record, the operational priority, and the simulated responder already assigned.</p>
        </div>
        <div className="workflow-timeline">
          <div className="timeline-rail" />
          <article className="timeline-step step-upload">
            <div className="timeline-marker"><span>01</span><Icon name="car" /></div>
            <div className="timeline-copy"><span className="timeline-time">Surface</span><h3>Possible collision</h3><p>A record appears here only after the existing pipeline surfaces one. An empty network stays empty.</p></div>
          </article>
          <article className="timeline-step step-detect">
            <div className="timeline-marker"><span>02</span><Icon name="spark" /></div>
            <div className="timeline-copy"><span className="timeline-time">Review</span><h3>Observable evidence</h3><p>Track ids, the evidence window, and the operational priority reasons are shown as they were recorded.</p></div>
          </article>
          <article className="timeline-step step-review">
            <div className="timeline-marker"><span>03</span><Icon name="phone" /></div>
            <div className="timeline-copy"><span className="timeline-time">Respond</span><h3>Simulated responder</h3><p>Accept, en route, on scene, and resolve follow the assignment already stored for this incident.</p></div>
          </article>
        </div>
      </section>
    </main>
  );
}

function MapPage({
  cameras,
  incidents,
  setPage,
  openCamera,
  openIncident,
}: {
  cameras: ViewCamera[]
  incidents: Incident[]
  setPage: (page: Page) => void
  openCamera: (camera: ViewCamera) => void
  openIncident: (incident: Incident) => void
}) {
  const [hovered, setHovered] = useState<string>();
  const [filter, setFilter] = useState<"all" | "incidents">("all");
  const visible = filter === "incidents" ? cameras.filter((camera) => camera.risk === "critical") : cameras;
  const lead = incidents[0] ?? null;
  return (
    <main className="operations-page">
      <aside className="channels-panel">
        <div className="channels-head">
          <span className="eyebrow">DEMO CAMERA NETWORK</span>
          <h1>Channels</h1>
          <p><span className="status-dot" /> {cameras.filter((camera) => camera.status !== "Offline").length} monitoring · {incidents.length} active incidents</p>
        </div>
        <div className="channel-filter">
          <button className={filter === "all" ? "selected" : ""} onClick={() => setFilter("all")} type="button">All cameras <span>{cameras.length}</span></button>
          <button className={filter === "incidents" ? "selected" : ""} onClick={() => setFilter("incidents")} type="button">Incidents <span>{incidents.length}</span></button>
        </div>
        <div className="channel-list">
          {filter === "incidents" && incidents.map((incident) => (
            <button className="channel-card critical" data-testid={`incident-${incident.incidentId}`} key={incident.incidentId} onClick={() => openIncident(incident)} type="button">
              <div className="channel-copy">
                <div><b>{incident.cameraId}</b><span className="channel-state critical" /></div>
                <strong>{isDemo(incident) ? "TEST / DEMO EVENT" : "Possible collision"}</strong>
                <p>{incident.locationName}</p>
                <small>{priorityLabel(incident.priority)} · {incident.status}</small>
              </div>
              <Icon name="chevron" size={16} />
            </button>
          ))}
          {filter === "all" && visible.map((camera) => (
            <button
              className={`channel-card ${camera.risk} ${hovered === camera.id ? "hovered" : ""}`}
              data-testid={`camera-row-${camera.id}`}
              key={camera.id}
              onClick={() => openCamera(camera)}
              onMouseEnter={() => setHovered(camera.id)}
              onMouseLeave={() => setHovered(undefined)}
              type="button"
            >
              <div className="channel-copy">
                <div><b>{camera.id}</b><span className={`channel-state ${camera.risk}`} /></div>
                <strong>{camera.name}</strong><p>{camera.borough}</p><small>{camera.detail}</small>
              </div>
              <Icon name="chevron" size={16} />
            </button>
          ))}
          {visible.length === 0 && <p className="channel-copy">No incident surfaced</p>}
        </div>
      </aside>
      <section className="map-workspace">
        <div className="map-toolbar">
          <div><span className="eyebrow">DEMO VISUALIZATION</span><h2>Seeded camera locations</h2></div>
          <div className="map-toolbar-actions"><span>Not a production map</span><button onClick={() => setPage("home")} type="button">Overview</button></div>
        </div>
        <CityMap activeId={hovered} alert={lead} cameras={cameras} onHover={setHovered} onSelect={openCamera} />
        {lead ? (
          <div className="active-alert-bar">
            <span className="alert-pulse" />
            <div><span>{priorityLabel(lead.priority)} · {lead.status}</span><b>Possible collision at {lead.locationName}</b></div>
            <span>{lead.cameraId}</span>
            <Button className="button-alert" onClick={() => openIncident(lead)}>View channel <Icon name="arrow" size={16} /></Button>
          </div>
        ) : (
          <div className="active-alert-bar">
            <span className="alert-pulse" />
            <div><span>MONITORING</span><b>No incident surfaced</b></div>
            <span>Demo camera network</span>
            <Button className="button-alert" onClick={() => setFilter("all")}>View cameras <Icon name="arrow" size={16} /></Button>
          </div>
        )}
      </section>
    </main>
  );
}

function Clip({ cameraId, start, end }: { cameraId: string; start?: string; end?: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const startSeconds = Number(start);
  useEffect(() => {
    const node = video.current;
    if (!node || !Number.isFinite(startSeconds)) return;
    const seek = () => { node.currentTime = startSeconds; };
    node.addEventListener("loadedmetadata", seek);
    return () => node.removeEventListener("loadedmetadata", seek);
  }, [cameraId, startSeconds]);
  return (
    <video
      className="demo-clip"
      controls
      data-testid={`camera-video-${cameraId}`}
      ref={video}
      src={`/api/local/cameras/${cameraId}/video`}
    />
  );
}

function ChannelPage({
  camera,
  incident,
  responder,
  assignment,
  setPage,
  onAdvance,
  onAssign,
  busy,
}: {
  camera: ViewCamera | null
  incident: Incident | null
  responder: Responder | null
  assignment: RecordData<Assignment> | null
  setPage: (page: Page) => void
  onAdvance: (step: ProgressStep) => void
  onAssign: () => void
  busy: boolean
}) {
  const next = assignment ? STEPS[assignment.data.status] : undefined;
  const reasons = incident?.priorityReasons ?? [];
  const notes = incident?.observations.map((item) => item.summary).filter(Boolean) ?? [];
  return (
    <main className="channel-page">
      <div className="channel-topbar">
        <div>
          <button className="back-link" onClick={() => setPage("map")} type="button">Live map <Icon name="chevron" size={13} /></button>
          <h1>{camera?.name ?? "Camera"}</h1>
          <p><Icon name="location" size={14} /> {camera?.borough ?? "Simulated location"} · {camera?.id ?? ""}</p>
        </div>
        <div className="review-actions"><span className="live-badge"><span className="live-dot" /> Demo camera network</span></div>
      </div>
      {incident ? (
        <div className="incident-banner">
          <span className="alert-pulse" />
          <div>
            <span>{isDemo(incident) ? "TEST / DEMO EVENT" : "POSSIBLE COLLISION SURFACED"}</span>
            <b>{incident.locationName} · {incident.cameraId}</b>
          </div>
          <time>{incident.detectedAt}</time>
          <span className="dispatch-pill"><Icon name="shield" size={15} /> {responder ? `Simulated ${responder.responderId}` : "No responder assigned"}</span>
        </div>
      ) : (
        <div className="incident-banner quiet">
          <span className="alert-pulse" />
          <div><span>MONITORING</span><b>No incident surfaced</b></div>
          <time>{camera?.status ?? "…"}</time>
          <span className="dispatch-pill">Demo camera network</span>
        </div>
      )}
      <div className="channel-layout">
        <section className="live-view-panel">
          {camera ? <Clip cameraId={camera.id} end={incident?.evidenceWindowEnd} start={incident?.evidenceWindowStart} /> : <p>Select a camera.</p>}
          <div className="live-controls"><span>{camera?.id}</span><span>Visual evidence</span></div>
          <div className="camera-footer"><span><Icon name="camera" size={15} /> Monitoring status · {camera?.status ?? "…"}</span><span>CV monitoring state · {incident ? "possible collision surfaced" : "no incident surfaced"}</span></div>
        </section>
        <aside className="incident-data">
          <div className="incident-data-head"><span className="eyebrow">INCIDENT RECORD</span><h2>Possible collision</h2><p>Presented from the working record. This screen does not decide that a collision occurred.</p></div>
          {incident && (
            <>
              <div className="priority-card">
                <span>OPERATIONAL RESPONSE PRIORITY</span>
                <div><b>{priorityLabel(incident.priority).slice(0, 2)}</b><p><strong>{priorityLabel(incident.priority)}</strong>Status · {incident.status}</p></div>
              </div>
              <div className="data-grid">
                <div><span>Camera</span><b>{incident.cameraId}</b><small>{incident.locationName}</small></div>
                <div><span>Clip time</span><b>{incident.evidenceWindowStart || "—"}</b><small>to {incident.evidenceWindowEnd || "—"}</small></div>
                <div><span>Tracks</span><b>{incident.participantTrackIds.length}</b><small>{incident.participantTrackIds.join(", ") || "none recorded"}</small></div>
                <div><span>Evidence status</span><b>{incident.evidenceStatus ?? "unavailable"}</b><small>Visual evidence</small></div>
              </div>
              <div className="dispatch-card">
                <div className="dispatch-head"><Icon name="users" /><div><b>Observable evidence</b><span>Recorded with the surfaced event</span></div></div>
                <ul>{notes.length > 0 ? notes.map((note) => <li key={note}><span />{note}</li>) : <li><span />No observation text was stored.</li>}</ul>
              </div>
              <div className="dispatch-card">
                <div className="dispatch-head"><Icon name="spark" /><div><b>Why this priority</b><span>From the existing priority record</span></div></div>
                <ul>{reasons.length > 0 ? reasons.map((reason) => <li key={reason}><span />{reason}</li>) : <li><span />No priority explanation was stored.</li>}</ul>
                <p>Evidence score on the record: {incident.collisionEvidenceScore}</p>
              </div>
              <div className="dispatch-card">
                <div className="dispatch-head"><Icon name="phone" /><div><b>Assigned simulated responder</b><span>{responder ? `${responder.name} · ${responder.status}` : "None assigned"}</span></div></div>
                {incident.status === "open" && (
                  <Button className="button-outline" disabled={busy} onClick={onAssign}>Assign nearest available responder</Button>
                )}
                {next && <Button className="button-primary" disabled={busy} onClick={() => onAdvance(next.step)}>{next.label}</Button>}
              </div>
            </>
          )}
          <section className="dispatch-card briefing-slot" data-testid="briefing-slot">
            <div className="dispatch-head"><Icon name="spark" /><div><b>Responder briefing</b><span>Not connected</span></div></div>
            <p>A briefing can appear here later. This screen does not generate one.</p>
          </section>
        </aside>
      </div>
    </main>
  );
}

function isDemo(incident: Incident) {
  return incident.detectionMode === "demo_fallback" || incident.incidentId === "DEMO-TEST-INCIDENT";
}

function viewCamera(camera: Camera, incidents: Incident[]): ViewCamera {
  const surfaced = incidents.some((incident) => incident.cameraId === camera.cameraId);
  const inactive = camera.status !== "active";
  return {
    id: camera.cameraId,
    name: camera.locationName,
    borough: "Simulated placement",
    status: inactive ? "Offline" : surfaced ? "Incident" : "Monitoring",
    detail: surfaced ? "Possible collision surfaced" : inactive ? "Not monitoring" : "No incident surfaced",
    risk: inactive ? "offline" : surfaced ? "critical" : "clear",
    latitude: camera.latitude,
    longitude: camera.longitude,
  };
}

export default function App() {
  const { isSignedIn } = useAuthProfileReady({ requireUser: true });
  const camerasQuery = useQuery<Camera>("cameras", { orderBy: "cameraId", orderDir: "asc" });
  const incidentsQuery = useQuery<Incident>("incidents", { orderBy: "detectedAt", orderDir: "desc" });
  const respondersQuery = useQuery<Responder>("responders", { orderBy: "responderId", orderDir: "asc" });
  const assignmentsQuery = useQuery<Assignment>("assignments");
  const assignmentWrites = useMutations<Assignment>("assignments");
  const incidentWrites = useMutations<Incident>("incidents");
  const responderWrites = useMutations<Responder>("responders");
  const [page, setPage] = useState<Page>("home");
  const [selectedId, setSelectedId] = useState<string>("");
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const allIncidents = incidentsQuery.records.map((record) => record.data);
  const open = activeIncidents(incidentsQuery.records).map((record) => record.data).sort(compareOperational);
  const cameras = camerasQuery.records.map((record) => viewCamera(record.data, open));
  const selectedCamera = cameras.find((camera) => camera.id === selectedId) ?? cameras.find((camera) => camera.risk === "critical") ?? cameras[0] ?? null;
  const selectedIncident = allIncidents.find((incident) => incident.incidentId === selectedIncidentId)
    ?? open.find((incident) => incident.cameraId === selectedCamera?.id)
    ?? null;
  const responder = respondersQuery.records.find((record) => record.data.responderId === selectedIncident?.assignedResponderId) ?? null;
  const assignment = assignmentsQuery.records.find((record) => record.data.incidentId === selectedIncident?.incidentId && record.data.status !== "resolved") ?? null;
  const navigate = (next: Page) => {
    setPage(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  async function advance(step: ProgressStep) {
    if (!assignment || !selectedIncident || !responder) return;
    const plan = progressPlan(step, new Date().toISOString());
    if (assignment.data.status !== plan.expectedStatus) return;
    setBusy(true);
    try {
      await assignmentWrites.putConfirmed(assignment.recordId, plan.assignment);
      const incidentRecord = incidentsQuery.records.find((record) => record.data.incidentId === selectedIncident.incidentId);
      if (incidentRecord) await incidentWrites.putConfirmed(incidentRecord.recordId, plan.incident);
      if (plan.responder) await responderWrites.putConfirmed(responder.recordId, plan.responder);
    } finally {
      setBusy(false);
    }
  }

  async function assign() {
    if (!selectedIncident) return;
    setBusy(true);
    try {
      await callAppAction("assignResponder", { incidentId: selectedIncident.incidentId });
    } finally {
      setBusy(false);
    }
  }

  const ready = camerasQuery.status === "ready";
  return (
    <div className="app">
      <Header monitoring={cameras.filter((camera) => camera.status !== "Offline").length} page={page} setPage={navigate} signedIn={Boolean(isSignedIn)} />
      {!isSignedIn && ready && <p className="live-write-error">Sign in to load the demo camera network from the working system.</p>}
      {page === "home" && (
        <HomePage
          active={open.length}
          alert={open[0] ?? null}
          available={countAvailableResponders(respondersQuery.records)}
          cameras={cameras}
          highPriority={open.filter((incident) => incident.priority === "high").length}
          setPage={navigate}
        />
      )}
      {page === "map" && (
        <MapPage
          cameras={cameras}
          incidents={open}
          openCamera={(camera) => { setSelectedId(camera.id); setSelectedIncidentId(""); navigate("channel"); }}
          openIncident={(incident) => { setSelectedIncidentId(incident.incidentId); setSelectedId(incident.cameraId); navigate("channel"); }}
          setPage={navigate}
        />
      )}
      {page === "channel" && (
        <ChannelPage
          assignment={assignment}
          busy={busy || !assignmentWrites.ready}
          camera={selectedCamera}
          incident={selectedIncident}
          onAdvance={(step) => void advance(step)}
          onAssign={() => void assign()}
          responder={responder?.data ?? null}
          setPage={navigate}
        />
      )}
    </div>
  );
}
