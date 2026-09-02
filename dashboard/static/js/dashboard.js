/* AURA Dashboard — click person to view individual vitals */

let config = { area_size_m: 10, node_positions: {} };
let simSessionId = null;
let simWs = null;
let simFps = 30;
let hwWs = null;
let hwPollTimer = null;

const PERSON_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#a78bfa", "#ec4899", "#14b8a6", "#f97316", "#8b5cf6"];
const RESP_COLOR = "#10b981";
const HR_COLOR = "#ef4444";

const selectedPerson = { sim: null, hw: null };
const lastSensing = { sim: null, hw: null };

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
  renderMap("sim-map", { targets: [] }, config.node_positions, config.area_size_m || 10, "sim");
  renderMap("hw-map", { targets: [] }, config.node_positions, config.area_size_m || 10, "hw");
});

function personColor(index) {
  return PERSON_COLORS[index % PERSON_COLORS.length];
}

function getSelectedTarget(prefix, targets) {
  if (!targets?.length) return null;
  const id = selectedPerson[prefix];
  let t = targets.find((x) => x.id === id);
  if (!t) {
    t = targets[0];
    selectedPerson[prefix] = t.id;
  }
  return t;
}

function selectPerson(prefix, targetId) {
  selectedPerson[prefix] = targetId;
  const cached = lastSensing[prefix];
  if (cached) {
    updateSensingUI(prefix, cached.data, cached.nodePositions, cached.areaSize, false);
  }
}

function renderMap(elId, data, nodePositions, areaSize, prefix) {
  const el = document.getElementById(elId);
  if (!el) return;
  const targets = data.targets || [];
  const selId = selectedPerson[prefix];
  const nodeX = [], nodeY = [], nodeText = [];
  for (const [id, pos] of Object.entries(nodePositions || {})) {
    nodeX.push(pos[0]); nodeY.push(pos[1]); nodeText.push(`N${id}`);
  }
  const traces = [{
    x: nodeX, y: nodeY, mode: "markers+text", name: "Nodes",
    marker: { size: 10, color: "#3b82f6", symbol: "square" },
    text: nodeText, textposition: "top center", textfont: { size: 8 },
  }];

  targets.forEach((t, i) => {
    const color = personColor(i);
    const selected = t.id === selId;
    traces.push({
      x: [t.x_m], y: [t.y_m],
      mode: "markers+text",
      name: `Person ${t.id}`,
      marker: {
        size: selected ? 16 : 12,
        color: t.is_moving ? "#ef4444" : color,
        symbol: t.is_moving ? "circle" : "triangle-up",
        line: selected ? { color: "#fff", width: 2 } : { width: 0 },
      },
      text: [`#${t.id}`],
      textposition: "top center",
      textfont: { size: 9, color: selected ? "#fff" : color },
      customdata: [[t.id]],
    });
    if (t.trajectory?.length > 1) {
      const trailWidth = prefix === "hw" ? 2.5 : 1;
      const trailAlpha = prefix === "hw" ? "99" : "66";
      traces.push({
        x: t.trajectory.map((p) => p[0]), y: t.trajectory.map((p) => p[1]),
        mode: "lines",
        line: { color: color + trailAlpha, width: trailWidth },
        showlegend: false,
        hoverinfo: "skip",
      });
    }
  });

  Plotly.react(elId, traces, {
    ...plotLayout,
    xaxis: { ...plotLayout.xaxis, range: [0, areaSize], title: { text: "X", font: { size: 9 } } },
    yaxis: { ...plotLayout.yaxis, range: [0, areaSize], title: { text: "Y", font: { size: 9 } }, scaleanchor: "x" },
    showlegend: false,
  }, { responsive: true, displayModeBar: false });

  el.on("plotly_click", (ev) => {
    const cd = ev.points?.[0]?.customdata;
    if (cd?.[0] != null) selectPerson(prefix, cd[0]);
  });
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
    line: { color, width: 2 },
  }], {
    ...plotLayout,
    annotations: [{
      text: `${label}: ${bpm || "—"} BPM`,
      xref: "paper", yref: "paper", x: 1, y: 1,
      showarrow: false, xanchor: "right", font: { size: 9, color },
    }],
  }, { responsive: true, displayModeBar: false });
}

