/* Review page: page image viewer with bbox overlay + editable bill form. Uses helpers from app.js. */
"use strict";

const FIELDS = [
  { name: "supplier_name", label: "Supplier name", wide: true },
  { name: "supplier_address", label: "Supplier address", wide: true },
  { name: "supplier_tax_id", label: "Supplier tax ID (TIN / VAT no.)" },
  { name: "bill_number", label: "Bill / invoice no." },
  { name: "bill_date", label: "Bill date", placeholder: "YYYY-MM-DD" },
  { name: "currency", label: "Currency", placeholder: "LKR" },
  { name: "subtotal", label: "Subtotal", amount: true },
  { name: "discount", label: "Discount", amount: true },
  { name: "vat_amount", label: "VAT amount", amount: true },
  { name: "vat_rate", label: "VAT rate (%)", amount: true },
  { name: "sscl_amount", label: "SSCL amount", amount: true },
  { name: "total", label: "Total", amount: true },
  { name: "payment_method", label: "Payment method" },
];
const REQUIRED = new Set(["supplier_name", "bill_date", "total"]);
const EDITABLE = new Set(["needs_review", "approved"]);

const billId = Number($("#viewer-pane").dataset.billId);
let bill = null;
let itemsDirty = false;
let selectedAccount = null; // {code, name}
let pollTimer = null;

/* ================= viewer ================= */

const viewer = $("#viewer");
const stage = $("#stage");
const img = $("#page-img");
const rect = $("#highlight");
const view = { page: -1, scale: 1, tx: 0, ty: 0, w: 0, h: 0 };
let pendingBox = null;
let hoverName = null;
let focusName = null;

function applyTransform() {
  stage.style.transform = `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})`;
  $("#zoom-level").textContent = `${Math.round(view.scale * 100)}%`;
}

function fit() {
  if (!view.w) return;
  const vw = viewer.clientWidth, vh = viewer.clientHeight;
  view.scale = Math.min(vw / view.w, vh / view.h) * 0.97;
  view.tx = (vw - view.w * view.scale) / 2;
  view.ty = (vh - view.h * view.scale) / 2;
  applyTransform();
}

function zoomAt(factor, cx = viewer.clientWidth / 2, cy = viewer.clientHeight / 2) {
  const s = Math.min(8, Math.max(0.1, view.scale * factor));
  view.tx = cx - ((cx - view.tx) * s) / view.scale;
  view.ty = cy - ((cy - view.ty) * s) / view.scale;
  view.scale = s;
  applyTransform();
}

function showPage(n) {
  if (n === view.page) return;
  view.page = n;
  img.src = `/api/bills/${billId}/pages/${n}`;
  document.querySelectorAll("#page-tabs button").forEach((b) => b.classList.toggle("active", Number(b.dataset.page) === n));
  rect.setAttribute("visibility", "hidden");
}

img.addEventListener("load", () => {
  view.w = img.naturalWidth;
  view.h = img.naturalHeight;
  stage.style.width = `${view.w}px`;
  stage.style.height = `${view.h}px`;
  fit();
  if (pendingBox) { const b = pendingBox; pendingBox = null; drawBox(b); }
});

function renderPageTabs(count) {
  const tabs = $("#page-tabs");
  tabs.innerHTML = count > 1
    ? Array.from({ length: count }, (_, i) => `<button type="button" class="btn small" data-page="${i}">Page ${i + 1}</button>`).join("")
    : "";
  tabs.querySelectorAll("button").forEach((b) => {
    b.classList.toggle("active", Number(b.dataset.page) === view.page);
    b.addEventListener("click", () => showPage(Number(b.dataset.page)));
  });
}

/** box = {bbox:[x0,y0,x1,y1] normalised, page, level} */
function drawBox(box) {
  if (!box) { rect.setAttribute("visibility", "hidden"); return; }
  if (box.page !== view.page || !view.w) { pendingBox = box; showPage(box.page); return; }
  const [x0, y0, x1, y1] = box.bbox;
  rect.setAttribute("x", x0);
  rect.setAttribute("y", y0);
  rect.setAttribute("width", Math.max(0, x1 - x0));
  rect.setAttribute("height", Math.max(0, y1 - y0));
  rect.setAttribute("class", `highlight level-${box.level}`);
  rect.setAttribute("visibility", "visible");
  // pan so the box is visible
  const bx0 = view.tx + x0 * view.w * view.scale, bx1 = view.tx + x1 * view.w * view.scale;
  const by0 = view.ty + y0 * view.h * view.scale, by1 = view.ty + y1 * view.h * view.scale;
  const vw = viewer.clientWidth, vh = viewer.clientHeight;
  if (bx0 < 0 || by0 < 0 || bx1 > vw || by1 > vh) {
    view.tx += vw / 2 - (bx0 + bx1) / 2;
    view.ty += vh / 2 - (by0 + by1) / 2;
    applyTransform();
  }
}

