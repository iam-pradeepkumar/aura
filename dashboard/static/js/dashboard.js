/* AURA Simulation Dashboard */

let config = { area_size_m: 10, node_positions: {} };
let simSessionId = null;
let simWs = null;
let simFps = 30;

const PERSON_COLORS = ["#22d3ee", "#818cf8", "#fbbf24", "#f472b6", "#34d399", "#fb923c", "#a78bfa", "#38bdf8"];
const RESP_COLOR = "#34d399";
const HR_COLOR = "#fb7185";

const selectedPerson = { sim: null };
const lastSensing = { sim: null };

const plotLayout = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "#030712",
  font: { color: "#94a3b8", size: 9, family: "DM Sans, system-ui, sans-serif" },
  margin: { l: 36, r: 10, t: 10, b: 28 },
  xaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
  yaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
};

fetch("/api/config").then((r) => r.json()).then((c) => {
  config = c;
  const badge = document.getElementById("processor-badge");
  if (badge) badge.textContent = `v${c.processor_version || "?"}`;
  renderMap("sim-map", { targets: [] }, config.node_positions, config.area_size_m || 10);
});

function personColor(index) {
  return PERSON_COLORS[index % PERSON_COLORS.length];
}

function animateValue(el, end, duration = 400) {
  if (!el) return;
  const start = parseFloat(el.dataset.val || "0") || 0;
  const target = parseFloat(end) || 0;
  if (Math.abs(target - start) < 0.01) {
    el.textContent = Number.isInteger(target) ? String(Math.round(target)) : target.toFixed(1);
    el.dataset.val = target;
    return;
  }
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const v = start + (target - start) * eased;
    el.textContent = Number.isInteger(target) ? String(Math.round(v)) : v.toFixed(1);
    if (p < 1) requestAnimationFrame(step);
    else el.dataset.val = target;
  };
  requestAnimationFrame(step);
}

function getSelectedTarget(targets) {
  if (!targets?.length) return null;
  let t = targets.find((x) => x.id === selectedPerson.sim);
  if (!t) {
    t = targets[0];
    selectedPerson.sim = t.id;
  }
  return t;
}

function selectPerson(targetId) {
  selectedPerson.sim = targetId;
  const cached = lastSensing.sim;
  if (cached) updateSensingUI(cached.data, cached.nodePositions, cached.areaSize, false);
}

function renderMap(elId, data, nodePositions, areaSize) {
  const targets = data.targets || [];
  const selId = selectedPerson.sim;
  const nodeX = [], nodeY = [], nodeText = [];
  for (const [id, pos] of Object.entries(nodePositions || {})) {
    nodeX.push(pos[0]); nodeY.push(pos[1]); nodeText.push(`N${id}`);
  }

  const traces = [{
    x: nodeX, y: nodeY, mode: "markers+text", name: "Nodes",
    marker: { size: 11, color: "#3b82f6", symbol: "square", line: { width: 1, color: "#1d4ed8" } },
    text: nodeText, textposition: "top center", textfont: { size: 8, color: "#93c5fd" },
  }];

  targets.forEach((t, i) => {
    const color = personColor(i);
    const selected = t.id === selId;
    traces.push({
      x: [t.x_m], y: [t.y_m], mode: "markers+text", name: `Person ${t.id}`,
      marker: {
        size: selected ? 15 : 11,
        color: t.is_moving ? "#f43f5e" : color,
        symbol: t.is_moving ? "circle" : "triangle-up",
        line: selected ? { color: "#f8fafc", width: 2 } : { width: 0 },
      },
      text: [`#${t.id}`], textposition: "top center",
      textfont: { size: 9, color: selected ? "#fff" : color },
      customdata: [[t.id]],
    });
    if (t.trajectory?.length > 1) {
      traces.push({
        x: t.trajectory.map((p) => p[0]), y: t.trajectory.map((p) => p[1]),
        mode: "lines", line: { color: color + "88", width: 1.5 },
        showlegend: false, hoverinfo: "skip",
      });
    }
  });

  Plotly.react(elId, traces, {
    ...plotLayout,
    xaxis: { ...plotLayout.xaxis, range: [0, areaSize], title: { text: "X (m)", font: { size: 9 } } },
    yaxis: { ...plotLayout.yaxis, range: [0, areaSize], title: { text: "Y (m)", font: { size: 9 } }, scaleanchor: "x" },
    showlegend: false,
    transition: { duration: 180, easing: "cubic-in-out" },
  }, { responsive: true, displayModeBar: false });

  const el = document.getElementById(elId);
  if (el) {
    el.on("plotly_click", (ev) => {
      const cd = ev.points?.[0]?.customdata;
      if (cd?.[0] != null) selectPerson(cd[0]);
    });
  }
}

