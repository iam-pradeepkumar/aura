(function () {
  const webhookUrl = document.getElementById("webhook-url");
  const webhookToken = document.getElementById("webhook-token");
  const webhookStatus = document.getElementById("webhook-status");
  const pendingList = document.getElementById("pending-list");
  const pendingCount = document.getElementById("pending-count");

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  async function loadSettings() {
    const r = await fetch("/api/alerts/settings");
    const d = await r.json();
    webhookUrl.value = d.webhook_url || "";
    webhookStatus.textContent = d.webhook_url ? "Webhook configured ✓" : "Set webhook URL to enable dispatch";
    webhookStatus.className = d.webhook_url ? "status-ok" : "";
    if (d.bearer_token_set) webhookToken.placeholder = "Token saved (enter new to replace)";
  }

  async function loadPending() {
    const r = await fetch("/api/alerts/pending");
    const d = await r.json();
    const items = d.pending || [];
    pendingCount.textContent = String(items.length);
    if (!items.length) {
      pendingList.innerHTML = "<p style='opacity:0.7'>No pending alerts.</p>";
      return;
    }
    pendingList.innerHTML = items.map((item) => {
      const a = item.alert || item;
      const id = item.id || a.id;
      return `
        <div class="alert-item pending" data-id="${esc(id)}">
          <strong>${esc(a.title)}</strong>
          <p style="margin:0.25rem 0;font-size:0.95rem">${esc(a.message || "")}</p>
          <div style="display:flex;gap:0.5rem;margin-top:0.75rem;flex-wrap:wrap">
            <button class="btn-sketch btn-approve" data-id="${esc(id)}" style="min-height:40px;padding:0.4rem 1rem;font-size:1rem">Approve &amp; broadcast</button>
            <button class="btn-sketch secondary btn-reject" data-id="${esc(id)}" style="min-height:40px;padding:0.4rem 1rem;font-size:1rem">Reject</button>
          </div>
        </div>`;
    }).join("");
    pendingList.querySelectorAll(".btn-approve").forEach((btn) => {
      btn.onclick = () => approve(btn.dataset.id);
    });
    pendingList.querySelectorAll(".btn-reject").forEach((btn) => {
      btn.onclick = () => reject(btn.dataset.id);
    });
  }

  async function approve(id) {
    await fetch(`/api/alerts/${id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await loadPending();
  }

  async function reject(id) {
    await fetch(`/api/alerts/${id}/reject`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await loadPending();
  }

  document.getElementById("btn-save-webhook").onclick = async () => {
    const r = await fetch("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_url: webhookUrl.value.trim(), bearer_token: webhookToken.value.trim() }),
    });
    const d = await r.json();
    webhookStatus.textContent = d.webhook_url ? "Saved ✓" : "Cleared";
    webhookToken.value = "";
    loadSettings();
  };

  document.getElementById("btn-test").onclick = async () => {
    await fetch("/api/alerts/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: "DM console test alert" }) });
    webhookStatus.textContent = "Test sent — check webhook endpoint";
    loadPending();
  };

  loadSettings();
  loadPending();
  setInterval(loadPending, 15000);
})();
