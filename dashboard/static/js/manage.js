(function () {
  const pendingList = document.getElementById("pending-list");
  const pendingCount = document.getElementById("pending-count");
  const broadcastTitle = document.getElementById("broadcast-title");
  const broadcastMessage = document.getElementById("broadcast-message");
  const zoneEditor = document.getElementById("zone-editor");
  const zoneMap = document.getElementById("zone-map");
  const preview = document.getElementById("broadcast-preview");
  const dmError = document.getElementById("dm-error");
  const dmStatus = document.getElementById("dm-status");
  const webhookUrl = document.getElementById("webhook-url");
  const webhookToken = document.getElementById("webhook-token");
  const webhookStatus = document.getElementById("webhook-status");
  const simulateStatus = document.getElementById("simulate-status");

  let zones = [];
  let selectedId = null;
  let watchLocation = {};

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }

  function showError(msg) {
    dmError.textContent = msg;
    dmError.classList.remove("hidden");
  }

  function clearError() {
    dmError.classList.add("hidden");
  }

  async function api(path, opts = {}) {
    const r = await fetch(path, opts);
    if (!r.ok) {
      const t = await r.text();
      throw new Error(t || `HTTP ${r.status}`);
    }
    return r.json();
  }

  function updateMap() {
    if (!zones.length) {
      zoneMap.src = "about:blank";
      return;
    }
    const z = zones[0];
    zoneMap.src = `https://www.openstreetmap.org/export/embed.html?bbox=${z.lon - 0.02}%2C${z.lat - 0.02}%2C${z.lon + 0.02}%2C${z.lat + 0.02}&layer=mapnik&marker=${z.lat}%2C${z.lon}`;
  }

  function renderZones() {
    zoneEditor.innerHTML = zones.map((z, i) => `
      <div class="zone-row" data-idx="${i}">
        <input class="input-sketch zone-name" value="${esc(z.name)}" placeholder="Shelter name" />
        <input class="input-sketch zone-lat" type="number" step="0.000001" value="${z.lat}" placeholder="Lat" />
        <input class="input-sketch zone-lon" type="number" step="0.000001" value="${z.lon}" placeholder="Lon" />
        <input class="input-sketch zone-note" value="${esc(z.note || "")}" placeholder="Note" />
        <button type="button" class="btn-sketch secondary btn-del-zone" style="min-height:40px;padding:0.35rem 0.75rem;">✕</button>
      </div>`).join("");
    zoneEditor.querySelectorAll(".btn-del-zone").forEach((btn) => {
      btn.onclick = () => {
        zones.splice(parseInt(btn.closest(".zone-row").dataset.idx, 10), 1);
        renderZones();
        updatePreview();
      };
    });
    zoneEditor.querySelectorAll("input").forEach((inp) => {
      inp.oninput = () => {
        readZonesFromDom();
        updateMap();
        updatePreview();
      };
    });
    updateMap();
  }

  function readZonesFromDom() {
    zones = [];
    zoneEditor.querySelectorAll(".zone-row").forEach((row) => {
      zones.push({
        name: row.querySelector(".zone-name").value.trim(),
        lat: parseFloat(row.querySelector(".zone-lat").value) || 0,
        lon: parseFloat(row.querySelector(".zone-lon").value) || 0,
        note: row.querySelector(".zone-note").value.trim(),
      });
    });
  }

  function zoneText() {
    return zones.map((z) => `• ${z.name} (${z.lat}, ${z.lon}) — ${z.note || "Shelter"}`).join("\n");
  }

  function updatePreview(item) {
    const title = item?.custom_title || broadcastTitle.value || "Alert";
    const body = item?.custom_message || broadcastMessage.value || "";
    const a = item?.alert || {};
    preview.innerHTML = `
<strong>${esc(title)}</strong>
<p style="margin:0.5rem 0">${esc(body)}</p>
<div class="alert-meta">
  <span>📍 ${esc(a.metadata?.region || watchLocation.name || "Watch zone")}</span>
  <span>Coords: ${a.latitude ?? watchLocation.latitude ?? "—"}, ${a.longitude ?? watchLocation.longitude ?? "—"}</span>
  ${a.distance_km != null ? `<span>Distance: ${a.distance_km} km</span>` : ""}
  <span>Severity: ${esc(a.severity || "—")} · Type: ${esc(a.alert_type || "—")}</span>
</div>
${zones.length ? `<p style="margin-top:0.75rem"><strong>Safe zones:</strong><br>${esc(zoneText()).replace(/\n/g, "<br>")}</p>` : ""}`;
  }

  function renderPending(items) {
    pendingCount.textContent = String(items.length);
    if (!items.length) {
      pendingList.innerHTML = "<p style='opacity:0.7'>No pending alerts. Click <strong>Simulate hazard alert</strong>.</p>";
      selectedId = null;
      updatePreview();
      return;
    }
    pendingList.innerHTML = items.map((item) => {
      const a = item.alert || {};
      const id = item.id || a.id;
      const sel = id === selectedId ? " style='outline:3px solid var(--pen)'" : "";
      return `
        <div class="alert-item pending severity-${esc(a.severity)}" data-id="${esc(id)}"${sel}>
          <strong>${esc(a.title)}</strong>
          <div class="alert-meta">
            <span>📍 ${esc(a.metadata?.region || watchLocation.name || "")}</span>
            <span>${a.latitude}, ${a.longitude}</span>
            <span>${esc(a.alert_type)} · ${esc(a.severity)} · risk ${Math.round((a.metadata?.magnitude || 0.42) * 100) || Math.round((a.distance_km || 48) / 2)}%</span>
            <span class="mono" style="font-size:0.8rem">ID ${esc(id)} · ${new Date(item.queued_at).toLocaleString()}</span>
          </div>
          <p style="margin:0.35rem 0;font-size:0.95rem">${esc(a.message)}</p>
          <label style="font-weight:700;font-size:0.9rem;">Edit title for this alert</label>
          <input class="input-sketch draft-title" data-id="${esc(id)}" value="${esc(item.custom_title || broadcastTitle.value)}" style="margin:0.25rem 0;" />
          <label style="font-weight:700;font-size:0.9rem;">Edit message for this alert</label>
          <textarea class="textarea-sketch draft-message" data-id="${esc(id)}" style="min-height:80px;margin:0.25rem 0 0.75rem;">${esc(item.custom_message || broadcastMessage.value)}</textarea>
          <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
            <button class="btn-sketch btn-broadcast" data-id="${esc(id)}" style="min-height:44px;font-size:1.05rem">📢 Broadcast to area</button>
            <button class="btn-sketch secondary btn-save-draft" data-id="${esc(id)}" style="min-height:44px">Save draft</button>
            <button class="btn-sketch secondary btn-reject" data-id="${esc(id)}" style="min-height:44px">Reject</button>
          </div>
        </div>`;
    }).join("");

    pendingList.querySelectorAll(".alert-item").forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.closest("button") || ev.target.closest("input") || ev.target.closest("textarea")) return;
        selectedId = el.dataset.id;
        const item = items.find((i) => (i.id || i.alert?.id) === selectedId);
        updatePreview(item);
        renderPending(items);
      };
    });

    pendingList.querySelectorAll(".btn-broadcast").forEach((btn) => {
      btn.onclick = () => broadcast(btn.dataset.id);
    });
    pendingList.querySelectorAll(".btn-save-draft").forEach((btn) => {
      btn.onclick = () => saveDraft(btn.dataset.id);
    });
    pendingList.querySelectorAll(".btn-reject").forEach((btn) => {
      btn.onclick = () => reject(btn.dataset.id);
    });
    pendingList.querySelectorAll(".draft-title, .draft-message").forEach((el) => {
      el.oninput = () => {
        selectedId = el.dataset.id;
        const item = items.find((i) => (i.id || i.alert?.id) === selectedId);
        if (item) {
          if (el.classList.contains("draft-title")) item.custom_title = el.value;
          else item.custom_message = el.value;
          updatePreview(item);
        }
      };
    });
  }

  async function loadSettings() {
    const d = await api("/api/alerts/settings");
    watchLocation = d.location || {};
    broadcastTitle.value = d.broadcast_title || "";
    broadcastMessage.value = d.broadcast_message || "";
    zones = d.safe_zones || [];
    webhookUrl.value = d.webhook_url || "";
    webhookStatus.textContent = d.webhook_url ? "Webhook configured ✓" : "Optional — LAN broadcast works without webhook";
    if (d.bearer_token_set) webhookToken.placeholder = "Token saved";
    renderZones();
    dmStatus.textContent = watchLocation.name ? `📍 ${watchLocation.name}` : "DM LIVE";
  }

  async function loadPending() {
    const d = await api("/api/alerts/pending");
    renderPending(d.pending || []);
  }

  async function saveDraft(id) {
    clearError();
    const titleEl = pendingList.querySelector(`.draft-title[data-id="${id}"]`);
    const msgEl = pendingList.querySelector(`.draft-message[data-id="${id}"]`);
    await api(`/api/alerts/${id}/draft`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        custom_title: titleEl?.value || "",
        custom_message: msgEl?.value || "",
      }),
    });
    simulateStatus.textContent = "Draft saved.";
    await loadPending();
  }

  async function broadcast(id) {
    clearError();
    const titleEl = pendingList.querySelector(`.draft-title[data-id="${id}"]`);
    const msgEl = pendingList.querySelector(`.draft-message[data-id="${id}"]`);
    readZonesFromDom();
    await api("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        broadcast_title: titleEl?.value || broadcastTitle.value,
        broadcast_message: msgEl?.value || broadcastMessage.value,
        safe_zones: zones,
      }),
    });
    const res = await api(`/api/alerts/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        custom_title: titleEl?.value || broadcastTitle.value,
        custom_message: msgEl?.value || broadcastMessage.value,
      }),
    });
    simulateStatus.textContent = "✓ Broadcast sent to LAN + webhook. See /alerts feed.";
    webhookStatus.textContent = "Check public alert page →";
    webhookStatus.className = "status-ok";
    selectedId = null;
    await loadPending();
    updatePreview();
  }

  async function reject(id) {
    await api(`/api/alerts/${id}/reject`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await loadPending();
  }

  document.getElementById("btn-simulate").onclick = async () => {
    clearError();
    simulateStatus.textContent = "Creating demo hazard…";
    try {
      const d = await api("/api/alerts/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "" }),
      });
      selectedId = d.pending_id || d.alert?.id;
      simulateStatus.textContent = "Alert queued — review and broadcast below.";
      await loadPending();
    } catch (e) {
      showError("Simulate failed: " + e.message);
      simulateStatus.textContent = "";
    }
  };

  document.getElementById("btn-save-message").onclick = async () => {
    await api("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        broadcast_title: broadcastTitle.value,
        broadcast_message: broadcastMessage.value,
      }),
    });
    simulateStatus.textContent = "Message template saved.";
    updatePreview();
  };

  document.getElementById("btn-add-zone").onclick = () => {
    zones.push({ name: "New shelter", lat: watchLocation.latitude || 12.335, lon: watchLocation.longitude || 79.784, note: "" });
    renderZones();
    updatePreview();
  };

  document.getElementById("btn-save-zones").onclick = async () => {
    readZonesFromDom();
    await api("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ safe_zones: zones }),
    });
    simulateStatus.textContent = "Safe zones saved.";
    updatePreview();
  };

  document.getElementById("btn-save-webhook").onclick = async () => {
    await api("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_url: webhookUrl.value.trim(), bearer_token: webhookToken.value.trim() }),
    });
    webhookToken.value = "";
    webhookStatus.textContent = "Webhook saved ✓";
    webhookStatus.className = "status-ok";
  };

  broadcastTitle.oninput = broadcastMessage.oninput = () => updatePreview();

  function connectWs() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/alerts`);
    ws.onmessage = () => loadPending();
    ws.onclose = () => setTimeout(connectWs, 3000);
  }

  loadSettings().catch((e) => showError("Failed to load settings: " + e.message));
  loadPending().catch((e) => showError("Failed to load pending: " + e.message));
  connectWs();
  setInterval(() => loadPending().catch(() => {}), 12000);
})();
