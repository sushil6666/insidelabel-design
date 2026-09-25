// lib.js — storage, API calls, image preparation and a tiny DOM builder.
//
// Two rules from DECISIONS.md shape this file:
//  - D-074: profile nicknames live only in this browser. The server gets
//    {ref, age, avoid}; text comes back with "{name}" and fill() swaps it here.
//  - Every string from the server (including words read off a label) goes into
//    the page as a text node, never as HTML.

// ------------------------------------------------------------------ storage
// localStorage can throw (private mode, blocked site data); the app must still work.
const mem = {};
export const store = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem("il." + key);
      return v === null ? (key in mem ? mem[key] : fallback) : JSON.parse(v);
    } catch { return key in mem ? mem[key] : fallback; }
  },
  set(key, value) {
    mem[key] = value;
    try { localStorage.setItem("il." + key, JSON.stringify(value)); } catch { /* memory only */ }
  },
};

export function deviceId() {
  let id = store.get("device", null);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : fallbackUuid();
    store.set("device", id);
  }
  return id;
}

function fallbackUuid() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// ------------------------------------------------------------------ profiles (D-074)
export const AGES = [
  { id: "toddler", label: "Toddler", sub: "1–3 years" },
  { id: "kid", label: "Child", sub: "4–11 years" },
  { id: "young", label: "Older child or teen", sub: "12 and up" },
];
export const MAX_PROFILES = 3;

export function profiles() {
  const list = store.get("profiles", []);
  if (!list.some(p => p.ref === "me")) list.unshift({ ref: "me", nickname: "You", age: "adult", avoid: [] });
  return list;
}
export function saveProfiles(list) { store.set("profiles", list); }

// What the server sees: no nickname, no consent record, nothing else.
export function profilesForServer() {
  return profiles().map(p => ({ ref: p.ref, age: p.age, avoid: p.avoid }));
}

export function profileByRef(ref) { return profiles().find(p => p.ref === ref); }

// Swap the "{name}" placeholder for the nickname kept on this device.
export function fill(text, ref) {
  if (text == null) return "";
  const p = ref ? profileByRef(ref) : null;
  return String(text).split("{name}").join(p ? p.nickname : "your child");
}

// ------------------------------------------------------------------ history
const HISTORY_MAX = 30;
export function history() { return store.get("history", []); }
export function addHistory(entry) {
  const list = [entry, ...history().filter(h => h.id !== entry.id)].slice(0, HISTORY_MAX);
  store.set("history", list);
}
export function historyItem(id) { return history().find(h => h.id === id); }

// ------------------------------------------------------------------ API
export class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.detail || body.error)) || `HTTP ${status}`);
    this.status = status; this.body = body || {};
  }
}

async function call(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError(0, { error: "offline", detail: "No connection." });
  }
  let body = null;
  try { body = await res.json(); } catch { /* empty body */ }
  // A refused scan (422) still carries a screen to render (D-037).
  if (!res.ok && !(res.status === 422 && body && body.screen)) throw new ApiError(res.status, body);
  return { status: res.status, body };
}

export async function scanRequest({ barcode, back, front, pairing }) {
  const fd = new FormData();
  fd.append("device_id", deviceId());
  fd.append("profiles", JSON.stringify(profilesForServer()));
  if (barcode) fd.append("barcode", barcode);
  if (back) fd.append("back", back, "back.jpg");
  if (front) fd.append("front", front, "front.jpg");
  if (front && pairing) fd.append("pairing_confirmed", "true");
  return call("/scan", { method: "POST", body: fd });
}

export async function allergenList() {
  try {
    const { body } = await call("/allergens");
    store.set("allergens", body.allergens);
    return body.allergens;
  } catch (e) {
    const cached = store.get("allergens", null);
    if (cached) return cached;
    throw e;
  }
}

export const compareRequest = payload =>
  call("/compare", { method: "POST", headers: { "Content-Type": "application/json" },
                     body: JSON.stringify(payload) });

export const reportRequest = payload =>
  call("/report", { method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ...payload, device_id: deviceId() }) });

export const updatesRequest = () =>
  call("/updates?device_id=" + encodeURIComponent(deviceId()));

// ------------------------------------------------------------------ barcodes
// GTIN check digit (EAN-8, UPC-A, EAN-13, GTIN-14): catches a mistyped digit
// before it becomes a "we haven't checked this pack" answer.
export function validGtin(code) {
  if (!/^(\d{8}|\d{12,14})$/.test(code)) return false;
  const d = [...code].map(Number);
  const check = d.pop();
  const sum = d.reverse().reduce((s, x, i) => s + x * (i % 2 === 0 ? 3 : 1), 0);
  return (10 - (sum % 10)) % 10 === check;
}

// ------------------------------------------------------------------ images
// Phone photos are 3–12 MB; the label only needs ~1600 px on the long edge.
// Smaller uploads matter on slow connections and stay under the 12 MB API limit.
export async function prepareImage(file, maxEdge = 1600) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxEdge / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close && bmp.close();
    const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.85));
    return blob || file;
  } catch {
    return file;            // e.g. HEIC the browser can't decode: the API accepts it as is
  }
}

// ------------------------------------------------------------------ DOM
// el("p", {class: "x", onclick: fn}, "text", childNode, [more])
export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const c of children) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) append(node, c);
    else node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}
