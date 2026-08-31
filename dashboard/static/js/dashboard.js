/* AURA Dashboard — single-screen layout */

let config = { area_size_m: 10, node_positions: {} };
let simSessionId = null;
let simWs = null;
let simFps = 30;
let hwWs = null;

const PERSON_COLORS = ["#10b981", "#34d399", "#6ee7b7", "#f59e0b", "#fbbf24", "#a78bfa"];

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
      mode: "markers+text", name: "Move",
      marker: { size: 12, color: "#ef4444" },
      text: moving.map((t) => `#${t.id}`), textposition: "top center", textfont: { size: 8, color: "#fca5a5" },
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
      mode: "markers+text", name: "Static",
      marker: { size: 12, color: "#f59e0b", symbol: "triangle-up" },
      text: staticT.map((t) => `#${t.id}`), textposition: "top center", textfont: { size: 8, color: "#fcd34d" },
    });
  }
  Plotly.react(elId, traces, {
    ...plotLayout,
    xaxis: { ...plotLayout.xaxis, range: [0, areaSize], title: { text: "X", font: { size: 9 } } },
    yaxis: { ...plotLayout.yaxis, range: [0, areaSize], title: { text: "Y", font: { size: 9 } }, scaleanchor: "x" },
    showlegend: false,
  }, { responsive: true, displayModeBar: false });
}

function renderPerPersonWaveforms(elId, targets, kind) {
  const el = document.getElementById(elId);
  if (!el || !targets?.length) return;

  const isResp = kind === "resp";
  const traces = [];
  const annotations = [];

  targets.forEach((t, i) => {
    const wave = isResp ? t.respiration_waveform : t.heartbeat_waveform;
    const bpm = isResp ? t.respiration_bpm : t.heartbeat_bpm;
    const color = PERSON_COLORS[i % PERSON_COLORS.length];
    if (wave?.length) {
      const x = wave.map((_, j) => j / Math.max(wave.length - 1, 1));
      traces.push({
        x, y: wave, type: "scatter", mode: "lines",
        name: `#${t.id}`,
        line: { color, width: 1.5 },
      });
    }
    annotations.push({
      text: `#${t.id}: ${bpm || "—"} BPM`,
      xref: "paper", yref: "paper",
      x: 1, y: 1 - i * 0.12,
      showarrow: false,
      xanchor: "right",
      font: { size: 8, color },
    });
  });

  if (!traces.length) {
    Plotly.react(elId, [], { ...plotLayout, annotations }, { responsive: true, displayModeBar: false });
    return;
  }

  Plotly.react(elId, traces, {
    ...plotLayout,
    annotations,
    showlegend: traces.length > 1,
    legend: { orientation: "h", y: 1.15, font: { size: 8 } },
  }, { responsive: true, displayModeBar: false });
}

function vitalsSummary(targets, kind) {
  if (!targets?.length) return "—";
  const vals = targets
    .map((t) => (kind === "resp" ? t.respiration_bpm : t.heartbeat_bpm))
    .filter((v) => v > 0);
  if (!vals.length) return "—";
  if (vals.length === 1) return `${vals[0]}`;
  return vals.map((v) => v.toFixed(0)).join(" / ");
}

function renderTargets(elId, targets) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!targets?.length) { el.innerHTML = "<span class='text-slate-600'>No targets</span>"; return; }
  el.innerHTML = targets.map((t, i) => {
    const color = PERSON_COLORS[i % PERSON_COLORS.length];
    return `
    <div class="border-b border-slate-800 py-1.5" style="border-left: 3px solid ${color}; padding-left: 6px;">
      <div><b class="text-white">Person #${t.id}</b> ${t.is_moving ? "🔴 moving" : "🟠 static"}
        <span class="text-slate-500">@ (${Number(t.x_m).toFixed(1)}, ${Number(t.y_m).toFixed(1)})</span></div>
      <div class="text-slate-400 mt-0.5">
        <span style="color:${color}">Resp ${t.respiration_bpm || "—"} BPM</span>
        <span class="mx-1">·</span>
        <span style="color:${color}">HR ${t.heartbeat_bpm || "—"} BPM</span>
        <span class="text-slate-600 ml-1">v=${t.velocity_mps}</span>
      </div>
    </div>`;
  }).join("");
}

function updateSensingUI(prefix, data, nodePositions, areaSize) {
  const targets = data.targets || [];
  const countEl = document.getElementById(`${prefix}-count`);
  if (countEl) countEl.textContent = data.target_count ?? targets.length ?? 0;

  const motionEl = document.getElementById(`${prefix}-motion`);
  if (motionEl) {
    motionEl.textContent = data.motion_detected ? "YES" : "STATIC";
    motionEl.className = "stat-value-sm " + (data.motion_detected ? "text-red-400" : "text-emerald-400");
  }

  const respEl = document.getElementById(`${prefix}-resp`);
  const hrEl = document.getElementById(`${prefix}-hr`);
  if (respEl) respEl.textContent = vitalsSummary(targets, "resp");
  if (hrEl) hrEl.textContent = vitalsSummary(targets, "hr");

  renderMap(`${prefix}-map`, data, nodePositions, areaSize);
  renderTargets(`${prefix}-targets`, targets);
  renderPerPersonWaveforms(`${prefix}-resp-chart`, targets, "resp");
  renderPerPersonWaveforms(`${prefix}-hr-chart`, targets, "hr");
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
    simFps = json.fps || 30;
    status.textContent = `${json.csi_frames} CSI @ ${json.sample_rate_hz}Hz · CSI-only · v${json.processor_version || "?"}`;
    document.getElementById("sim-meta").textContent =
      `${json.duration_sec}s · ${json.n_frames} frames · CSI count ${json.csi_person_estimate ?? json.target_count ?? 0}`;
    document.getElementById("sim-events").innerHTML =
      (json.events || []).map((e) => `<li>${e}</li>`).join("") || "<li>—</li>";

    updateSensingUI("sim", {
      target_count: json.target_count ?? json.csi_person_estimate ?? 0,
      motion_detected: json.motion_detected,
      targets: json.targets || [],
    }, config.node_positions, config.area_size_m);

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

    fetch(`/api/simulation/${simSessionId}/frame?index=0`)
      .then((r) => r.json())
      .then((fr) => {
        if (fr.data) {
          updateSensingUI("sim", fr.data, fr.node_positions, fr.area_size_m);
        }
      })
      .catch(() => {});
  } catch (err) {
    status.textContent = "Error: " + err.message;
  }
};

videoEl.addEventListener("timeupdate", () => {
  if (!simSessionId || !simWs || simWs.readyState !== WebSocket.OPEN) return;
  const idx = Math.floor(videoEl.currentTime * simFps);
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