function boxFor(name) {
  const f = name && bill?.fields?.[name];
  if (!f || !Array.isArray(f.bbox) || f.bbox.length !== 4) return null;
  return { bbox: f.bbox, page: f.page || 0, level: f.level };
}

function updateBox() {
  drawBox(boxFor(hoverName) || boxFor(focusName));
}

// drag to pan
let drag = null;
viewer.addEventListener("pointerdown", (ev) => {
  drag = { x: ev.clientX, y: ev.clientY, tx: view.tx, ty: view.ty };
  viewer.setPointerCapture(ev.pointerId);
  viewer.classList.add("dragging");
});
viewer.addEventListener("pointermove", (ev) => {
  if (!drag) return;
  view.tx = drag.tx + ev.clientX - drag.x;
  view.ty = drag.ty + ev.clientY - drag.y;
  applyTransform();
});
const endDrag = () => { drag = null; viewer.classList.remove("dragging"); };
viewer.addEventListener("pointerup", endDrag);
viewer.addEventListener("pointercancel", endDrag);
// scroll pans, ctrl/cmd + scroll zooms
viewer.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  if (ev.ctrlKey || ev.metaKey) {
    const r = viewer.getBoundingClientRect();
    zoomAt(ev.deltaY < 0 ? 1.15 : 1 / 1.15, ev.clientX - r.left, ev.clientY - r.top);
  } else {
    view.tx -= ev.deltaX;
    view.ty -= ev.deltaY;
    applyTransform();
  }
}, { passive: false });
$("#zoom-in").addEventListener("click", () => zoomAt(1.25));
$("#zoom-out").addEventListener("click", () => zoomAt(1 / 1.25));
$("#zoom-fit").addEventListener("click", fit);
window.addEventListener("resize", fit);

/* ================= form ================= */

function renderFields() {
  const html = FIELDS.map((meta) => {
    const f = bill.fields[meta.name] || {};
    const empty = !REQUIRED.has(meta.name) && !f.value && !f.confidence;
    const level = empty && !f.confirmed ? "none" : f.level || "none";
    const conf = empty && !f.confirmed ? "" : typeof f.confidence === "number" && !f.confirmed ? `${Math.round(f.confidence * 100)}%` : f.confirmed ? "confirmed" : "";
    const req = REQUIRED.has(meta.name);
    const needsConfirm = req && (level === "medium" || level === "low");
    const extracted = f.extracted_value && f.extracted_value !== f.value
      ? `<span class="extracted">extracted: ${esc(f.extracted_value)}</span>` : "";
    const hasBox = boxFor(meta.name) ? " has-box" : "";
    return `
      <div class="field fld level-${level}${meta.wide ? " wide" : ""}${hasBox}" data-name="${meta.name}">
        <div class="field-head">
          <label for="f-${meta.name}">${esc(meta.label)}${req ? " *" : ""}</label>
          <span class="conf">${conf}</span>
        </div>
        <input type="text" id="f-${meta.name}" name="${meta.name}" class="${meta.amount ? "amount" : ""}"
               value="${esc(f.value ?? "")}" placeholder="${esc(meta.placeholder || "")}">
        ${needsConfirm ? `<label class="confirm"><input type="checkbox" class="confirm-box" value="${meta.name}"> confirm value</label>` : ""}
        ${extracted}
      </div>`;
  }).join("");
  const box = $("#fields");
  box.innerHTML = html;
  box.querySelectorAll(".fld").forEach((wrap) => {
    const name = wrap.dataset.name;
    const input = wrap.querySelector("input[type=text]");
    wrap.addEventListener("mouseenter", () => { hoverName = name; updateBox(); });
    wrap.addEventListener("mouseleave", () => { hoverName = null; updateBox(); });
    input.addEventListener("focus", () => { focusName = name; updateBox(); });
    input.addEventListener("blur", () => { if (focusName === name) focusName = null; updateBox(); });
    input.addEventListener("input", () => {
      if (input.value.trim() !== (bill.fields[name]?.value ?? "")) {
        wrap.className = wrap.className.replace(/level-\w+/, "level-confirmed");
      }
      if (name === "currency") updateRateVisibility();
    });
  });
}

