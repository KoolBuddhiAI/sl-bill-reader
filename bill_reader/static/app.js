/* Shared helpers + the bills list, export and settings pages. The review page lives in review.js. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/** fetch wrapper: returns parsed JSON (or the Response for non-JSON bodies); throws Error with .status/.detail. */
async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    delete init.json;
  }
  const resp = await fetch(path, init);
  const type = resp.headers.get("content-type") || "";
  if (!resp.ok) {
    let detail = resp.statusText;
    if (type.includes("json")) detail = (await resp.json()).detail;
    const err = new Error(typeof detail === "string" ? detail : (detail?.problems || []).join("; ") || resp.statusText);
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  if (resp.status === 204) return null;
  return type.includes("json") ? resp.json() : resp;
}

function fmtAmount(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(String(v).replace(/,/g, ""));
  if (Number.isNaN(n)) return esc(v);
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString();
}

function statusBadge(status) {
  return `<span class="status ${esc(status)}">${esc(String(status).replace("_", " "))}</span>`;
}

function confBadge(conf, level) {
  if (conf === null || conf === undefined) return `<span class="badge level-none">–</span>`;
  return `<span class="badge level-${esc(level)}">${Math.round(conf * 100)}%</span>`;
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 3500);
}

function setMsg(el, text, kind = "") {
  el.textContent = text;
  el.className = "msg " + kind;
}

/** Download a fetch Response body as a file, using the server's filename. */
async function downloadResponse(resp, fallbackName) {
  const blob = await resp.blob();
  const cd = resp.headers.get("content-disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = m ? decodeURIComponent(m[1]) : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------------- bills list ---------------- */

function initBillsPage() {
  const body = $("#bills-body");
  const filter = $("#status-filter");
  const note = $("#refresh-note");
  let timer = null;

  try { filter.value = localStorage.getItem("billStatusFilter") || ""; } catch (e) { /* ignore */ }

  async function load() {
    clearTimeout(timer);
    const qs = filter.value ? `?status=${encodeURIComponent(filter.value)}` : "";
    let bills;
    try {
      bills = await api(`/api/bills${qs}`);
    } catch (e) {
      body.innerHTML = `<tr><td colspan="8" class="muted">Could not load bills: ${esc(e.message)}</td></tr>`;
      return;
    }
    if (!bills.length) {
      body.innerHTML = `<tr><td colspan="8" class="muted">No bills${filter.value ? " with this status" : " yet – upload one above"}.</td></tr>`;
    } else {
      body.innerHTML = bills.map((b) => `
        <tr data-id="${b.id}">
          <td><img class="thumb" loading="lazy" src="/api/bills/${b.id}/pages/0" alt="" onerror="this.style.visibility='hidden'"></td>
          <td><a href="/bills/${b.id}">${esc(b.supplier_name) || '<span class="muted">—</span>'}</a>
              ${b.error ? `<div class="small-text" style="color:var(--danger)">${esc(b.error)}</div>` : ""}</td>
          <td>${esc(b.bill_date)}</td>
          <td class="num">${fmtAmount(b.total)} <span class="muted">${esc(b.currency)}</span></td>
          <td>${confBadge(b.overall_confidence, b.confidence_level)}</td>
          <td>${statusBadge(b.status)}</td>
          <td class="muted">${esc(b.model_profile)}</td>
          <td class="muted small-text">${esc(b.filename)}</td>
        </tr>`).join("");
    }
    const busy = bills.some((b) => b.status === "processing");
    note.textContent = busy ? "Processing… refreshing every 3 s" : "";
    if (busy) timer = setTimeout(load, 3000);
  }

  body.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-id]");
    if (tr && !ev.target.closest("a")) location.href = `/bills/${tr.dataset.id}`;
  });
  filter.addEventListener("change", () => {
    try { localStorage.setItem("billStatusFilter", filter.value); } catch (e) { /* ignore */ }
    load();
  });

  // upload
  const zone = $("#dropzone");
  const input = $("#file-input");
  const results = $("#upload-results");

  async function upload(files) {
    if (!files.length) return;
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    results.innerHTML = `<li>Uploading ${files.length} file(s)…</li>`;
    try {
      const data = await api("/api/bills", { method: "POST", body: fd });
      results.innerHTML = data.results.map((r) => {
        if (r.error) return `<li class="err"><strong>${esc(r.filename)}</strong>: ${esc(r.error)}</li>`;
        if (r.duplicate_of) return `<li class="dup"><strong>${esc(r.filename)}</strong>: duplicate – already uploaded as <a href="/bills/${r.duplicate_of}">bill #${r.duplicate_of}</a></li>`;
        return `<li class="ok"><strong>${esc(r.filename)}</strong>: uploaded as <a href="/bills/${r.bill_id}">bill #${r.bill_id}</a></li>`;
      }).join("");
    } catch (e) {
      results.innerHTML = `<li class="err">Upload failed: ${esc(e.message)}</li>`;
    }
    load();
  }

  input.addEventListener("change", () => { upload([...input.files]); input.value = ""; });
  ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, (ev) => { ev.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, (ev) => { ev.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", (ev) => upload([...ev.dataTransfer.files]));
  zone.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); input.click(); } });
  // a file dropped outside the zone should not navigate away
  window.addEventListener("dragover", (ev) => ev.preventDefault());
  window.addEventListener("drop", (ev) => ev.preventDefault());

  load();
}

