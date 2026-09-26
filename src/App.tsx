import { useState, type ReactNode } from "react";

type Page = "home" | "map" | "channel";
type IconName =
  | "arrow"
  | "bell"
  | "camera"
  | "car"
  | "chevron"
  | "clock"
  | "download"
  | "location"
  | "phone"
  | "play"
  | "shield"
  | "spark"
  | "users";

type Camera = {
  id: string;
  name: string;
  borough: string;
  status: "Incident" | "Monitoring" | "Offline";
  detail: string;
  position: string;
  risk: "critical" | "clear" | "offline";
};

const cameras: Camera[] = [
  { id: "CAM-042", name: "Atlantic Ave & 4th Ave", borough: "Brooklyn", status: "Incident", detail: "Collision detected · 34 sec ago", position: "cam-atlantic", risk: "critical" },
  { id: "CAM-018", name: "Canal St & Bowery", borough: "Manhattan", status: "Monitoring", detail: "Normal traffic flow", position: "cam-canal", risk: "clear" },
  { id: "CAM-067", name: "Queens Blvd & 71st Ave", borough: "Queens", status: "Monitoring", detail: "Heavy traffic", position: "cam-queens", risk: "clear" },
  { id: "CAM-031", name: "Grand Concourse & E 161st", borough: "Bronx", status: "Monitoring", detail: "Normal traffic flow", position: "cam-bronx", risk: "clear" },
  { id: "CAM-089", name: "Richmond Ter & Bay St", borough: "Staten Island", status: "Offline", detail: "Connection interrupted", position: "cam-staten", risk: "offline" },
];

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    camera: <><path d="M3 7h4l2-3h6l2 3h4v12H3z" /><circle cx="12" cy="13" r="3.5" /></>,
    car: <><path d="m5 11 2-5h10l2 5v7H5z" /><path d="M7 18v2m10-2v2M5 13h14" /><circle cx="8" cy="15" r="1" /><circle cx="16" cy="15" r="1" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    download: <><path d="M12 3v12m-4-4 4 4 4-4" /><path d="M5 19h14" /></>,
    location: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></>,
    phone: <path d="M8 3H5a2 2 0 0 0-2 2c0 8.8 7.2 16 16 16a2 2 0 0 0 2-2v-3l-4-1-1.5 2a13 13 0 0 1-8.5-8.5L9 7z" />,
    play: <path d="m9 7 8 5-8 5Z" />,
    shield: <path d="M12 3 5 6v5c0 4.6 3 8 7 10 4-2 7-5.4 7-10V6zM9 12l2 2 4-4" />,
    spark: <><path d="m12 3 1.3 4.2L17 9l-3.7 1.8L12 15l-1.3-4.2L7 9l3.7-1.8Z" /><path d="m19 15 .7 2.2L22 18l-2.3.8L19 21l-.7-2.2L16 18l2.3-.8Z" /></>,
    users: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-4 2-6 6-6s6 2 6 6" /><circle cx="17" cy="9" r="2" /><path d="M16 15c3 0 5 2 5 5" /></>,
  };
  return <svg aria-hidden="true" className="icon" height={size} viewBox="0 0 24 24" width={size}>{paths[name]}</svg>;
}

function Button({ children, className = "", onClick }: { children: ReactNode; className?: string; onClick?: () => void }) {
  return <button className={`button ${className}`} onClick={onClick} type="button">{children}</button>;
}

function Brand() {
  return <div className="brand"><div className="brand-mark"><span /><span /></div><span>nearmiss</span></div>;
}

function Header({ page, setPage }: { page: Page; setPage: (page: Page) => void }) {
  return (
    <header className="site-header">
      <button aria-label="Go to home" className="brand-button" onClick={() => setPage("home")}><Brand /></button>
      <nav aria-label="Primary navigation">
        <button className={page === "home" ? "nav-item active" : "nav-item"} onClick={() => setPage("home")}>Overview</button>
        <button className={page === "map" ? "nav-item active" : "nav-item"} onClick={() => setPage("map")}>Live map</button>
        <button className={page === "channel" ? "nav-item active" : "nav-item"} onClick={() => setPage("channel")}>Active incident</button>
      </nav>
      <div className="header-actions">
        <span className="city-pill"><span className="status-dot" /> 4 channels live</span>
        <Button className="button-compact button-light" onClick={() => setPage("map")}>Open operations <Icon name="arrow" size={16} /></Button>
      </div>
    </header>
  );
}

