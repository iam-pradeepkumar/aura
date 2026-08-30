/* AURA Dashboard — simulation upload + live hardware */

let config = { area_size_m: 10, node_positions: {} };
let simSessionId = null;
let simWs = null;
let hwWs = null;

const plotLayout = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "#020617",
  font: { color: "#94a3b8", size: 11 },
  margin: { l: 40, r: 20, t: 20, b: 40 },
  xaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
  yaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
};

document.getElementById("tab-simulation").onclick = () => setTab("simulation");
document.getElementById("tab-hardware").onclick = () => setTab("hardware");

function setTab(name) {
  document.getElementById("panel-simulation").classList.toggle("hidden", name !== "simulation");
  document.getElementById("panel-hardware").classList.toggle("hidden", name !== "hardware");
  document.getElementById("tab-simulation").classList.toggle("active", name === "simulation");
  document.getElementById("tab-hardware").classList.toggle("active", name === "hardware");
}

fetch("/api/config").then((r) => r.json()).then((c) => {
  config = c;
  renderMap("sim-map", { targets: [] }, config.node_positions, config.area_size_m || 10);
  renderMap("hw-map", { targets: [] }, config.node_positions, config.area_size_m || 10);
});

function renderMap(elId, data, nodePositions, areaSize) {
  const targets = data.targets || [];
  const moving = targets.filter((t) => t.is_moving);
  const staticT = targets.filter((t) => !t.is_moving);
  const nodeX = [], nodeY = [], nodeText = [];
  for (const [id, pos] of Object.entries(nodePositions || {})) {
    nodeX.push(pos[0]); nodeY.push(pos[1]); nodeText.push(`Node ${id}`);
  }
  const traces = [{
    x: nodeX, y: nodeY, mode: "markers+text", name: "ESP32 Nodes",
    marker: { size: 14, color: "#3b82f6", symbol: "square" },
    text: nodeText, textposition: "top center",
  }];
  if (moving.length) {
    traces.push({
      x: moving.map((t) => t.x_m), y: moving.map((t) => t.y_m),
      mode: "markers", name: "Moving", marker: { size: 16, color: "#ef4444" },
    });
    moving.forEach((t) => {
      if (t.trajectory?.length > 1) {
        traces.push({
          x: t.trajectory.map((p) => p[0]), y: t.trajectory.map((p) => p[1]),
          mode: "lines", line: { color: "rgba(148,163,184,0.5)", width: 1 }, showlegend: false,
        });
      }
    });
  }
  if (staticT.length) {
    traces.push({
      x: staticT.map((t) => t.x_m), y: staticT.map((t) => t.y_m),
      mode: "markers", name: "Static", marker: { size: 16, color: "#f59e0b", symbol: "triangle-up" },
    });
  }
  Plotly.react(elId, traces, {
    ...plotLayout,
    xaxis: { ...plotLayout.xaxis, range: [0, areaSize], title: "X (m)" },
    yaxis: { ...plotLayout.yaxis, range: [0, areaSize], title: "Y (m)", scaleanchor: "x" },
    showlegend: true, legend: { orientation: "h", y: -0.15 },
  }, { responsive: true, displayModeBar: false });
}

function renderWaveform(elId, wave, bpm, label, color) {
  if (!wave?.length) return;
  const x = wave.map((_, i) => i / Math.max(wave.length - 1, 1));
  Plotly.react(elId, [{ x, y: wave, type: "scatter", mode: "lines", line: { color, width: 2 } }], {
    ...plotLayout,
    title: { text: `${label}: ${bpm} BPM`, font: { size: 12, color: "#cbd5e1" } },
  }, { responsive: true, displayModeBar: false });
}

function renderTargets(elId, targets) {
  const el = document.getElementById(elId);
  if (!targets?.length) { el.innerHTML = "<p class='text-slate-500'>No targets detected</p>"; return; }
  el.innerHTML = targets.map((t) => `
    <div class="border border-slate-800 rounded-lg p-3 mb-2">
      <div class="font-semibold text-white">Target #${t.id} ${t.is_moving ? "Moving" : "Static"}</div>
      <div class="grid grid-cols-2 gap-1 mt-1 text-slate-400">
        <span>XY: (${t.x_m}, ${t.y_m}) m</span>
        <span>Velocity: ${t.velocity_mps} m/s</span>
        <span>Accel: ${t.acceleration_mps2} m/s²</span>
        <span>Resp ${t.respiration_bpm} · HR ${t.heartbeat_bpm} BPM</span>
      </div>
    </div>`).join("");
}