function itemRow(item = {}) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="text" data-k="description" value="${esc(item.description ?? "")}">
        ${item.description_original ? `<div class="original" lang="si">${esc(item.description_original)}</div>` : ""}</td>
    <td class="num"><input type="text" data-k="qty" value="${esc(item.qty ?? "")}"></td>
    <td class="num"><input type="text" data-k="unit_price" value="${esc(item.unit_price ?? "")}"></td>
    <td class="num"><input type="text" data-k="amount" value="${esc(item.amount ?? "")}"></td>
    <td><button type="button" class="remove" title="Remove line">×</button></td>`;
  tr.dataset.original = item.description_original ?? "";
  tr.querySelector(".remove").addEventListener("click", () => { tr.remove(); itemsDirty = true; });
  tr.querySelectorAll("input").forEach((i) => i.addEventListener("input", () => (itemsDirty = true)));
  return tr;
}

function renderItems() {
  const body = $("#items-body");
  body.innerHTML = "";
  bill.line_items.forEach((it) => body.appendChild(itemRow(it)));
  itemsDirty = false;
}

function collectItems() {
  return [...document.querySelectorAll("#items-body tr")].map((tr) => {
    const item = { description_original: tr.dataset.original || null };
    tr.querySelectorAll("input[data-k]").forEach((i) => (item[i.dataset.k] = i.value.trim() || null));
    return item;
  }).filter((it) => it.description || it.qty || it.unit_price || it.amount);
}

function currentCurrency() {
  return ($("#f-currency")?.value || bill.currency || "").trim().toUpperCase();
}

function voucherType() {
  return document.querySelector("input[name=voucher_type]:checked").value;
}

function updateRateVisibility() {
  const cur = currentCurrency();
  const needs = Boolean(cur) && cur !== bill.home_currency;
  $("#rate-wrap").hidden = !needs;
  $("#rate-label").textContent = `Exchange rate (1 ${cur || "?"} = ? ${bill.home_currency}) *`;
}

function updatePayingVisibility() {
  $("#paying-wrap").hidden = voucherType() !== "spend_money";
}
document.querySelectorAll("input[name=voucher_type]").forEach((r) => r.addEventListener("change", updatePayingVisibility));
$("#add-item").addEventListener("click", () => {
  const tr = itemRow();
  $("#items-body").appendChild(tr);
  itemsDirty = true;
  tr.querySelector("input").focus();
});

/* ---------- account picker ---------- */

const accInput = $("#account-input");
const accList = $("#account-results");
let accResults = [];
let accActive = -1;
let accTimer = null;

function accountLabel(a) { return a ? `${a.code} — ${a.name || ""}` : ""; }

function renderAccountList() {
  accList.innerHTML = accResults.length
    ? accResults.map((a, i) => `<li data-i="${i}" class="${i === accActive ? "active" : ""}"><span class="code">${esc(a.code)}</span>
        <span>${esc(a.name)}</span><span class="type">${esc(a.type)}</span></li>`).join("")
    : `<li class="muted">No matching accounts</li>`;
  accList.hidden = false;
}

async function searchAccounts() {
  const q = accInput.value === accountLabel(selectedAccount) ? "" : accInput.value.trim();
  try {
    accResults = (await api(`/api/accounts?q=${encodeURIComponent(q)}`)).slice(0, 50);
  } catch (e) {
    accResults = [];
  }
  accActive = accResults.length ? 0 : -1;
  renderAccountList();
}

function pickAccount(a) {
  selectedAccount = { code: a.code, name: a.name };
  accInput.value = accountLabel(selectedAccount);
  accList.hidden = true;
  $("#account-wrap").className = "field account-field level-confirmed";
}

accInput.addEventListener("focus", () => { accInput.select(); searchAccounts(); });
accInput.addEventListener("input", () => { clearTimeout(accTimer); accTimer = setTimeout(searchAccounts, 150); });
accInput.addEventListener("keydown", (ev) => {
  if (accList.hidden) return;
  if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
    ev.preventDefault();
    accActive = Math.max(0, Math.min(accResults.length - 1, accActive + (ev.key === "ArrowDown" ? 1 : -1)));
    renderAccountList();
    accList.querySelector("li.active")?.scrollIntoView({ block: "nearest" });
  } else if (ev.key === "Enter") {
    ev.preventDefault();
    if (accResults[accActive]) pickAccount(accResults[accActive]);
  } else if (ev.key === "Escape") {
    accList.hidden = true;
  }
});
accList.addEventListener("mousedown", (ev) => {
  const li = ev.target.closest("li[data-i]");
  if (li) { ev.preventDefault(); pickAccount(accResults[Number(li.dataset.i)]); }
});
accInput.addEventListener("blur", () => {
  accList.hidden = true;
  accInput.value = accountLabel(selectedAccount);
});

/* ---------- render whole bill ---------- */

function renderBanners() {
  const warn = $("#warnings-banner");
  const warnings = bill.warnings || [];
  warn.hidden = !warnings.length;
  warn.innerHTML = warnings.length ? `<strong>Check these:</strong><ul>${warnings.map((w) => `<li>${esc(typeof w === "string" ? w : JSON.stringify(w))}</li>`).join("")}</ul>` : "";
  const err = $("#error-banner");
  err.hidden = !bill.error;
  err.textContent = bill.error ? `Extraction failed: ${bill.error}` : "";
  $("#processing-banner").hidden = bill.status !== "processing";

  const x = bill.extraction || {};
  if (x.profile || x.extractor) {
    const bits = [x.model, x.mode, x.latency_ms != null ? `${x.latency_ms} ms` : null].filter(Boolean).join(", ");
    let text = `Extracted by ${x.profile || "?"}${bits ? ` (${bits})` : ""}`;
    if (x.tokens_in || x.tokens_out) text += ` · ${x.tokens_in || 0} in / ${x.tokens_out || 0} out tokens`;
    if (x.extractor && !x.extractor.startsWith(x.profile || "\u0000")) text += ` · Extracted with: ${x.extractor}`;
    if (bill.doc_type) text += ` · ${bill.doc_type.replace(/_/g, " ")}`;
    if (bill.languages?.length) text += ` · ${bill.languages.join(", ")}`;
    $("#extraction-info").textContent = text;
  } else {
    $("#extraction-info").textContent = "";
  }
}

function renderCoding() {
  selectedAccount = bill.account_code ? { code: bill.account_code, name: bill.account_name } : null;
  accInput.value = accountLabel(selectedAccount);
  $("#account-wrap").className = `field account-field level-${bill.account_level || "none"}`;
  const sugg = $("#account-suggestion");
  if (bill.account_code) {
    const conf = bill.account_confidence != null ? `${Math.round(bill.account_confidence * 100)}%` : "";
    sugg.innerHTML = `Suggested <strong>${esc(bill.account_code)}</strong> ${esc(bill.account_name || "")}
      ${conf ? confBadge(bill.account_confidence, bill.account_level) : ""}${bill.account_reason ? ` · ${esc(bill.account_reason)}` : ""}`;
  } else {
    sugg.textContent = "No account suggested – pick one.";
  }
  const tax = $("#tax-code");
  if (bill.tax_code && ![...tax.options].some((o) => o.value === bill.tax_code)) {
    tax.add(new Option(bill.tax_code, bill.tax_code));
  }
  tax.value = bill.tax_code || "N-T";
  document.querySelector(`input[name=voucher_type][value=${bill.voucher_type || "spend_money"}]`).checked = true;
  $("#paying-account").value = bill.paying_account || "";
  $("#exchange-rate").value = bill.exchange_rate || "";
  updatePayingVisibility();
  updateRateVisibility();
}

function describeAudit(a) {
  const d = a.details || {};
  if (a.action === "corrected" && Array.isArray(d.changes)) {
    return d.changes.map((c) => c.field === "line_items"
      ? `line items replaced (${c.new})`
      : `${c.field}: ${c.old ?? "∅"} → ${c.new ?? "∅"}`).join("; ");
  }
  return Object.entries(d).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("; ");
}

function renderAudit() {
  $("#audit-list").innerHTML = (bill.audit || []).slice().reverse().map((a) =>
    `<li><span class="ts">${esc(fmtTime(a.ts))}</span> <strong>${esc(a.action)}</strong> ${esc(describeAudit(a))}</li>`).join("")
    || `<li class="muted">No events.</li>`;
}

function render() {
  $("#status-badge").outerHTML = `<span id="status-badge" class="status ${esc(bill.status)}">${esc(bill.status.replace("_", " "))}</span>`;
  renderBanners();
  renderFields();
  renderItems();
  renderCoding();
  renderAudit();
  renderPageTabs(bill.page_count || 1);
  if (view.page < 0) showPage(0);

  const editable = EDITABLE.has(bill.status);
  $("#form-fields").disabled = !editable;
  $("#save-btn").disabled = !editable;
  $("#approve-btn").disabled = !(bill.status === "needs_review" || bill.status === "approved");
  $("#reextract-btn").disabled = bill.status === "processing" || bill.status === "exported";
  updateBox();
}

async function loadBill() {
  clearTimeout(pollTimer);
  try {
    bill = await api(`/api/bills/${billId}`);
  } catch (e) {
    $("#error-banner").hidden = false;
    $("#error-banner").textContent = `Could not load bill: ${e.message}`;
    return;
  }
  render();
  if (bill.status === "processing") pollTimer = setTimeout(loadBill, 2000);
}

/* ---------- actions ---------- */

function collectPatch() {
  const patch = { fields: {}, confirmed: [] };
  for (const meta of FIELDS) {
    const v = $(`#f-${meta.name}`).value.trim();
    if (v !== (bill.fields[meta.name]?.value ?? "")) patch.fields[meta.name] = v || null;
  }
  document.querySelectorAll(".confirm-box:checked").forEach((c) => patch.confirmed.push(c.value));
  if (itemsDirty) patch.line_items = collectItems();
  if (selectedAccount && selectedAccount.code !== bill.account_code) patch.account_code = selectedAccount.code;
  const tax = $("#tax-code").value;
  if (tax !== bill.tax_code) patch.tax_code = tax;
  const vt = voucherType();
  if (vt !== bill.voucher_type) patch.voucher_type = vt;
  const pay = $("#paying-account").value.trim();
  if (vt === "spend_money" && pay && pay !== bill.paying_account) patch.paying_account = pay;
  const rate = $("#exchange-rate").value.trim().replace(/,/g, "");
  if (!$("#rate-wrap").hidden && rate && rate !== bill.exchange_rate) patch.exchange_rate = rate;
  return patch;
}