function renderSingleWaveform(elId, wave, bpm, color, label) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!wave?.length) {
    Plotly.react(elId, [], {
      ...plotLayout,
      annotations: [{
        text: label ? `${label}: — BPM` : "—",
        xref: "paper", yref: "paper", x: 1, y: 1,
        showarrow: false, xanchor: "right", font: { size: 9, color: "#64748b" },
      }],
    }, { responsive: true, displayModeBar: false });
    return;
  }
  const x = wave.map((_, i) => i / Math.max(wave.length - 1, 1));
  Plotly.react(elId, [{
    x, y: wave, type: "scatter", mode: "lines",
    line: { color, width: 2, shape: "spline" },
    fill: "tozeroy", fillcolor: color + "22",
  }], {
    ...plotLayout,
    annotations: [{
      text: `${label}: ${bpm || "—"} BPM`,
      xref: "paper", yref: "paper", x: 1, y: 1,
      showarrow: false, xanchor: "right", font: { size: 9, color },
    }],
    transition: { duration: 150 },
  }, { responsive: true, displayModeBar: false });
}

function renderTargets(elId, targets) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!targets?.length) {
    el.innerHTML = "<span class='text-slate-600 text-xs'>No targets detected</span>";
    return;
  }
  const selId = selectedPerson.sim;
  el.innerHTML = targets.map((t, i) => {
    const color = personColor(i);
    const selected = t.id === selId;
    const state = t.is_moving ? '<span class="pill pill-motion">moving</span>' : '<span class="pill pill-static">static</span>';
    return `
      <div class="target-row ${selected ? "selected" : ""}" data-person-id="${t.id}" style="border-left-color:${color}">
        <div class="target-head">
          <span class="target-id">Person ${t.id}</span> ${state}
          <span class="target-coord">(${Number(t.x_m).toFixed(1)}, ${Number(t.y_m).toFixed(1)})</span>
        </div>
        <div class="target-vitals">
          <span style="color:${RESP_COLOR}">Resp ${t.respiration_bpm || "—"}</span>
          <span class="dot">·</span>
          <span style="color:${HR_COLOR}">HR ${t.heartbeat_bpm || "—"}</span>
        </div>
      </div>`;
  }).join("");

  el.querySelectorAll(".target-row").forEach((row) => {
    row.onclick = () => selectPerson(Number(row.dataset.personId));
  });
}

function updateSensingUI(data, nodePositions, areaSize, store = true) {
  const targets = data.targets || [];
  if (store) lastSensing.sim = { data, nodePositions, areaSize };

  animateValue(document.getElementById("sim-count"), data.target_count ?? targets.length ?? 0);

  const motionEl = document.getElementById("sim-motion");
  if (motionEl) {
    motionEl.textContent = data.motion_detected ? "YES" : "STATIC";
    motionEl.className = "stat-value-sm " + (data.motion_detected ? "text-rose-400 motion-pulse" : "text-emerald-400");
  }

  const selected = getSelectedTarget(targets);
  const respBpm = selected?.respiration_bpm || data.respiration_bpm;
  const hrBpm = selected?.heartbeat_bpm || data.heartbeat_bpm;
  const respEl = document.getElementById("sim-resp");
  const hrEl = document.getElementById("sim-hr");
  if (respEl) respEl.textContent = respBpm ? `${respBpm}` : "—";
  if (hrEl) hrEl.textContent = hrBpm ? `${hrBpm}` : "—";

  renderMap("sim-map", data, nodePositions, areaSize);
  renderTargets("sim-targets", targets);

  const respWave = selected?.respiration_waveform?.length ? selected.respiration_waveform : data.respiration_waveform || [];
  const hrWave = selected?.heartbeat_waveform?.length ? selected.heartbeat_waveform : data.heartbeat_waveform || [];
  renderSingleWaveform("sim-resp-chart", respWave, respBpm, RESP_COLOR, selected ? `P${selected.id}` : "");
  renderSingleWaveform("sim-hr-chart", hrWave, hrBpm, HR_COLOR, selected ? `P${selected.id}` : "");
}