function CityMap({
  activeId,
  onHover,
  onSelect,
  preview = false,
}: {
  activeId?: string;
  onHover?: (id?: string) => void;
  onSelect?: (camera: Camera) => void;
  preview?: boolean;
}) {
  return (
    <div className={preview ? "city-map preview-map" : "city-map"} aria-label="Live New York City security camera map">
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
          className={`camera-pin ${camera.position} ${camera.risk} ${activeId === camera.id ? "pin-active" : ""}`}
          key={camera.id}
          onClick={() => onSelect?.(camera)}
          onMouseEnter={() => onHover?.(camera.id)}
          onMouseLeave={() => onHover?.()}
        >
          <span className="pin-ripple" /><span className="pin-core"><Icon name="camera" size={14} /></span>
          <span className="pin-label"><b>{camera.id}</b>{camera.name}</span>
        </button>
      ))}
      <div className="map-controls"><button>+</button><button>−</button></div>
      <div className="map-status"><span><i className="map-dot live" /> Live</span><span><i className="map-dot incident" /> Incident</span><span><i className="map-dot unavailable" /> Offline</span></div>
      {preview && (
        <div className="map-alert-card">
          <div><span className="alert-pulse" /><span>COLLISION DETECTED</span><time>34 sec ago</time></div>
          <strong>Atlantic Ave & 4th Ave</strong>
          <p>Possible two-vehicle collision · Priority 1</p>
        </div>
      )}
    </div>
  );
}

function HomePage({ setPage }: { setPage: (page: Page) => void }) {
  return (
    <main>
      <section className="hero response-hero">
        <div className="hero-copy">
          <div className="eyebrow hero-eyebrow"><span className="eyebrow-line" /> REAL-TIME CITY RESPONSE</div>
          <h1>See the impact.<br /><em>Send help faster.</em></h1>
          <p className="hero-lede">Nearmiss monitors NYC security cameras for collisions, verifies the scene, and sends police the location, severity, and vehicle data they need to respond.</p>
          <div className="hero-actions">
            <Button className="button-primary" onClick={() => setPage("map")}>Open live map <Icon name="arrow" /></Button>
            <Button className="button-ghost" onClick={() => setPage("channel")}><span className="play-chip"><Icon name="play" size={14} /></span> View active incident</Button>
          </div>
          <div className="trust-row">
            <span><Icon name="shield" size={16} /> Computer-vision verified</span>
            <span><Icon name="bell" size={16} /> Automatic officer alerts</span>
          </div>
        </div>
        <div className="hero-map">
          <div className="map-kicker"><span>NYC / LIVE OPERATIONS</span><span>4 OF 5 CHANNELS ONLINE</span></div>
          <CityMap preview />
        </div>
      </section>
      <section className="impact-section">
        <div className="impact-intro">
          <span className="eyebrow">A FASTER FIRST RESPONSE</span>
          <p>From first impact to a verified police alert—without waiting for a bystander to make the call.</p>
        </div>
        <div className="impact-metrics">
          <div><strong>&lt; 10 sec</strong><span>average detection time</span></div>
          <div><strong>24 / 7</strong><span>camera monitoring</span></div>
          <div><strong>5 data points</strong><span>sent with every alert</span></div>
        </div>
      </section>
      <section className="workflow-section">
        <div className="section-heading">
          <span className="eyebrow">FROM IMPACT TO RESPONSE</span>
          <h2>One collision. Every critical detail.</h2>
          <p>Nearmiss turns live camera footage into an actionable dispatch alert, giving officers a clearer picture before they arrive.</p>
        </div>
        <div className="workflow-timeline">
          <div className="timeline-rail" />
          <article className="timeline-step step-upload">
            <div className="timeline-marker"><span>01</span><Icon name="car" /></div>
            <div className="timeline-copy"><span className="timeline-time">00:00</span><h3>Detect the collision</h3><p>Computer vision identifies sudden impact, stopped vehicles, and unusual road movement.</p><span className="timeline-detail">Impact confidence · 98%</span></div>
          </article>
          <article className="timeline-step step-detect">
            <div className="timeline-marker"><span>02</span><Icon name="spark" /></div>
            <div className="timeline-copy"><span className="timeline-time">00:04</span><h3>Assess the scene</h3><p>The system estimates severity, vehicle speed, road blockage, and people involved.</p><div className="timeline-signal"><i /><i /><i /><i /><i /><i /><i /><i /></div></div>
          </article>
          <article className="timeline-step step-review">
            <div className="timeline-marker"><span>03</span><Icon name="phone" /></div>
            <div className="timeline-copy"><span className="timeline-time">00:08</span><h3>Notify nearby officers</h3><p>A location-rich priority alert is sent to the operations dashboard and officers in the field.</p><span className="timeline-detail timeline-ready"><span className="status-dot" /> Alert delivered</span></div>
          </article>
        </div>
      </section>
    </main>
  );
}