function renderTargets(elId, targets, prefix) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!targets?.length) {
    el.innerHTML = "<span class='text-slate-600'>No targets</span>";
    return;
  }
  const selId = selectedPerson[prefix];
  el.innerHTML = `<p class="text-slate-600 text-xs mb-1">Click a person to view their vitals</p>` +
    targets.map((t, i) => {
      const color = personColor(i);
      const selected = t.id === selId;
      return `
      <div class="target-row ${selected ? "selected" : ""}" data-person-id="${t.id}" data-prefix="${prefix}"
           style="border-left: 3px solid ${color};">
        <div><b class="text-white">Person #${t.id}</b> ${t.is_moving ? "🔴 moving" : "🟠 static"}
          <span class="text-slate-500">@ (${Number(t.x_m).toFixed(1)}, ${Number(t.y_m).toFixed(1)})</span>
          ${t.velocity_mps > 0.1 ? `<span class="text-slate-500"> · ${Number(t.velocity_mps).toFixed(2)} m/s</span>` : ""}</div>
        <div class="text-slate-400 mt-0.5">
          <span style="color:${RESP_COLOR}">Resp ${t.respiration_bpm || "—"} BPM</span>
          <span class="mx-1">·</span>
          <span style="color:${HR_COLOR}">HR ${t.heartbeat_bpm || "—"} BPM</span>
        </div>
      </div>`;
    }).join("");

  el.querySelectorAll(".target-row").forEach((row) => {
    row.onclick = () => selectPerson(row.dataset.prefix, Number(row.dataset.personId));
  });
}

function updateSensingUI(prefix, data, nodePositions, areaSize, store = true) {
  const targets = data.targets || [];
  if (store) {
    lastSensing[prefix] = { data, nodePositions, areaSize };
    if (targets.length && !targets.find((t) => t.id === selectedPerson[prefix])) {
      selectedPerson[prefix] = targets[0].id;
    }
  }

  const countEl = document.getElementById(`${prefix}-count`);
  if (countEl) countEl.textContent = data.target_count ?? targets.length ?? 0;

  const motionEl = document.getElementById(`${prefix}-motion`);
  if (motionEl) {
    motionEl.textContent = data.motion_detected ? "YES" : "STATIC";
    motionEl.className = "stat-value-sm " + (data.motion_detected ? "text-red-400" : "text-emerald-400");
  }

  const selected = getSelectedTarget(prefix, targets);
  const respEl = document.getElementById(`${prefix}-resp`);
  const hrEl = document.getElementById(`${prefix}-hr`);
  if (respEl) respEl.textContent = selected?.respiration_bpm ? `${selected.respiration_bpm}` : "—";
  if (hrEl) hrEl.textContent = selected?.heartbeat_bpm ? `${selected.heartbeat_bpm}` : "—";

  renderMap(`${prefix}-map`, data, nodePositions, areaSize, prefix);
  renderTargets(`${prefix}-targets`, targets, prefix);

  if (selected) {
    renderSingleWaveform(
      `${prefix}-resp-chart`, selected.respiration_waveform,
      selected.respiration_bpm, RESP_COLOR, `Person #${selected.id}`
    );
    renderSingleWaveform(
      `${prefix}-hr-chart`, selected.heartbeat_waveform,
      selected.heartbeat_bpm, HR_COLOR, `Person #${selected.id}`
    );
  } else {
    renderSingleWaveform(`${prefix}-resp-chart`, [], 0, RESP_COLOR, "");
    renderSingleWaveform(`${prefix}-hr-chart`, [], 0, HR_COLOR, "");
  }
}