/* ---------------- export ---------------- */

function initExportPage() {
  const btn = $("#export-btn");
  const msg = $("#export-msg");

  async function load() {
    const [approved, batches] = await Promise.all([api("/api/bills?status=approved"), api("/api/exports")]);
    $("#approved-count").textContent = approved.length;
    btn.disabled = approved.length === 0;
    $("#batches-body").innerHTML = batches.length
      ? batches.map((b) => `<tr><td>#${b.id}</td><td>${esc(fmtTime(b.created_at))}</td><td class="num">${b.bill_count}</td>
          <td><a href="/api/exports/${b.id}" download>${esc(b.file)}</a></td></tr>`).join("")
      : `<tr><td colspan="4" class="muted">No exports yet.</td></tr>`;
  }

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    setMsg(msg, "Exporting…");
    try {
      const resp = await api("/api/exports", { method: "POST" });
      if (resp === null) {
        setMsg(msg, "Nothing to export – no approved bills.", "");
      } else {
        await downloadResponse(resp, "myob-export.zip");
        setMsg(msg, "Export created and downloaded.", "ok");
      }
    } catch (e) {
      setMsg(msg, `Export failed: ${e.message}`, "err");
    }
    await load();
  });

  load();
}

/* ---------------- settings ---------------- */

function initSettingsPage() {
  const extSel = $("#extraction-select");
  const catSel = $("#categorisation-select");
  const msg = $("#models-msg");

  function render(m) {
    const opts = (sel, current) => {
      sel.innerHTML = m.profiles.map((p) => `<option value="${esc(p.name)}">${esc(p.name)} (${esc(p.model)})</option>`).join("");
      sel.value = current;
    };
    opts(extSel, m.extraction);
    opts(catSel, m.categorisation);
    $("#fallback-chain").textContent = (m.fallback_chain || []).join(" → ") || "none";
    $("#profiles-body").innerHTML = m.profiles.map((p) => `
      <tr><td><strong>${esc(p.name)}</strong></td><td>${esc(p.provider)}</td><td>${esc(p.model)}</td><td>${esc(p.mode)}</td>
      <td class="${p.key.includes("✓") ? "" : "muted"}">${esc(p.key)}</td><td>${esc(p.role)}</td></tr>`).join("");
  }

  async function load() {
    try { render(await api("/api/models")); } catch (e) { setMsg(msg, e.message, "err"); }
  }

  $("#models-save").addEventListener("click", async () => {
    try {
      render(await api("/api/models/active", { method: "PUT", json: { extraction: extSel.value, categorisation: catSel.value } }));
      setMsg(msg, "Saved.", "ok");
    } catch (e) {
      setMsg(msg, e.message, "err");
    }
  });

  $("#accounts-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const file = $("#accounts-file").files[0];
    const amsg = $("#accounts-msg");
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file, file.name);
    try {
      const r = await api("/api/accounts/import", { method: "POST", body: fd });
      setMsg(amsg, `Imported ${r.imported} account(s).`, "ok");
    } catch (e) {
      setMsg(amsg, `Import failed: ${e.message}`, "err");
    }
  });

  api("/healthz").then((h) => {
    const el = $("#ocr-status");
    el.textContent = h.ocr ? `available (${h.ocr})` : "not installed – fallback unavailable (pip install .[surya])";
    el.className = h.ocr ? "" : "muted";
  }).catch(() => ($("#ocr-status").textContent = "unknown"));

  load();
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "bills") initBillsPage();
  else if (page === "export") initExportPage();
  else if (page === "settings") initSettingsPage();
});
