/* AURA Dashboard — single-screen layout */

let config = { area_size_m: 10, node_positions: {} };
let simSessionId = null;
let simWs = null;
let hwWs = null;

const plotLayout = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "#020617",
  font: { color: "#94a3b8", size: 9 },
  margin: { l: 32, r: 8, t: 8, b: 24 },
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
  setTimeout(() => window.dispatchEvent(new Event("resize")), 100);
}

fetch("/api/config").then((r) => r.json()).then((c) => {
  config = c;
  renderMap("sim-map", { targets: [] }, config.node_positions, config.area_size_m || 10);
  renderMap("hw-map", { targets: [] }, config.node_positions, config.area_size_m || 10);
});

function renderMap(elId, data, nodePositions, areaSize) {
  const el = document.getElementById(elId);
  if (!el) return;
  const targets = data.targets || [];
  const moving = targets.filter((t) => t.is_moving);
  const staticT = targets.filter((t) => !t.is_moving);
  const nodeX = [], nodeY = [], nodeText = [];
  for (const [id, pos] of Object.entries(nodePositions || {})) {
    nodeX.push(pos[0]); nodeY.push(pos[1]); nodeText.push(`N${id}`);
  }
  const traces = [{
    x: nodeX, y: nodeY, mode: "markers+text", name: "Nodes",
    marker: { size: 10, color: "#3b82f6", symbol: "square" },
    text: nodeText, textposition: "top center", textfont: { size: 8 },
  }];
  if (moving.length) {
    traces.push({
      x: moving.map((t) => t.x_m), y: moving.map((t) => t.y_m),
      mode: "markers", name: "Move", marker: { size: 12, color: "#ef4444" },
    });
    moving.forEach((t) => {
      if (t.trajectory?.length > 1) {
        traces.push({
          x: t.trajectory.map((p) => p[0]), y: t.trajectory.map((p) => p[1]),
          mode: "lines", line: { color: "rgba(148,163,184,0.45)", width: 1 }, showlegend: false,
        });
      }
    });
  }
  if (staticT.length) {
    traces.push({
      x: staticT.map((t) => t.x_m), y: staticT.map((t) => t.y_m),
      mode: "markers", name: "Static", marker: { size: 12, color: "#f59e0b", symbol: "triangle-up" },
    });
  }
  Plotly.react(elId, traces, {
    ...plotLayout,
    xaxis: { ...plotLayout.xaxis, range: [0, areaSize], title: { text: "X", font: { size: 9 } } },
    yaxis: { ...plotLayout.yaxis, range: [0, areaSize], title: { text: "Y", font: { size: 9 } }, scaleanchor: "x" },
    showlegend: false,
  }, { responsive: true, displayModeBar: false });
}

function renderWaveform(elId, wave, bpm, color) {
  if (!wave?.length) return;
  const x = wave.map((_, i) => i / Math.max(wave.length - 1, 1));
  Plotly.react(elId, [{ x, y: wave, type: "scatter", mode: "lines", line: { color, width: 1.5 } }], {
    ...plotLayout,
    annotations: [{ text: `${bpm} BPM`, xref: "paper", yref: "paper", x: 1, y: 1, showarrow: false, font: { size: 9, color: "#94a3b8" } }],
  }, { responsive: true, displayModeBar: false });
}

function renderTargets(elId, targets) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!targets?.length) { el.innerHTML = "<span class='text-slate-600'>No targets</span>"; return; }
  el.innerHTML = targets.map((t) => `
    <div class="border-b border-slate-800 py-1">
      <b class="text-white">#${t.id}</b> ${t.is_moving ? "🔴" : "🟠"}
      (${t.x_m}, ${t.y_m}) v=${t.velocity_mps} a=${t.acceleration_mps2}
      <span class="text-slate-500">R${t.respiration_bpm} HR${t.heartbeat_bpm}</span>
    </div>`).join("");
}

function updateSensingUI(prefix, data, nodePositions, areaSize) {
  const countEl = document.getElementById(`${prefix}-count`);
  if (countEl) countEl.textContent = data.target_count ?? 0;

  const motionEl = document.getElementById(`${prefix}-motion`);
  if (motionEl) {
    motionEl.textContent = data.motion_detected ? "YES" : "STATIC";
    motionEl.className = "stat-value-sm " + (data.motion_detected ? "text-red-400" : "text-emerald-400");
  }

  const respEl = document.getElementById(`${prefix}-resp`);
  const hrEl = document.getElementById(`${prefix}-hr`);
  if (respEl) respEl.textContent = `${data.respiration_bpm ?? 0}`;
  if (hrEl) hrEl.textContent = `${data.heartbeat_bpm ?? 0}`;

  renderMap(`${prefix}-map`, data, nodePositions, areaSize);
  renderTargets(`${prefix}-targets`, data.targets);
  renderWaveform(`${prefix}-resp-chart`, data.respiration_waveform, data.respiration_bpm, "#10b981");
  renderWaveform(`${prefix}-hr-chart`, data.heartbeat_waveform, data.heartbeat_bpm, "#8b5cf6");
}

// --- Simulation ---
const videoEl = document.getElementById("sim-video-player");

document.getElementById("btn-run-simulation").onclick = async () => {
  const videoFile = document.getElementById("sim-video").files[0];
  const csiFile = document.getElementById("sim-csi").files[0];
  const fsVal = document.getElementById("sim-fs").value;
  const status = document.getElementById("sim-status");

  if (!videoFile || !csiFile) {
    status.textContent = "Select video + CSI files.";
    return;
  }

  status.textContent = "Processing…";
  const form = new FormData();
  form.append("video", videoFile);
  form.append("csi", csiFile);
  if (fsVal) form.append("sample_rate", fsVal);

  try {
    const res = await fetch("/api/simulation/upload", { method: "POST", body: form });
    const json = await res.json();
    if (!res.ok) {
      status.textContent = "Error: " + (json.detail || json.error || res.statusText);
      return;
    }

    simSessionId = json.session_id;
    status.textContent = `${json.csi_frames} CSI @ ${json.sample_rate_hz}Hz`;
    document.getElementById("sim-meta").textContent = `${json.duration_sec}s · ${json.n_frames} frames`;
    document.getElementById("sim-events").innerHTML =
      (json.events || []).map((e) => `<li>${e}</li>`).join("") || "<li>—</li>";

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
  } catch (err) {
    status.textContent = "Error: " + err.message;
  }
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
  document.getElementById("hw-status").textContent = "Listening UDP :5555";
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
  hwWs.onopen = () => { document.getElementById("hw-status").textContent = "Live"; };
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
    document.getElementById("hw-resp").textContent = d.respiration_bpm;
    document.getElementById("hw-hr").textContent = d.heartbeat_bpm;
    updateSensingUI("hw", d, d.node_positions, d.area_size_m);
    document.getElementById("hw-nodes").innerHTML = (d.node_status || []).map((n) => `
      <li class="flex justify-between"><span>Node ${n.id}</span><span class="text-slate-500">${n.rssi ?? "—"} dBm · ${n.count ?? 0}</span></li>
    `).join("") || "<li class='text-slate-600'>No nodes</li>";
    document.getElementById("hw-events").innerHTML =
      (d.events || []).map((e) => `<li>${e}</li>`).join("") || "<li>—</li>";
  };
}

window.addEventListener("resize", () => {
  ["sim-map", "sim-resp-chart", "sim-hr-chart", "hw-map", "hw-resp-chart", "hw-hr-chart"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) Plotly.Plots.resize(el);
  });
});
