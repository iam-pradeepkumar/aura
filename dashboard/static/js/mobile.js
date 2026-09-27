/* AURA Mobile SAR dashboard — consumes /ws/mobile (reuses map rendering from dashboard.js patterns) */

const PERSON_COLORS = ["#ff4d4d", "#2d5da1", "#f59e0b", "#15803d"];
let mobileWs = null;

function renderMobileMap(msg) {
  const data = msg.data || {};
  const nodePos = msg.node_positions || {};
  const area = msg.area_size_m || 40;
  const targets = data.targets || [];
  const nodeX = [], nodeY = [], nodeText = [];
  for (const [id, pos] of Object.entries(nodePos)) {
    nodeX.push(pos[0]); nodeY.push(pos[1]); nodeText.push(`N${id}`);
  }
  const traces = [{
    x: nodeX, y: nodeY, mode: "markers+text", name: "Nodes",
    marker: { size: 12, color: "#2d5da1", symbol: "square" },
    text: nodeText, textposition: "top center",
  }];
  targets.forEach((t, i) => {
    traces.push({
      x: [t.x_m], y: [t.y_m], mode: "markers+text", name: `P${t.id}`,
      marker: { size: 12, color: PERSON_COLORS[i % PERSON_COLORS.length], symbol: t.is_moving ? "circle" : "triangle-up" },
      text: [`#${t.id}`], textposition: "top center",
    });
  });
  Plotly.react("mobile-map", traces, {
    xaxis: { range: [0, area], title: "X (m)" },
    yaxis: { range: [0, area], title: "Y (m)", scaleanchor: "x" },
    margin: { l: 40, r: 10, t: 10, b: 40 },
    showlegend: false,
  }, { responsive: true });
}

function updateMobileUI(msg) {
  const data = msg.data || {};
  const m = msg.mission || {};
  document.getElementById("mobile-count").textContent = data.target_count ?? 0;
  document.getElementById("mobile-motion").textContent = data.motion_detected ? "MOTION" : "CLEAR";
  document.getElementById("mobile-resp").textContent = data.respiration_bpm ? Math.round(data.respiration_bpm) : "—";
  const conf = (data.targets?.[0]?.resp_confidence || 0) * 100;
  document.getElementById("mobile-resp-conf").textContent = conf > 0 ? `${Math.round(conf)}%` : "—";
  document.getElementById("mission-status").textContent =
    `phase=${m.phase} t=${m.elapsed_sec}s cov=${m.coverage_pct}% det=${m.confirmed_detections}\n` +
    `rover=(${m.rover?.x},${m.rover?.y}) hold=${m.rover?.holding} drone=(${m.drone?.x},${m.drone?.y})`;
  renderMobileMap(msg);
}

function connectMobileWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  mobileWs = new WebSocket(`${proto}://${location.host}/ws/mobile`);
  mobileWs.onmessage = (ev) => {
    try { updateMobileUI(JSON.parse(ev.data)); } catch (e) { console.warn(e); }
  };
  mobileWs.onclose = () => setTimeout(connectMobileWs, 2000);
}

document.getElementById("btn-start-mobile")?.addEventListener("click", async () => {
  await fetch("/api/mobile/start", { method: "POST" });
  connectMobileWs();
});

connectMobileWs();
