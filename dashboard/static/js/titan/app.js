/* AURA TITAN Command Center */

const state = {
  mode: "simulation",
  roster: [],
  selectedUnit: null,
  selectedSurvivor: null,
  missionRunning: false,
  connected: false,
  latest: null,
  zoneDefaults: null,
};

let ws = null;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  return r.json();
}

async function init() {
  const [roster, zone] = await Promise.all([
    api("/api/command/roster"),
    api("/api/command/zone"),
  ]);
  state.roster = roster.units || [];
  state.zoneDefaults = zone;
  renderRoster();
  TITANScene.areaSize = zone.area_size_m || 40;
  TITANScene.init(document.getElementById("map3d"));
  TITANScene.setZonePolygon(zone.zone_polygon || []);
  TITANScene.setObstacles(zone.obstacles || []);
  TITANScene.onPolygonPoint = (pts) => {
    document.getElementById("polygon-pts").textContent = `${pts.length} points marked`;
  };
  connectWs();
  updateClock();
  setInterval(updateClock, 1000);
}

function renderRoster() {
  const el = document.getElementById("unit-roster");
  el.innerHTML = state.roster.map((u) => `
    <label class="unit-check ${u.enabled ? "selected" : ""}" data-id="${u.id}">
      <input type="checkbox" ${u.enabled ? "checked" : ""} hidden />
      <div class="unit-icon ${u.type === "drone" ? "drone" : "spider"}">${u.type === "drone" ? "🛸" : "🕷"}</div>
      <div class="unit-meta">
        <div class="name">${u.name}</div>
        <div class="role">${u.type === "drone" ? "Aerial coverage + relay" : "CSI sensing + vitals"} · Node ${u.node_id}</div>
      </div>
    </label>
  `).join("");
  el.querySelectorAll(".unit-check").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.dataset.id;
      const u = state.roster.find((x) => x.id === id);
      if (u) { u.enabled = !u.enabled; renderRoster(); }
    });
  });
}

function getEnabledUnits() {
  return state.roster.filter((u) => u.enabled);
}

async function startMission() {
  const polygon = TITANScene.getPolygon();
  const zone = polygon.length >= 3 ? polygon : (state.zoneDefaults?.zone_polygon || []);
  if (zone.length < 3) {
    alert("Mark at least 3 points on the map to define the disaster zone.");
    return;
  }
  if (getEnabledUnits().length === 0) {
    alert("Assign at least one spiderbot or drone.");
    return;
  }
  document.getElementById("btn-start").disabled = true;
  const res = await api("/api/command/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: state.mode,
      units: state.roster,
      zone_polygon: zone,
      area_size_m: state.zoneDefaults?.area_size_m || 40,
      obstacles: state.zoneDefaults?.obstacles || [],
    }),
  });
  state.missionRunning = true;
  document.getElementById("btn-stop").style.display = "block";
  document.getElementById("mission-phase").textContent = "RUNNING";
}

async function stopMission() {
  await api("/api/command/stop", { method: "POST" });
  state.missionRunning = false;
  document.getElementById("btn-start").disabled = false;
  document.getElementById("btn-stop").style.display = "none";
  document.getElementById("mission-phase").textContent = "IDLE";
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/command`);
  ws.onopen = () => {
    state.connected = true;
    document.getElementById("conn-status").textContent = "Connected";
    document.querySelector(".status-dot").style.background = "#4ade80";
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "command_sensing" || msg.type === "mobile_sensing") {
        state.latest = msg;
        updateDashboard(msg);
      }
    } catch (e) { console.warn(e); }
  };
  ws.onclose = () => {
    state.connected = false;
    document.getElementById("conn-status").textContent = "Reconnecting…";
    setTimeout(connectWs, 2000);
  };
}

function updateDashboard(msg) {
  const data = msg.data || {};
  const mission = msg.mission || {};
  const units = msg.units_roster || mission.units || [];

  document.getElementById("stat-survivors").textContent = data.survivors_detected ?? data.target_count ?? 0;
  document.getElementById("stat-spiders").textContent = units.filter((u) => u.type === "spiderbot").length;
  document.getElementById("stat-drones").textContent = units.filter((u) => u.type === "drone").length;
  document.getElementById("mission-phase").textContent = (mission.phase || "—").toUpperCase();
  document.getElementById("mission-coverage").textContent = `${mission.coverage_pct ?? 0}%`;
  document.getElementById("mission-elapsed").textContent = `${mission.elapsed_sec ?? 0}s`;

  TITANScene.clearSurvivors();
  (data.targets || []).forEach((t) => TITANScene.upsertSurvivor(t));
  units.forEach((u) => TITANScene.upsertUnit(u));

  renderUnitCards(units, data.targets || []);
  if (state.selectedUnit) showUnitDetail(state.selectedUnit, data);
  if (state.selectedSurvivor) showSurvivorDetail(state.selectedSurvivor);
}

function renderUnitCards(units, targets) {
  const bar = document.getElementById("units-scroll");
  let html = units.map((u) => `
    <div class="unit-card ${state.selectedUnit?.id === u.id ? "selected" : ""}" data-unit="${u.id}">
      <div class="top">
        <span class="name">${u.name}</span>
        <span class="status-badge ${(u.status || "patrol").toLowerCase()}">${u.status || "PATROL"}</span>
      </div>
      <div class="coords">${u.x?.toFixed(1) ?? "—"}, ${u.y?.toFixed(1) ?? "—"}${u.z ? ` · ${u.z.toFixed(1)}m` : ""}</div>
    </div>
  `).join("");
  targets.forEach((t) => {
    const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
    html += `
      <div class="survivor-card" data-survivor="${t.id}">
        <div style="font-size:0.75rem;color:#f87171;">SURVIVOR #${t.id}</div>
        <div class="prob">${prob}%</div>
        <div style="font-size:0.65rem;color:#7a8fa6;">Resp ${t.respiration_bpm ? Math.round(t.respiration_bpm) : "—"} BPM · ${t.vitals_confidence_pct ?? 0}% vitals</div>
      </div>
    `;
  });
  bar.innerHTML = html;
  bar.querySelectorAll("[data-unit]").forEach((el) => {
    el.addEventListener("click", () => {
      const u = units.find((x) => x.id === el.dataset.unit);
      state.selectedUnit = u;
      state.selectedSurvivor = null;
      switchTab("details");
      showUnitDetail(u, state.latest?.data || {});
      renderUnitCards(units, targets);
    });
  });
  bar.querySelectorAll("[data-survivor]").forEach((el) => {
    el.addEventListener("click", () => {
      const t = targets.find((x) => String(x.id) === el.dataset.survivor);
      state.selectedSurvivor = t;
      state.selectedUnit = null;
      switchTab("details");
      showSurvivorDetail(t);
    });
  });
}

function showUnitDetail(u, data) {
  if (!u) return;
  const panel = document.getElementById("detail-content");
  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-avatar" style="background:rgba(56,189,248,0.15)">${u.type === "drone" ? "🛸" : "🕷"}</div>
      <div>
        <div style="font-weight:700;font-size:1rem;">${u.name}</div>
        <div style="font-size:0.75rem;color:#7a8fa6;">${u.type === "drone" ? "Aerial Unit" : "Spiderbot"} · Node ${u.node_id}</div>
      </div>
    </div>
    <div class="detail-row"><span class="k">Status</span><span>${u.status || "—"}</span></div>
    <div class="detail-row"><span class="k">Position</span><span>${u.x?.toFixed(2)}, ${u.y?.toFixed(2)}${u.z ? ` @ ${u.z.toFixed(1)}m` : ""}</span></div>
    <div class="detail-row"><span class="k">Sensors</span><span>${(u.sensors || []).map((s) => `<span class="tag">${s}</span>`).join("")}</span></div>
    <div class="detail-row"><span class="k">Detections</span><span>${data.target_count ?? 0} survivors in range</span></div>
    <div class="panel-section" style="margin-top:1rem;">
      <h3>Vitals pipeline</h3>
      <div class="detail-row"><span class="k">Motion</span><span>${data.motion_detected ? "DETECTED" : "CLEAR"}</span></div>
      <div class="detail-row"><span class="k">Respiration</span><span>${data.respiration_bpm ? Math.round(data.respiration_bpm) + " BPM" : "—"}</span></div>
    </div>
  `;
}

