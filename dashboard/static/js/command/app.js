/* AURA SAR Command Center */

const S = {
  mode: "simulation",
  roster: [],
  zoneDefaults: null,
  selectedUnit: null,
  selectedTarget: null,
  missionRunning: false,
  zoneGeo: [],
  placedSurvivors: [],
  addressLabel: "",
  fitUnitsOnce: false,
};

let ws = null;
const coverageHistory = {};

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  return r.json();
}

async function boot() {
  const [roster, zone] = await Promise.all([
    api("/api/command/roster"),
    api("/api/command/zone"),
  ]);
  S.roster = roster.units || [];
  S.zoneDefaults = zone;
  renderUnits();
  AuraMap.init("map");
  AuraMap.onZoneChange = (pts) => {
    if (pts.length >= 3) S.zoneGeo = pts;
    setBanner(
      pts.length < 3
        ? `Click ${3 - pts.length} more corner(s) on the map (double-click to finish)`
        : `${pts.length} corners — click "Close polygon" or double-click map`
    );
  };
  AuraMap.onSurvivorChange = (list) => {
    S.placedSurvivors = list;
    setBanner(`${list.length} survivor(s) placed — add more or start rescue`);
  };
  if (zone.default_geo) {
    AuraMap.flyTo(zone.default_geo.lat, zone.default_geo.lon, zone.default_geo.label);
    S.addressLabel = zone.default_geo.label;
  }
  bindUi();
  connectWs();
  tickClock();
  setInterval(tickClock, 1000);
}

function bindUi() {
  document.getElementById("btn-search").addEventListener("click", searchAddress);
  document.getElementById("address-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchAddress();
  });
  document.getElementById("btn-draw").addEventListener("click", () => {
    AuraMap.setDrawMode(true);
    document.getElementById("btn-draw").classList.add("active");
    setBanner("Click map corners to outline the disaster area (double-click to close)");
  });
  document.getElementById("btn-close-zone").addEventListener("click", () => {
    const ring = AuraMap.closePolygon();
    if (ring) {
      S.zoneGeo = ring;
      AuraMap.setDrawMode(false);
      document.getElementById("btn-draw").classList.remove("active");
      setBanner(`Disaster zone sealed — ${ring.length} points. Place survivors inside the zone.`);
    } else {
      setBanner("Need at least 3 points before closing zone");
    }
  });
  document.getElementById("btn-clear-zone").addEventListener("click", () => {
    AuraMap.clearDraw();
    AuraMap.clearPlacedSurvivors();
    S.zoneGeo = [];
    S.placedSurvivors = [];
    setBanner("Zone cleared");
  });
  document.getElementById("btn-place-survivors").addEventListener("click", () => {
    const zone = AuraMap.getZoneGeo();
    if (!zone || zone.length < 3) {
      setBanner("Close the disaster zone polygon first, then place survivors");
      return;
    }
    AuraMap.setSurvivorMode(true);
    document.getElementById("btn-place-survivors").classList.add("active");
    document.getElementById("btn-draw").classList.remove("active");
    setBanner("Click inside the yellow zone to place survivors (simulation targets)");
  });
  document.getElementById("btn-clear-survivors").addEventListener("click", () => {
    AuraMap.clearPlacedSurvivors();
    S.placedSurvivors = [];
    AuraMap.setSurvivorMode(false);
    document.getElementById("btn-place-survivors").classList.remove("active");
    setBanner("Placed survivors cleared");
  });
  document.getElementById("btn-start").addEventListener("click", startMission);
  document.getElementById("btn-stop").addEventListener("click", stopMission);
  document.querySelectorAll(".chip").forEach((c) => {
    c.addEventListener("click", () => {
      S.mode = c.dataset.mode;
      document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === c));
    });
  });
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });
  document.getElementById("btn-toggle-sidebar")?.addEventListener("click", () => {
    const sb = document.querySelector(".sidebar");
    const btn = document.getElementById("btn-toggle-sidebar");
    sb?.classList.toggle("collapsed");
    if (btn) btn.textContent = sb?.classList.contains("collapsed") ? "▶" : "◀";
    setTimeout(() => AuraMap.resize(), 280);
  });
}

async function searchAddress() {
  const q = document.getElementById("address-input").value.trim();
  if (!q) return;
  setBanner("Searching address…");
  const res = await api(`/api/command/geocode?q=${encodeURIComponent(q)}`);
  const box = document.getElementById("geo-results");
  if (!res.results?.length) {
    setBanner("No results — try a more specific address");
    box.classList.remove("open");
    return;
  }
  box.innerHTML = res.results.map((r, i) =>
    `<div class="geo-item" data-i="${i}">${r.label}</div>`
  ).join("");
  box.classList.add("open");
  box.querySelectorAll(".geo-item").forEach((el) => {
    el.addEventListener("click", () => {
      const r = res.results[+el.dataset.i];
      AuraMap.flyTo(r.lat, r.lon, r.label);
      S.addressLabel = r.label;
      document.getElementById("address-input").value = r.label;
      box.classList.remove("open");
      AuraMap.setDrawMode(true);
      document.getElementById("btn-draw").classList.add("active");
      setBanner(`Located: ${r.label} — click map corners to mark disaster zone`);
    });
  });
}