const videoEl = document.getElementById("sim-video-player");
const runBtn = document.getElementById("btn-run-simulation");
const runSpinner = runBtn?.querySelector(".btn-spinner");
const runLabel = runBtn?.querySelector(".btn-label");

function setRunning(running) {
  if (!runBtn) return;
  runBtn.disabled = running;
  runSpinner?.classList.toggle("hidden", !running);
  if (runLabel) runLabel.textContent = running ? "Processing…" : "Run analysis";
}

["sim-video", "sim-csi-mat", "sim-csi-npy"].forEach((id, i) => {
  const input = document.getElementById(id);
  const label = document.getElementById(["sim-video-name", "sim-csi-mat-name", "sim-csi-npy-name"][i]);
  if (!input || !label) return;
  input.addEventListener("change", () => {
    const f = input.files?.[0];
    label.textContent = f ? f.name : "No file chosen";
    label.classList.toggle("chosen", !!f);
  });
});

runBtn.onclick = async () => {
  const videoFile = document.getElementById("sim-video")?.files?.[0];
  const matFile = document.getElementById("sim-csi-mat")?.files?.[0];
  const npyFile = document.getElementById("sim-csi-npy")?.files?.[0];
  const fsVal = document.getElementById("sim-fs").value;
  const status = document.getElementById("sim-status");

  if (!videoFile || !matFile || !npyFile) {
    status.textContent = "Select video, .mat, and .npy files.";
    return;
  }

  setRunning(true);
  status.textContent = "Uploading and processing CSI…";
  selectedPerson.sim = null;
  lastSensing.sim = null;

  const form = new FormData();
  form.append("video", videoFile);
  form.append("csi_mat", matFile);
  form.append("csi_npy", npyFile);
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
    status.textContent = `${json.csi_frames} CSI frames @ ${json.sample_rate_hz}Hz`;
    document.getElementById("sim-meta").textContent =
      `${json.duration_sec}s · ${json.n_frames} frames · sync ${((json.sync_score || 1) * 100).toFixed(0)}%`;
    document.getElementById("sim-events").innerHTML =
      (json.events || []).map((e) => `<li class="event-chip">${e}</li>`).join("") || "<li>—</li>";

    updateSensingUI({
      target_count: json.target_count ?? 0,
      motion_detected: json.motion_detected,
      targets: json.targets || [],
      respiration_bpm: json.respiration_bpm,
      heartbeat_bpm: json.heartbeat_bpm,
    }, config.node_positions, config.area_size_m);

    videoEl.src = `/api/simulation/${simSessionId}/video`;
    videoEl.load();
    document.querySelector(".video-card")?.classList.add("video-ready");

    if (simWs) simWs.close();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    simWs = new WebSocket(`${proto}://${location.host}/ws/simulation/${simSessionId}`);
    simWs.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "sensing") {
        updateSensingUI(msg.data, msg.node_positions, msg.area_size_m);
      }
    };

    fetch(`/api/simulation/${simSessionId}/frame?index=0`)
      .then((r) => r.json())
      .then((fr) => { if (fr.data) updateSensingUI(fr.data, fr.node_positions, fr.area_size_m); })
      .catch(() => {});
  } catch (err) {
    status.textContent = "Error: " + err.message;
  } finally {
    setRunning(false);
  }
};

videoEl?.addEventListener("timeupdate", () => {
  if (!simSessionId || !simWs || simWs.readyState !== WebSocket.OPEN) return;
  const idx = Math.floor(videoEl.currentTime * simFps);
  document.getElementById("sim-time").textContent = `${videoEl.currentTime.toFixed(2)}s`;
  simWs.send(JSON.stringify({ type: "frame", index: idx }));
});

window.addEventListener("resize", () => {
  ["sim-map", "sim-resp-chart", "sim-hr-chart"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) Plotly.Plots.resize(el);
  });
});
