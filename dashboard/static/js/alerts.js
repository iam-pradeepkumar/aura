(function () {
  const sourceList = document.getElementById("source-list");
  const alertList = document.getElementById("alert-list");
  const alertCount = document.getElementById("alert-count");
  const lastPoll = document.getElementById("last-poll");
  const statusBadge = document.getElementById("status-badge");
  const safeZones = document.getElementById("safe-zones");
  const locName = document.getElementById("loc-name");
  const locCoords = document.getElementById("loc-coords");
  const errBox = document.getElementById("alert-error");
  const infoBox = document.getElementById("alert-info");
  const locLabel = document.getElementById("loc-label");
  const locLat = document.getElementById("loc-lat");
  const locLon = document.getElementById("loc-lon");
  const livePolling = document.getElementById("live-polling");
  const locSaveStatus = document.getElementById("loc-save-status");

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function severityClass(s) {
    const v = String(s || "info").toLowerCase();
    if (v === "critical") return "critical";
    if (v === "warning") return "warning";
    if (v === "advisory") return "advisory";
    return "info";
  }

  function sourceLabel(v) {
    if (v === "ok") return "ok";
    if (v === "skipped") return "not configured";
    if (v === "paused") return "paused";
    if (v === "offline") return "offline";
    return v;
  }

  function sourceClass(v) {
    if (v === "ok") return "status-ok";
    if (v === "offline" || v === "paused") return "status-offline";
    if (v === "skipped") return "";
    return "status-err";
  }

  function fillLocationForm(loc) {
    if (!loc) return;
    if (locLabel) locLabel.value = loc.name || "";
    if (locLat) locLat.value = loc.latitude ?? "";
    if (locLon) locLon.value = loc.longitude ?? "";
  }

  function renderAlerts(alerts) {
    alertCount.textContent = String(alerts.length);
    if (!alerts.length) {
      alertList.innerHTML = "<p style='opacity:0.7'>No public alerts yet. DM team must approve &amp; broadcast from <a href='/manage'>DM Console</a>.</p>";
      return;
    }
    alertList.innerHTML = alerts.map((a) => `
      <div class="alert-item ${severityClass(a.severity)}">
        <strong>${esc(a.title)}</strong>
        <div class="alert-meta">
          <span>📍 ${esc(a.location_name || "Watch zone")}</span>
          <span>${a.latitude}, ${a.longitude}</span>
          ${a.broadcast_at ? `<span>Broadcast: ${new Date(a.broadcast_at).toLocaleString()}</span>` : ""}
        </div>
        <p style="margin:0.35rem 0;font-size:0.95rem;white-space:pre-wrap">${esc(a.message)}</p>
        <span class="mono" style="font-size:0.8rem">${esc(a.alert_type)} · ${esc(a.severity)}</span>
      </div>`).join("");
  }

  async function loadStatus() {
    try {
      const r = await fetch("/api/alerts/status");
      if (!r.ok) throw new Error("Status " + r.status);
      const d = await r.json();
      const loc = d.location || {};
      locName.textContent = loc.name || "Watch zone";
      locCoords.textContent = `${loc.latitude ?? "—"}, ${loc.longitude ?? "—"}`;
      fillLocationForm(loc);
      if (livePolling) livePolling.checked = d.live_api_polling !== false;

      const sources = d.sources || {};
      sourceList.innerHTML = Object.entries(sources).map(([k, v]) =>
        `<li><strong>${esc(k)}</strong>: <span class="${sourceClass(v)}">${esc(sourceLabel(v))}</span></li>`
      ).join("");

      if (d.last_poll) {
        lastPoll.textContent = "Last poll: " + new Date(d.last_poll * 1000).toLocaleString();
      } else if (!d.live_api_polling) {
        lastPoll.textContent = "Live polling paused — use Simulate in DM Console.";
      } else {
        lastPoll.textContent = "Polling on startup…";
      }

      if (errBox) errBox.classList.add("hidden");
      if (infoBox) infoBox.classList.add("hidden");

      if (d.network_offline) {
        statusBadge.textContent = "OFFLINE";
        statusBadge.className = "badge-sketch status-offline";
        if (infoBox) {
          infoBox.textContent = (d.errors || []).join(" ");
          infoBox.classList.remove("hidden");
        }
      } else if ((d.errors || []).length > 0) {
        statusBadge.textContent = "DEGRADED";
        statusBadge.className = "badge-sketch status-warn";
        if (errBox) {
          errBox.textContent = d.errors.join(" · ");
          errBox.classList.remove("hidden");
        }
      } else if (!d.live_api_polling) {
        statusBadge.textContent = "DEMO";
        statusBadge.className = "badge-sketch";
        if (infoBox) {
          infoBox.textContent = "Live API polling is off. Simulated alerts still work via DM Console.";
          infoBox.classList.remove("hidden");
        }
      } else {
        statusBadge.textContent = "LIVE";
        statusBadge.className = "badge-sketch";
      }
    } catch (e) {
      if (errBox) {
        errBox.textContent = "Could not reach alert API: " + e.message;
        errBox.classList.remove("hidden");
      }
      statusBadge.textContent = "OFFLINE";
    }
  }

  async function saveLocation() {
    const body = {
      location: {
        name: locLabel?.value?.trim() || "Watch zone",
        latitude: parseFloat(locLat?.value),
        longitude: parseFloat(locLon?.value),
      },
      live_api_polling: livePolling?.checked ?? true,
    };
    if (!Number.isFinite(body.location.latitude) || !Number.isFinite(body.location.longitude)) {
      locSaveStatus.textContent = "Enter valid latitude and longitude.";
      return;
    }
    const r = await fetch("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    locSaveStatus.textContent = "Location saved ✓";
    locSaveStatus.className = "status-ok";
    await loadStatus();
    if (body.live_api_polling) {
      await fetch("/api/alerts/poll", { method: "POST" });
      await loadStatus();
    }
  }

  async function loadAlerts() {
    try {
      const r = await fetch("/api/alerts/list");
      if (!r.ok) throw new Error("List " + r.status);
      const d = await r.json();
      renderAlerts(d.alerts || []);
    } catch (e) {
      alertList.innerHTML = `<p class='status-err'>Failed to load alerts: ${esc(e.message)}</p>`;
    }
  }

  async function loadSafeZones() {
    try {
      const r = await fetch("/api/alerts/safe-zones");
      const d = await r.json();
      safeZones.innerHTML = (d.safe_zones || []).map((z) =>
        `<p><strong>${esc(z.name)}</strong> <span class="mono">(${z.lat}, ${z.lon})</span><br>${esc(z.note || "")}</p>`
      ).join("") || "<p>No safe zones configured — set in DM Console.</p>";
    } catch {
      safeZones.innerHTML = "<p>Could not load safe zones.</p>";
    }
  }

  function connectWs() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/alerts`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "alert_approved" || msg.type === "poll_complete" || msg.type === "test_alert" || msg.type === "settings_updated") {
        loadAlerts();
        loadStatus();
      }
    };
    ws.onclose = () => setTimeout(connectWs, 3000);
  }

  document.getElementById("btn-poll").onclick = async () => {
    const btn = document.getElementById("btn-poll");
    btn.disabled = true;
    btn.textContent = "Polling…";
    try {
      await fetch("/api/alerts/poll", { method: "POST" });
      await loadStatus();
      await loadAlerts();
    } finally {
      btn.disabled = false;
      btn.textContent = "Poll hazard APIs";
    }
  };

  document.getElementById("btn-save-location")?.addEventListener("click", () => {
    saveLocation().catch((e) => {
      locSaveStatus.textContent = "Save failed: " + e.message;
      locSaveStatus.className = "status-err";
    });
  });

  livePolling?.addEventListener("change", () => {
    saveLocation().catch(() => {});
  });

  loadStatus();
  loadAlerts();
  loadSafeZones();
  connectWs();
})();