function getEnabledUnits() {
  return S.roster.filter((u) => u.enabled);
}

async function startMission() {
  let ring = S.zoneGeo;
  if (!ring || ring.length < 3) {
    ring = AuraMap.closePolygon();
  }
  if (!ring || ring.length < 3) {
    alert("Search an address, then mark and close a disaster zone polygon (3+ points).");
    return;
  }
  if (!getEnabledUnits().length) {
    alert("Enable at least one spiderbot or drone in the Units tab.");
    return;
  }
  const survivors = AuraMap.getPlacedSurvivors();
  if (!survivors.length) {
    alert("Place at least one survivor inside the disaster zone (Place survivors tool).");
    return;
  }
  const anchor = AuraMap.getAnchor();
  if (!anchor) {
    alert("Search and fly to a real-world address first.");
    return;
  }
  document.getElementById("btn-start").disabled = true;
  await api("/api/command/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: S.mode,
      units: S.roster,
      geo_anchor: { lat: anchor.lat, lon: anchor.lon, label: S.addressLabel || anchor.label },
      zone_polygon_geo: ring,
      survivors_geo: survivors,
      gazebo: S.mode === "gazebo",
    }),
  });
  AuraMap.setSurvivorMode(false);
  document.getElementById("btn-place-survivors").classList.remove("active");
  S.missionRunning = true;
  S.zoneGeo = ring;
  S.fitUnitsOnce = true;
  document.getElementById("btn-stop").style.display = "block";
  document.getElementById("mission-phase").textContent = "RUNNING";
  AuraMap.fitToZone(ring);
  AuraMap.resize();
  setBanner("Rescue active — units patrol on CSI; HOMING when a survivor WiFi signal is detected");
}