function MapPage({
  setPage,
  setSelected,
}: {
  setPage: (page: Page) => void;
  setSelected: (camera: Camera) => void;
}) {
  const [hovered, setHovered] = useState<string>();
  const openCamera = (camera: Camera) => {
    setSelected(camera);
    setPage("channel");
  };
  return (
    <main className="operations-page">
      <aside className="channels-panel">
        <div className="channels-head">
          <span className="eyebrow">NYC CAMERA NETWORK</span>
          <h1>Channels</h1>
          <p><span className="status-dot" /> 4 live · 1 offline</p>
        </div>
        <div className="channel-filter"><button className="selected">All cameras <span>5</span></button><button>Incidents <span>1</span></button></div>
        <div className="channel-list">
          {cameras.map((camera) => (
            <button
              className={`channel-card ${camera.risk} ${hovered === camera.id ? "hovered" : ""}`}
              key={camera.id}
              onClick={() => openCamera(camera)}
              onMouseEnter={() => setHovered(camera.id)}
              onMouseLeave={() => setHovered(undefined)}
            >
              <div className="channel-thumbnail"><ScenePreview compact incident={camera.risk === "critical"} /><span>{camera.status === "Offline" ? "OFFLINE" : "LIVE"}</span></div>
              <div className="channel-copy">
                <div><b>{camera.id}</b><span className={`channel-state ${camera.risk}`} /></div>
                <strong>{camera.name}</strong><p>{camera.borough}</p><small>{camera.detail}</small>
              </div>
              <Icon name="chevron" size={16} />
            </button>
          ))}
        </div>
      </aside>
      <section className="map-workspace">
        <div className="map-toolbar">
          <div><span className="eyebrow">LIVE OPERATIONS MAP</span><h2>New York City</h2></div>
          <div className="map-toolbar-actions"><span><Icon name="clock" size={14} /> Updated just now</span><button><Icon name="location" size={15} /> Recenter</button></div>
        </div>
        <CityMap activeId={hovered} onHover={setHovered} onSelect={openCamera} />
        <div className="active-alert-bar">
          <span className="alert-pulse" />
          <div><span>PRIORITY 1 · NEW INCIDENT</span><b>Possible collision at Atlantic Ave & 4th Ave</b></div>
          <span>Detected 34 sec ago</span>
          <Button className="button-alert" onClick={() => openCamera(cameras[0])}>View channel <Icon name="arrow" size={16} /></Button>
        </div>
      </section>
    </main>
  );
}

