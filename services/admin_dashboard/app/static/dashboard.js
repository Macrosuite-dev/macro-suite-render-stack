async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload.detail || payload;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail.message === "string") {
        message = detail.message;
      } else {
        message = JSON.stringify(detail);
      }
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

function formatPacificDateTime(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZoneName: "short",
  }).format(parsed);
}

function statusPill(status) {
  const text = String(status || "unknown").toLowerCase();
  return `<span class="pill ${text}">${text}</span>`;
}

function actionButton(label, handler, licenseId, payload = {}) {
  return `<button class="action-btn" data-handler="${handler}" data-license-id="${licenseId}" data-payload='${JSON.stringify(payload)}'>${label}</button>`;
}

function renderInventory(payload) {
  document.getElementById("statTotal").textContent = payload.stats.total || 0;
  document.getElementById("statActive").textContent = payload.stats.active || 0;
  document.getElementById("statDisabled").textContent = payload.stats.disabled || 0;
  document.getElementById("statBanned").textContent = payload.stats.banned || 0;
  document.getElementById("statExpired").textContent = payload.stats.expired || 0;

  const rows = payload.items.map((item) => `
    <tr>
      <td><code>${item.license_key}</code></td>
      <td>${item.customer_name || "-"}</td>
      <td>${statusPill(item.computed_status)}</td>
      <td>${formatPacificDateTime(item.expires_at)}</td>
      <td>${item.activation_count} / ${item.max_devices}</td>
      <td>
        <div class="action-row">
          ${actionButton("Extend 30d", "extend", item.id, {extra_days: 30})}
          ${actionButton("Disable", "disable", item.id, {reason: "Disabled by admin"})}
          ${actionButton("Revoke", "ban", item.id, {reason: "Revoked by admin"})}
          ${actionButton("Restore", "restore", item.id, {})}
          ${actionButton("Reset Devices", "reset-device", item.id, {})}
        </div>
      </td>
    </tr>
  `).join("");
  document.getElementById("licenseRows").innerHTML = rows || '<tr><td colspan="6">No licenses found.</td></tr>';
}

function renderAudit(payload) {
  const rows = payload.items.map((item) => `
    <tr>
      <td>${formatPacificDateTime(item.created_at)}</td>
      <td>${item.actor}</td>
      <td>${item.action}</td>
      <td>${item.license_key_suffix || "-"}</td>
      <td>${item.detail || "-"}</td>
    </tr>
  `).join("");
  document.getElementById("auditRows").innerHTML = rows || '<tr><td colspan="5">No audit logs yet.</td></tr>';
}

async function loadInventory() {
  const search = document.getElementById("searchInput").value;
  const status = document.getElementById("statusFilter").value;
  const payload = await apiFetch(`/api/licenses?search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}`);
  renderInventory(payload);
  document.getElementById("inventoryStatus").textContent = `${payload.total} license(s) loaded.`;
}

async function loadAudit() {
  const payload = await apiFetch("/api/audit-logs?limit=100");
  renderAudit(payload);
  document.getElementById("auditStatus").textContent = `${payload.total} audit entries loaded.`;
}

async function generateLicense() {
  const payload = {
    customer_name: document.getElementById("customerName").value || null,
    customer_email: document.getElementById("customerEmail").value || null,
    duration_days: Number(document.getElementById("durationDays").value || 30),
    max_devices: Number(document.getElementById("maxDevices").value || 1),
    notes: document.getElementById("notes").value || null,
  };
  const result = await apiFetch("/api/licenses/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  document.getElementById("generatedKey").textContent = result.license_key;
  document.getElementById("generatedExpiry").textContent = formatPacificDateTime(result.expires_at);
  document.getElementById("generateStatus").textContent = "License generated.";
  await loadInventory();
  await loadAudit();
}

async function runLicenseAction(handler, licenseId, payload) {
  await apiFetch(`/api/licenses/${licenseId}/${handler}`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  await loadInventory();
  await loadAudit();
}

document.getElementById("refreshBtn").addEventListener("click", () => {
  loadInventory().catch((err) => { document.getElementById("inventoryStatus").textContent = err.message; });
});

document.getElementById("searchInput").addEventListener("input", () => {
  loadInventory().catch((err) => { document.getElementById("inventoryStatus").textContent = err.message; });
});

document.getElementById("statusFilter").addEventListener("change", () => {
  loadInventory().catch((err) => { document.getElementById("inventoryStatus").textContent = err.message; });
});

document.getElementById("generateBtn").addEventListener("click", () => {
  generateLicense().catch((err) => { document.getElementById("generateStatus").textContent = err.message; });
});

document.getElementById("licenseRows").addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.dataset.handler) {
    return;
  }
  const payload = JSON.parse(target.dataset.payload || "{}");
  runLicenseAction(target.dataset.handler, target.dataset.licenseId, payload).catch((err) => {
    document.getElementById("inventoryStatus").textContent = err.message;
  });
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await fetch("/session/logout", {method: "POST"});
  window.location.href = "/login";
});

loadInventory().catch((err) => { document.getElementById("inventoryStatus").textContent = err.message; });
loadAudit().catch((err) => { document.getElementById("auditStatus").textContent = err.message; });
