(function () {
  const sourceList = document.getElementById("source-list");
  const alertList = document.getElementById("alert-list");
  const alertCount = document.getElementById("alert-count");
  const lastPoll = document.getElementById("last-poll");
  const statusBadge = document.getElementById("status-badge");
  const safeZones = document.getElementById("safe-zones");
  const locName = document.getElementById("loc-name");
  const locCoords = document.getElementById("loc-coords");

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function renderAlerts(alerts) {
    alertCount.textContent = String(alerts.length);
    if (!alerts.length) {
      alertList.innerHTML = "<p style='opacity:0.7'>No active alerts. Monitoring…</p>";
      return;
    }
    alertList.innerHTML = alerts.map((a) => `
      <div class="alert-item ${a.severity || "watch"}">
        <strong>${esc(a.title)}</strong>
        <p style="margin:0.25rem 0;font-size:0.95rem">${esc(a.message || "")}</p>
        <span class="mono" style="font-size:0.8rem">${a.alert_type} · ${a.severity} · risk ${Math.round((a.risk_score||0)*100)}%</span>
      </div>`).join("");
  }

  async function loadStatus() {
    const r = await fetch("/api/alerts/status");
    const d = await r.json();
    const loc = d.location || {};
    locName.textContent = loc.name || "Watch zone";
    locCoords.textContent = `${loc.latitude}, ${loc.longitude}`;
    sourceList.innerHTML = Object.entries(d.sources || {}).map(([k, v]) =>
      `<li><strong>${k}</strong>: <span class="${v === "ok" ? "status-ok" : "status-err"}">${esc(v)}</span></li>`
    ).join("");
    if (d.last_poll) lastPoll.textContent = "Last poll: " + new Date(d.last_poll * 1000).toLocaleString();
    statusBadge.textContent = d.ok ? "LIVE" : "ERROR";
  }

  async function loadAlerts() {
    const r = await fetch("/api/alerts/list");
    const d = await r.json();
    renderAlerts(d.alerts || []);
  }

  async function loadSafeZones() {
    const r = await fetch("/api/alerts/safe-zones");
    const d = await r.json();
    safeZones.innerHTML = (d.safe_zones || []).map((z) =>
      `<p><strong>${esc(z.name)}</strong> — ${esc(z.note || "")}</p>`
    ).join("") || "<p>No safe zones configured.</p>";
  }

  function connectWs() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/alerts`);
    ws.onopen = () => { statusBadge.textContent = "LIVE"; };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "poll_complete" || msg.type === "test_alert") loadAlerts();
      if (msg.type === "alert_approved") loadAlerts();
    };
    ws.onclose = () => setTimeout(connectWs, 3000);
  }

  document.getElementById("btn-poll").onclick = async () => {
    await fetch("/api/alerts/poll", { method: "POST" });
    await loadStatus();
    await loadAlerts();
  };

  loadStatus();
  loadAlerts();
  loadSafeZones();
  connectWs();
})();