function showProblems(problems) {
  const el = $("#problems-banner");
  el.hidden = !problems?.length;
  el.innerHTML = problems?.length ? `<strong>Cannot approve yet:</strong><ul>${problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
  if (problems?.length) el.scrollIntoView({ block: "nearest" });
}

const actionMsg = $("#action-msg");

$("#save-btn").addEventListener("click", async () => {
  showProblems(null);
  try {
    bill = await api(`/api/bills/${billId}`, { method: "PATCH", json: collectPatch() });
    render();
    setMsg(actionMsg, "Saved.", "ok");
  } catch (e) {
    setMsg(actionMsg, `Save failed: ${e.message}`, "err");
  }
});

$("#approve-btn").addEventListener("click", async () => {
  showProblems(null);
  try {
    bill = await api(`/api/bills/${billId}/approve`, { method: "POST", json: collectPatch() });
    render();
    setMsg(actionMsg, "Approved – ready to export.", "ok");
  } catch (e) {
    if (e.status === 422 && e.detail?.problems) {
      showProblems(e.detail.problems);
      setMsg(actionMsg, "Your edits were saved, but the bill is not approved yet.", "err");
      const problems = e.detail.problems;
      await loadBill(); // edits are kept server-side
      showProblems(problems);
    } else {
      setMsg(actionMsg, `Approve failed: ${e.message}`, "err");
    }
  }
});

$("#reextract-btn").addEventListener("click", async () => {
  const profile = $("#reextract-profile").value;
  if (!confirm(`Re-extract this bill with ${profile || "the active profile"}? Unsaved edits are lost.`)) return;
  try {
    await api(`/api/bills/${billId}/reextract?profile=${encodeURIComponent(profile)}`, { method: "POST" });
    setMsg(actionMsg, `Re-extracting with ${profile}…`, "");
    view.page = -1;
    await loadBill();
  } catch (e) {
    setMsg(actionMsg, `Re-extract failed: ${e.message}`, "err");
  }
});

$("#delete-btn").addEventListener("click", async () => {
  if (!confirm("Delete this bill? This cannot be undone.")) return;
  try {
    await api(`/api/bills/${billId}`, { method: "DELETE" });
    location.href = "/";
  } catch (e) {
    setMsg(actionMsg, `Delete failed: ${e.message}`, "err");
  }
});

async function loadProfiles() {
  try {
    const m = await api("/api/models");
    const sel = $("#reextract-profile");
    sel.innerHTML = m.profiles.map((p) => `<option value="${esc(p.name)}">${esc(p.name)} (${esc(p.mode)})</option>`).join("");
    sel.value = m.extraction;
  } catch (e) { /* the button still works with the active profile */ }
}

document.addEventListener("DOMContentLoaded", () => {
  loadProfiles();
  loadBill();
});