function updateSensingUI(prefix, data, nodePositions, areaSize) {
  document.getElementById(`${prefix}-count`).textContent = data.target_count ?? 0;
  const motionEl = document.getElementById(`${prefix}-motion`);
  if (motionEl) {
    motionEl.textContent = data.motion_detected ? "DETECTED" : "STATIC / VITALS";
    motionEl.className = "stat-value " + (data.motion_detected ? "text-red-400" : "text-emerald-400");
  }
  const respEl = document.getElementById(`${prefix}-resp`);
  const hrEl = document.getElementById(`${prefix}-hr`);
  if (respEl) respEl.textContent = `${data.respiration_bpm ?? 0}${respEl.textContent.includes("BPM") ? " BPM" : ""}`;
  if (hrEl) hrEl.textContent = `${data.heartbeat_bpm ?? 0}${hrEl.textContent.includes("BPM") ? " BPM" : ""}`;
  if (prefix === "sim") {
    document.getElementById("sim-resp").textContent = `${data.respiration_bpm ?? 0} BPM`;
    document.getElementById("sim-hr").textContent = `${data.heartbeat_bpm ?? 0} BPM`;
  }

  renderMap(`${prefix}-map`, data, nodePositions, areaSize);
  renderTargets(`${prefix}-targets`, data.targets);
  renderWaveform(`${prefix}-resp-chart`, data.respiration_waveform, data.respiration_bpm, "Respiration", "#10b981");
  renderWaveform(`${prefix}-hr-chart`, data.heartbeat_waveform, data.heartbeat_bpm, "Heartbeat", "#8b5cf6");
}

// --- Simulation ---
const videoEl = document.getElementById("sim-video-player");

document.getElementById("btn-run-simulation").onclick = async () => {
  const videoFile = document.getElementById("sim-video").files[0];
  const csiFile = document.getElementById("sim-csi").files[0];
  const fsVal = document.getElementById("sim-fs").value;
  const status = document.getElementById("sim-status");

  if (!videoFile || !csiFile) {
    status.textContent = "Please select both video and CSI files.";
    return;
  }

  status.textContent = "Processing CSI and aligning with video…";
  const form = new FormData();
  form.append("video", videoFile);
  form.append("csi", csiFile);
  if (fsVal) form.append("sample_rate", fsVal);

  const res = await fetch("/api/simulation/upload", { method: "POST", body: form });
  const json = await res.json();
  if (json.error) { status.textContent = "Error: " + json.error; return; }

  simSessionId = json.session_id;
  status.textContent = `Ready — ${json.csi_frames} CSI frames @ ${json.sample_rate_hz} Hz`;
  document.getElementById("sim-meta").textContent = `${json.duration_sec}s · ${json.n_frames} video frames`;
  document.getElementById("sim-results").classList.remove("hidden");
  document.getElementById("sim-events").innerHTML =
    (json.events || []).map((e) => `<li>${e}</li>`).join("") || "<li>No entry/exit events</li>";

  videoEl.src = `/api/simulation/${simSessionId}/video`;
  videoEl.load();

  if (simWs) simWs.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  simWs = new WebSocket(`${proto}://${location.host}/ws/simulation/${simSessionId}`);
  simWs.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "sensing") {
      updateSensingUI("sim", msg.data, msg.node_positions, msg.area_size_m);
    }
  };
};

videoEl.addEventListener("timeupdate", () => {
  if (!simSessionId || !simWs || simWs.readyState !== WebSocket.OPEN) return;
  const idx = Math.floor(videoEl.currentTime * 30);
  document.getElementById("sim-time").textContent = `${videoEl.currentTime.toFixed(2)}s`;
  simWs.send(JSON.stringify({ type: "frame", index: idx }));
});

// --- Hardware ---
document.getElementById("btn-start-hardware").onclick = async () => {
  await fetch("/api/hardware/start", { method: "POST" });
  document.getElementById("hw-status").textContent = "Listening UDP :5555 — connect ESP32 nodes to AURA_HUB";
  connectHardwareWs();
};

document.getElementById("btn-stop-hardware").onclick = async () => {
  await fetch("/api/hardware/stop", { method: "POST" });
  if (hwWs) { hwWs.close(); hwWs = null; }
  document.getElementById("hw-status").textContent = "Stopped";
};

function connectHardwareWs() {
  if (hwWs) hwWs.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  hwWs = new WebSocket(`${proto}://${location.host}/ws/hardware`);
  hwWs.onopen = () => {
    document.getElementById("hw-status").textContent = "Live — receiving CSI from wireless nodes";
  };
  hwWs.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "status") {
      document.getElementById("hw-status").textContent = msg.message;
      return;
    }
    if (msg.type !== "sensing") return;
    const d = msg.data;
    document.getElementById("hw-nodes-count").textContent = d.active_nodes;
    document.getElementById("hw-count").textContent = d.target_count;
    document.getElementById("hw-resp").textContent = `${d.respiration_bpm} BPM`;
    document.getElementById("hw-hr").textContent = `${d.heartbeat_bpm} BPM`;
    const motionEl = document.getElementById("hw-motion");
    motionEl.textContent = d.motion_detected ? "DETECTED" : "STATIC / VITALS";
    motionEl.className = "stat-value " + (d.motion_detected ? "text-red-400" : "text-emerald-400");
    updateSensingUI("hw", d, d.node_positions, d.area_size_m);
    document.getElementById("hw-nodes").innerHTML = (d.node_status || []).map((n) => `
      <li class="flex justify-between border border-slate-800 rounded px-3 py-2">
        <span>Node ${n.id} — ${n.status}</span>
        <span class="text-slate-500">RSSI ${n.rssi ?? "—"} · count ${n.count ?? 0}</span>
      </li>`).join("") || "<li class='text-slate-500'>No nodes connected — check AURA_HUB hotspot</li>";
    document.getElementById("hw-events").innerHTML =
      (d.events || []).map((e) => `<li>${e}</li>`).join("") || "<li>Waiting for events…</li>";
  };
}