async function stopMission() {
  await api("/api/command/stop", { method: "POST" });
  S.missionRunning = false;
  document.getElementById("btn-start").disabled = false;
  document.getElementById("btn-stop").style.display = "none";
  document.getElementById("mission-phase").textContent = "IDLE";
  setBanner("Mission stopped");
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/command`);
  ws.onopen = () => {
    document.getElementById("conn-label").textContent = "Live";
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "command_sensing" || msg.type === "mobile_sensing") {
        renderTelemetry(msg);
      }
    } catch (e) { console.warn(e); }
  };
  ws.onclose = () => {
    document.getElementById("conn-label").textContent = "Reconnecting";
    setTimeout(connectWs, 2000);
  };
}

function renderTelemetry(msg) {
  const data = msg.data || {};
  const mission = msg.mission || {};
  const units = msg.units_roster || mission.units || [];
  const targets = data.targets || [];

  document.getElementById("stat-survivors").textContent = data.survivors_detected ?? data.target_count ?? 0;
  document.getElementById("stat-spiders").textContent = units.filter((u) => u.type === "spiderbot").length;
  document.getElementById("stat-drones").textContent = units.filter((u) => u.type === "drone").length;
  document.getElementById("mission-phase").textContent = (mission.phase || "—").toUpperCase();
  document.getElementById("mission-cov").textContent = `${mission.coverage_pct ?? 0}%`;
  document.getElementById("mission-time").textContent = `${mission.elapsed_sec ?? 0}s`;

  AuraMap.showMissionZone(msg);
  AuraMap.updateUnits(units);
  AuraMap.updateWifiSignals(msg.wifi?.signals || []);
  AuraMap.updateSurvivors(targets);
  if (S.missionRunning && S.fitUnitsOnce && units.some((u) => u.lat != null)) {
    AuraMap.fitToUnits(units);
    S.fitUnitsOnce = false;
  }
  renderFleet(units, targets);

  if (S.selectedUnit) showUnitDetail(S.selectedUnit, data);
  if (S.selectedTarget) showSurvivorDetail(S.selectedTarget);
}

function renderUnits() {
  const el = document.getElementById("unit-list");
  el.innerHTML = S.roster.map((u) => `
    <div class="unit-row ${u.enabled ? "on" : ""}" data-id="${u.id}">
      <div class="unit-sym ${u.type === "drone" ? "drone" : "spider"}">${u.type === "drone" ? "DR" : "SP"}</div>
      <div>
        <div style="font-weight:600;font-size:0.82rem;">${u.name}</div>
        <div style="font-size:0.68rem;color:var(--muted);">Node ${u.node_id} · ${u.type === "drone" ? "Coverage relay" : "CSI vitals"}</div>
      </div>
    </div>
  `).join("");
  el.querySelectorAll(".unit-row").forEach((row) => {
    row.addEventListener("click", () => {
      const u = S.roster.find((x) => x.id === row.dataset.id);
      if (u) { u.enabled = !u.enabled; renderUnits(); }
    });
  });
}

function renderFleet(units, targets) {
  const bar = document.getElementById("fleet-scroll");
  let html = units.map((u) => `
    <div class="card" data-unit="${u.id}">
      <div class="head">
        <span class="name">${u.name}</span>
        <span class="badge ${(u.status || "patrol").toLowerCase()}">${u.status || "PATROL"}${u.wifi_signal > 0.12 ? " · CSI" : ""}</span>
      </div>
      <div class="sub">${u.lat != null ? `${u.lat.toFixed(5)}, ${u.lon.toFixed(5)}` : "Deploying…"}</div>
    </div>
  `).join("");
  const seen = new Set();
  targets.forEach((t) => {
    const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
    const confirmed = t.confirmed || prob >= 55;
    seen.add(String(t.id));
    html += `
      <div class="card survivor-card ${confirmed ? "confirmed" : ""}" data-target="${t.id}">
        <div style="font-size:0.7rem;color:var(--alert);">${confirmed ? "FOUND" : "SCANNING"} #${t.id}</div>
        <div class="prob">${prob}%</div>
        <div class="sub">${t.lat != null ? `${t.lat.toFixed(5)}, ${t.lon.toFixed(5)}` : "—"} · Resp ${t.respiration_bpm ? Math.round(t.respiration_bpm) : "—"} BPM</div>
      </div>
    `;
  });
  bar.innerHTML = html || '<div class="card"><span class="name">Awaiting mission…</span></div>';
  bar.querySelectorAll("[data-unit]").forEach((el) => {
    el.addEventListener("click", () => {
      S.selectedUnit = units.find((u) => u.id === el.dataset.unit);
      S.selectedTarget = null;
      switchTab("details");
      showUnitDetail(S.selectedUnit, {});
    });
  });
  bar.querySelectorAll("[data-target]").forEach((el) => {
    el.addEventListener("click", () => {
      S.selectedTarget = targets.find((t) => String(t.id) === el.dataset.target);
      S.selectedUnit = null;
      switchTab("details");
      showSurvivorDetail(S.selectedTarget);
    });
  });
}

function showUnitDetail(u, data) {
  if (!u) return;
  document.getElementById("detail-body").innerHTML = `
    <div class="section-title">Unit telemetry</div>
    <div class="row"><span class="k">ID</span><span>${u.name}</span></div>
    <div class="row"><span class="k">Role</span><span>${u.type === "drone" ? "Aerial coverage" : "Ground CSI"}</span></div>
    <div class="row"><span class="k">Status</span><span>${u.status || "—"}</span></div>
    <div class="row"><span class="k">Position</span><span>${u.lat != null ? `${u.lat.toFixed(6)}, ${u.lon.toFixed(6)}` : "—"}</span></div>
    <div class="row"><span class="k">Sensors</span><span>${(u.sensors || ["CSI", "Motion"]).join(", ")}</span></div>
    <div class="section-title" style="margin-top:1rem;">CSI pipeline</div>
    <div class="row"><span class="k">Motion</span><span>${data.motion_detected ? "DETECTED" : "CLEAR"}</span></div>
    <div class="row"><span class="k">Targets in field</span><span>${data.target_count ?? 0}</span></div>
  `;
}

function showSurvivorDetail(t) {
  if (!t) return;
  const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
  const vit = t.vitals_confidence_pct ?? Math.round((t.resp_confidence || 0) * 100);
  document.getElementById("detail-body").innerHTML = `
    <div class="section-title">Survivor detection</div>
    <div class="row"><span class="k">Probability</span><span style="color:var(--alert);font-family:var(--mono);">${prob}%</span></div>
    <div class="vitals-track"><i style="width:${prob}%"></i></div>
    <div class="row"><span class="k">Location</span><span>${t.lat?.toFixed(6)}, ${t.lon?.toFixed(6)}</span></div>
    <div class="row"><span class="k">Triage</span><span>${t.suggested_triage || "assessing"}</span></div>
    <div class="row"><span class="k">Respiration</span><span>${t.respiration_bpm ? Math.round(t.respiration_bpm) + " BPM" : "—"}</span></div>
    <div class="section-title" style="margin-top:0.75rem;">Vitals confidence</div>
    <div class="vitals-track"><i style="width:${vit}%"></i></div>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:0.35rem;">WiFi CSI ensemble · stationary-gated vitals</div>
  `;
}

function switchTab(id) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${id}`));
}

function setBanner(text) {
  document.getElementById("map-banner").textContent = text;
}

function tickClock() {
  document.getElementById("clock").textContent = new Date().toLocaleString();
}

document.addEventListener("DOMContentLoaded", boot);