function ScenePreview({ compact = false, incident = true }: { compact?: boolean; incident?: boolean }) {
  return (
    <div className={`${compact ? "scene compact" : "scene"} ${incident ? "incident-scene" : "scene-normal"}`}>
      <div className="scene-sky" />
      <div className="building building-one"><span /><span /><span /></div><div className="building building-two"><span /><span /><span /></div><div className="building building-three"><span /><span /><span /></div>
      <div className="road"><span className="lane lane-one" /><span className="lane lane-two" /><div className="crosswalk">{Array.from({ length: 7 }).map((_, index) => <i key={index} />)}</div></div>
      <div className="vehicle car-one"><span /></div><div className="vehicle car-two"><span /></div><div className="person"><i /><b /></div>
      {incident && <><div className="tracking-box vehicle-track"><span>VEHICLE A · 42 MPH</span></div><div className="tracking-box car-two-track"><span>VEHICLE B</span></div><div className="distance-line"><span>IMPACT</span></div></>}
      {!compact && <><div className="camera-tag"><span className="live-dot" /> LIVE · CAM-042</div><div className="video-time">19:42:18</div></>}
    </div>
  );
}

function ChannelPage({ camera, setPage }: { camera: Camera; setPage: (page: Page) => void }) {
  return (
    <main className="channel-page">
      <div className="channel-topbar">
        <div><button className="back-link" onClick={() => setPage("map")}>Live map <Icon name="chevron" size={13} /></button><h1>{camera.name}</h1><p><Icon name="location" size={14} /> {camera.borough}, New York · {camera.id}</p></div>
        <div className="review-actions"><span className="live-badge"><span className="live-dot" /> Live channel</span><Button className="button-outline"><Icon name="download" size={16} /> Download clip</Button></div>
      </div>
      <div className="incident-banner"><span className="alert-pulse" /><div><span>COLLISION DETECTED · PRIORITY 1</span><b>Two-vehicle impact with possible lane obstruction</b></div><time>Detected 7:42:18 PM</time><span className="dispatch-pill"><Icon name="shield" size={15} /> Police notified</span></div>
      <div className="channel-layout">
        <section className="live-view-panel">
          <ScenePreview />
          <div className="live-controls"><Button className="control-button"><Icon name="play" size={15} /></Button><span>LIVE</span><div className="scrubber"><span /><i /></div><span>Go to live</span></div>
          <div className="camera-footer"><span><Icon name="camera" size={15} /> Fixed traffic camera · Northeast view</span><span>1080p · 30 FPS</span></div>
        </section>
        <aside className="incident-data">
          <div className="incident-data-head"><span className="eyebrow">INCIDENT INTELLIGENCE</span><h2>Automatic scene assessment</h2><p>Updated 3 seconds ago</p></div>
          <div className="priority-card"><span>RESPONSE PRIORITY</span><div><b>1</b><p><strong>Immediate response</strong>Possible injuries · Lane blocked</p></div></div>
          <div className="data-grid">
            <div><span>Impact speed</span><b>42 mph</b><small>Vehicle A estimate</small></div>
            <div><span>Vehicles</span><b>2</b><small>Both stationary</small></div>
            <div><span>People detected</span><b>3</b><small>1 exited vehicle</small></div>
            <div><span>Confidence</span><b>98%</b><small>Collision verified</small></div>
          </div>
          <div className="dispatch-card">
            <div className="dispatch-head"><Icon name="phone" /><div><b>Alert delivered</b><span>NYPD 78th Precinct</span></div><time>7:42:26 PM</time></div>
            <ul><li><span />GPS location and camera ID</li><li><span />10-second incident clip</li><li><span />Priority and speed estimate</li></ul>
          </div>
        </aside>
      </div>
    </main>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [selected, setSelected] = useState<Camera>(cameras[0]);
  const navigate = (next: Page) => {
    setPage(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <div className="app">
      <Header page={page} setPage={navigate} />
      {page === "home" && <HomePage setPage={navigate} />}
      {page === "map" && <MapPage setPage={navigate} setSelected={setSelected} />}
      {page === "channel" && <ChannelPage camera={selected} setPage={navigate} />}
    </div>
  );
}
