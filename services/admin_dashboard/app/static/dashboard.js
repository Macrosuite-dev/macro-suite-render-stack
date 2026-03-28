const FRIENDLY_INVENTORY_ERROR = "Unable to load inventory right now. Please refresh and try again.";
const FRIENDLY_AUDIT_ERROR = "Unable to load audit activity right now. Please refresh and try again.";
const FRIENDLY_DASHBOARD_ERROR = "Unable to load dashboard data right now. Please refresh and try again.";
const FRIENDLY_UPSTREAM_WAKE = "License API is waking up. Please wait a few seconds and try again.";
const FRIENDLY_UNEXPECTED_RESPONSE = "Unexpected dashboard response. Please refresh and try again.";

function looksLikeHtml(value) {
  const text = String(value || "").trim().toLowerCase();
  return text.startsWith("<!doctype html") || text.startsWith("<html") || text.includes("</html>");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function extractErrorMessage(status, payload, rawText) {
  const detail = payload && typeof payload === "object" ? (payload.detail ?? payload) : rawText;
  if (status === 502 || status === 503 || status === 504) {
    return FRIENDLY_UPSTREAM_WAKE;
  }
  if (typeof detail === "string") {
    if (looksLikeHtml(detail) || detail.length > 600) {
      return status >= 500 ? FRIENDLY_DASHBOARD_ERROR : FRIENDLY_UNEXPECTED_RESPONSE;
    }
    return detail;
  }
  if (detail && typeof detail.message === "string") {
    return detail.message;
  }
  return status >= 500 ? FRIENDLY_DASHBOARD_ERROR : `Request failed (${status})`;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  const isJson = contentType.includes("application/json");
  let payload = null;
  let rawText = "";
  if (isJson) {
    try {
      payload = await response.json();
    } catch {
      throw new Error(FRIENDLY_UNEXPECTED_RESPONSE);
    }
  } else {
    rawText = await response.text();
  }
  if (!response.ok) {
    throw new Error(extractErrorMessage(response.status, payload, rawText));
  }
  if (!isJson) {
    throw new Error(FRIENDLY_UNEXPECTED_RESPONSE);
  }
  return payload;
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
  const allowed = new Set(["active", "disabled", "banned", "expired", "unknown"]);
  const safe = allowed.has(text) ? text : "unknown";
  return `<span class="pill ${safe}">${escapeHtml(safe)}</span>`;
}

function actionButton(label, handler, licenseId, payload = {}) {
  return `<button class="action-btn" data-handler="${escapeHtml(handler)}" data-license-id="${escapeHtml(licenseId)}" data-payload='${escapeHtml(JSON.stringify(payload))}'>${escapeHtml(label)}</button>`;
}

function resetInventoryView(message) {
  document.getElementById("statTotal").textContent = "0";
  document.getElementById("statActive").textContent = "0";
  document.getElementById("statDisabled").textContent = "0";
  document.getElementById("statBanned").textContent = "0";
  document.getElementById("statExpired").textContent = "0";
  document.getElementById("licenseRows").innerHTML = `<tr><td colspan="6">${escapeHtml(message)}</td></tr>`;
}

function resetAuditView(message) {
  document.getElementById("auditRows").innerHTML = `<tr><td colspan="5">${escapeHtml(message)}</td></tr>`;
}

function renderInventory(payload) {
  if (!payload || !Array.isArray(payload.items) || !payload.stats || typeof payload.stats !== "object") {
    throw new Error(FRIENDLY_INVENTORY_ERROR);
  }
  document.getElementById("statTotal").textContent = String(payload.stats.total || 0);
  document.getElementById("statActive").textContent = String(payload.stats.active || 0);
  document.getElementById("statDisabled").textContent = String(payload.stats.disabled || 0);
  document.getElementById("statBanned").textContent = String(payload.stats.banned || 0);
  document.getElementById("statExpired").textContent = String(payload.stats.expired || 0);

  const rows = payload.items.map((item) => `
    <tr>
      <td><code>${escapeHtml(item.license_key || "-")}</code></td>
      <td>${escapeHtml(item.customer_name || "-")}</td>
      <td>${statusPill(item.computed_status)}</td>
      <td>${formatPacificDateTime(item.expires_at)}</td>
      <td>${escapeHtml(`${item.activation_count} / ${item.max_devices}`)}</td>
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
  if (!payload || !Array.isArray(payload.items)) {
    throw new Error(FRIENDLY_AUDIT_ERROR);
  }
  const rows = payload.items.map((item) => `
    <tr>
      <td>${formatPacificDateTime(item.created_at)}</td>
      <td>${escapeHtml(item.actor || "-")}</td>
      <td>${escapeHtml(item.action || "-")}</td>
      <td>${escapeHtml(item.license_key_suffix || "-")}</td>
      <td>${escapeHtml(item.detail || "-")}</td>
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
  loadInventory().catch((err) => {
    const message = !err?.message || err.message === FRIENDLY_DASHBOARD_ERROR ? FRIENDLY_INVENTORY_ERROR : err.message;
    resetInventoryView(message);
    document.getElementById("inventoryStatus").textContent = message;
  });
});

document.getElementById("searchInput").addEventListener("input", () => {
  loadInventory().catch((err) => {
    const message = !err?.message || err.message === FRIENDLY_DASHBOARD_ERROR ? FRIENDLY_INVENTORY_ERROR : err.message;
    resetInventoryView(message);
    document.getElementById("inventoryStatus").textContent = message;
  });
});

document.getElementById("statusFilter").addEventListener("change", () => {
  loadInventory().catch((err) => {
    const message = !err?.message || err.message === FRIENDLY_DASHBOARD_ERROR ? FRIENDLY_INVENTORY_ERROR : err.message;
    resetInventoryView(message);
    document.getElementById("inventoryStatus").textContent = message;
  });
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
    const message = !err?.message || err.message === FRIENDLY_DASHBOARD_ERROR ? FRIENDLY_INVENTORY_ERROR : err.message;
    resetInventoryView(message);
    document.getElementById("inventoryStatus").textContent = message;
  });
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await fetch("/session/logout", {method: "POST"});
  window.location.href = "/login";
});

loadInventory().catch((err) => {
  const message = !err?.message || err.message === FRIENDLY_DASHBOARD_ERROR ? FRIENDLY_INVENTORY_ERROR : err.message;
  resetInventoryView(message);
  document.getElementById("inventoryStatus").textContent = message;
});
loadAudit().catch((err) => {
  const message = !err?.message || err.message === FRIENDLY_DASHBOARD_ERROR ? FRIENDLY_AUDIT_ERROR : err.message;
  resetAuditView(message);
  document.getElementById("auditStatus").textContent = message;
});