function showSurvivorDetail(t) {
  if (!t) return;
  const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
  const vitals = t.vitals_confidence_pct ?? Math.round((t.resp_confidence || 0) * 100);
  document.getElementById("detail-content").innerHTML = `
    <div class="detail-header">
      <div class="detail-avatar" style="background:rgba(248,113,113,0.15)">🆘</div>
      <div>
        <div style="font-weight:700;font-size:1rem;">Survivor #${t.id}</div>
        <div style="font-size:0.75rem;color:#f87171;">Detection probability ${prob}%</div>
      </div>
    </div>
    <div class="detail-row"><span class="k">Location</span><span>${t.x_m?.toFixed(2)}m, ${t.y_m?.toFixed(2)}m</span></div>
    <div class="detail-row"><span class="k">Triage</span><span>${t.suggested_triage || "assessing"}</span></div>
    <div class="detail-row"><span class="k">Respiration</span><span>${t.respiration_bpm ? Math.round(t.respiration_bpm) + " BPM" : "—"}</span></div>
    <div class="panel-section">
      <h3>Detection confidence</h3>
      <div style="font-size:0.8rem;margin-bottom:0.25rem;">Presence ${prob}%</div>
      <div class="vitals-bar"><span style="width:${prob}%"></span></div>
      <div style="font-size:0.8rem;margin:0.5rem 0 0.25rem;">Vitals ${vitals}%</div>
      <div class="vitals-bar"><span style="width:${vitals}%"></span></div>
    </div>
  `;
}

function switchTab(name) {
  document.querySelectorAll(".sidebar-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  document.querySelectorAll(".sidebar-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `panel-${name}`);
  });
}

function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent = now.toLocaleString();
}

document.addEventListener("DOMContentLoaded", () => {
  init();
  document.getElementById("btn-start").addEventListener("click", startMission);
  document.getElementById("btn-stop").addEventListener("click", stopMission);
  document.getElementById("btn-draw-zone").addEventListener("click", () => {
    TITANScene.setDrawMode(true);
    document.getElementById("btn-draw-zone").classList.add("active");
    document.getElementById("map-hint").textContent = "Click on the ground to mark disaster zone corners. Need 3+ points.";
  });
  document.getElementById("btn-clear-zone").addEventListener("click", () => {
    TITANScene.clearPolygon();
    TITANScene.setDrawMode(false);
    document.getElementById("btn-draw-zone").classList.remove("active");
    document.getElementById("polygon-pts").textContent = "0 points";
  });
  document.getElementById("btn-use-default").addEventListener("click", () => {
    if (state.zoneDefaults) {
      TITANScene.setZonePolygon(state.zoneDefaults.zone_polygon);
      document.getElementById("polygon-pts").textContent = "Default zone loaded";
    }
  });
  document.querySelectorAll(".sidebar-tabs button").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.addEventListener("click", () => {
      state.mode = b.dataset.mode;
      document.querySelectorAll(".mode-btn").forEach((x) => x.classList.toggle("active", x === b));
    });
  });
});