// --- Simulation ---
const videoEl = document.getElementById("sim-video-player");
const videoInput = document.getElementById("sim-video");
const csiMatInput = document.getElementById("sim-csi-mat");
const csiNpyInput = document.getElementById("sim-csi-npy");
const videoNameEl = document.getElementById("sim-video-name");
const csiMatNameEl = document.getElementById("sim-csi-mat-name");
const csiNpyNameEl = document.getElementById("sim-csi-npy-name");

function bindFileLabel(input, labelEl) {
  if (!input || !labelEl) return;
  input.addEventListener("change", () => {
    const f = input.files?.[0];
    labelEl.textContent = f ? f.name : "No file chosen";
    labelEl.classList.toggle("chosen", !!f);
  });
}
bindFileLabel(videoInput, videoNameEl);
bindFileLabel(csiMatInput, csiMatNameEl);
bindFileLabel(csiNpyInput, csiNpyNameEl);

document.getElementById("btn-run-simulation").onclick = async () => {
  const videoFile = videoInput?.files?.[0];
  const matFile = csiMatInput?.files?.[0];
  const npyFile = csiNpyInput?.files?.[0];
  const fsVal = document.getElementById("sim-fs").value;
  const status = document.getElementById("sim-status");

  if (!videoFile || !matFile || !npyFile) {
    status.textContent = "Select all three: video (.mp4), raw CSI (.mat), and preprocessed (.npy).";
    return;
  }

  const matExt = (matFile.name.split(".").pop() || "").toLowerCase();
  const npyExt = (npyFile.name.split(".").pop() || "").toLowerCase();
  if (matExt !== "mat") {
    status.textContent = "File 2 must be a .mat raw CSI file.";
    return;
  }
  if (npyExt !== "npy") {
    status.textContent = "File 3 must be a .npy preprocessed amplitude file.";
    return;
  }

  status.textContent = "Processing…";
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
    const warn = (json.warnings || []).join(" ");
    const fp = json.csi_fingerprint ? ` · CSI ${json.csi_fingerprint}` : "";
    const sync = json.sync_score != null ? ` · sync ${(json.sync_score * 100).toFixed(0)}%` : "";
    status.textContent = `${json.csi_frames} CSI @ ${json.sample_rate_hz}Hz · v${json.processor_version || "?"}${fp}${sync}`;
    if (warn) status.textContent += ` — ${warn}`;
    document.getElementById("sim-meta").textContent =
      `${json.duration_sec}s · ${json.n_frames} frames · count ${json.target_count ?? 0}` +
      (json.csi_load?.frames ? ` · CSI ${json.csi_load.frames}×${json.csi_load.subcarriers}` : "") +
      (json.csi_load?.merged_with_npy ? " · mat+npy fused" : "") +
      (json.csi_load?.npy_only_fusion ? " · amp+Hilbert phase" : "") +
      (json.csi_load?.has_phase === false && !json.csi_load?.npy_only_fusion ? " · ⚠ no phase" : "") +
      (json.confidence != null ? ` · conf ${(json.confidence * 100).toFixed(0)}%` : "") +
      (json.reliable === false ? " · ⚠ low confidence" : "");
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
        if (fr.data) updateSensingUI("sim", fr.data, fr.node_positions, fr.area_size_m);
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

function renderHwNodeList(nodeStatus) {
  const statusColor = (s) => {
    if (s === "active" || s === "good") return "text-emerald-400";
    if (s === "offline") return "text-slate-600";
    if (String(s).startsWith("buffering")) return "text-amber-400";
    return "text-sky-400";
  };
  document.getElementById("hw-nodes").innerHTML = (nodeStatus || []).map((n) => {
    const hz = n.packet_rate_hz ?? n.link?.packet_rate_hz ?? 0;
    const st = n.status || n.link?.status || "?";
    return `
      <li class="flex justify-between gap-2">
        <span>Node ${n.id}${n.ip ? ` · ${n.ip}` : ""}</span>
        <span class="${statusColor(st)}">${st} · ${hz} Hz</span>
      </li>`;
  }).join("") || "<li class='text-slate-600'>Waiting for nodes...</li>";
}

function startHwStatusPoll() {
  if (hwPollTimer) clearInterval(hwPollTimer);
  hwPollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/hardware/status");
      const d = await res.json();
      const expected = d.expected_nodes ?? 4;
      const online = d.active_nodes ?? 0;
      document.getElementById("hw-nodes-count").textContent = `${online}/${expected}`;
      if (!d.udp_listening) {
        document.getElementById("hw-warnings").textContent =
          "UDP not listening — stop udp_probe.py, restart dashboard.";
        document.getElementById("hw-warnings").className = "text-xs mt-2 text-amber-400";
        document.getElementById("hw-warnings").classList.remove("hidden");
      }
      renderHwNodeList(d.node_status);
    } catch (_) { /* ignore transient poll errors */ }
  }, 1500);
}

function stopHwStatusPoll() {
  if (hwPollTimer) {
    clearInterval(hwPollTimer);
    hwPollTimer = null;
  }
}

// --- Hardware ---
document.getElementById("btn-start-hardware").onclick = async () => {
  const statusEl = document.getElementById("hw-status");
  try {
    const res = await fetch("/api/hardware/start", { method: "POST" });
    const json = await res.json();
    if (!res.ok) {
      statusEl.textContent = "Error: " + (json.detail || res.statusText);
      return;
    }
    const pkts = json.total_packets ?? 0;
    const active = json.active_nodes ?? 0;
    statusEl.textContent = `Listening UDP :5555 · ${active} nodes · ${pkts} pkts`;
    if (json.node_status) renderHwNodeList(json.node_status);
    if (pkts === 0) {
      document.getElementById("hw-warnings").textContent =
        "No CSI packets yet — stop udp_probe.py if running, then click Start Live again.";
      document.getElementById("hw-warnings").classList.remove("hidden");
    }
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
    return;
  }
  startHwStatusPoll();
  connectHardwareWs();
};

document.getElementById("btn-stop-hardware").onclick = async () => {
  stopHwStatusPoll();
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
    if (d.error) {
      document.getElementById("hw-warnings").textContent = d.error;
      document.getElementById("hw-warnings").classList.remove("hidden");
      return;
    }
    const expected = d.expected_nodes ?? 4;
    const online = d.active_nodes ?? 0;
    const healthy = d.healthy_nodes ?? 0;
    document.getElementById("hw-nodes-count").textContent = `${online}/${expected}`;
    document.getElementById("hw-count").textContent = d.target_count;
    updateSensingUI("hw", d, d.node_positions, d.area_size_m);

    const warnEl = document.getElementById("hw-warnings");
    const warnings = d.warnings || [];
    if (warnings.length) {
      warnEl.className = "text-xs mt-2 text-amber-400";
      warnEl.textContent = warnings.join(" ");
      warnEl.classList.remove("hidden");
    } else {
      warnEl.textContent = healthy === expected
        ? `All ${expected} nodes streaming CSI`
        : `Online ${online}/${expected} — power TX, wait 15s`;
      warnEl.classList.remove("hidden");
      warnEl.className = healthy === expected
        ? "text-xs mt-2 text-emerald-400"
        : "text-xs mt-2 text-amber-400";
    }

    renderHwNodeList(d.node_status);
    document.getElementById("hw-events").innerHTML =
      (d.events || []).map((e) => `<li>${e}</li>`).join("") || "<li>—</li>";
  };
  hwWs.onclose = () => {
    document.getElementById("hw-status").textContent = "Reconnecting…";
    setTimeout(() => {
      if (hwPollTimer) connectHardwareWs();
    }, 2000);
  };
}

window.addEventListener("resize", () => {
  ["sim-map", "sim-resp-chart", "sim-hr-chart", "hw-map", "hw-resp-chart", "hw-hr-chart"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) Plotly.Plots.resize(el);
  });
});
