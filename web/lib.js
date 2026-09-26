// lib.js - storage, API calls, the flight recorder, image preparation and a
// tiny DOM builder.
//
// Three rules from DECISIONS.md shape this file:
//  - D-074: profile nicknames live only in this browser. The server gets
//    {ref, age, avoid}; text comes back with "{name}" and fill() swaps it here.
//  - Every string from the server (including words read off a label) goes into
//    the page as a text node, never as HTML.
//  - D-092: the app keeps a short trail of what happened (screens, API calls
//    with their request ids, errors) so "Report a problem" can send enough to
//    reproduce it. The trail holds no names, no query strings and no label text
//    beyond the headline the user was shown.

// Bump together with VERSION in sw.js: a report then says which shell was cached.
export const APP_VERSION = "web-9";

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
    id = uuid();
    store.set("device", id);
  }
  return id;
}

export function uuid() {
  return crypto.randomUUID ? crypto.randomUUID() : fallbackUuid();
}

function fallbackUuid() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// ------------------------------------------------------------------ profiles (D-074)
export const AGES = [
  { id: "toddler", label: "Toddler", sub: "1 to 3 years" },
  { id: "kid", label: "Child", sub: "4 to 11 years" },
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

// ------------------------------------------------------------------ flight recorder (D-092)
const TRAIL_MAX = 60;
const trail = (() => {
  try { return JSON.parse(sessionStorage.getItem("il.trail") || "[]"); } catch { return []; }
})();

export function record(type, data = {}) {
  trail.push({ ...data, t: Date.now(), type });           // `type` and `t` can't be overwritten
  if (trail.length > TRAIL_MAX) trail.splice(0, trail.length - TRAIL_MAX);
  try { sessionStorage.setItem("il.trail", JSON.stringify(trail)); } catch { /* memory only */ }
}

export function trailSnapshot() { return trail.map(e => ({ ...e })); }

// The most recent call that failed, or the most recent scan: what a report is about.
export function lastIncident() {
  const failed = [...trail].reverse().find(e => e.type === "api" && (e.status === 0 || e.status >= 400));
  const scanned = [...trail].reverse().find(e => e.type === "api" && e.path === "/scan");
  const hit = failed || scanned;
  return hit ? { request_id: hit.request_id, scan_id: hit.scan_id || null } : { request_id: null, scan_id: null };
}

export function clientInfo() {
  const c = navigator.connection || {};
  return {
    app_version: APP_VERSION,
    ua: navigator.userAgent,
    lang: navigator.language,
    screen: `${screen.width}x${screen.height}@${window.devicePixelRatio || 1}`,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    online: navigator.onLine,
    network: c.effectiveType || null,
    save_data: c.saveData || false,
    memory_gb: navigator.deviceMemory || null,
    standalone: window.matchMedia?.("(display-mode: standalone)").matches || false,
    barcode_detector: "BarcodeDetector" in window,
    service_worker: !!navigator.serviceWorker?.controller,
    profiles: profilesForServer(),          // ref, age band, avoid list: never a nickname
    scans_on_phone: history().length,
  };
}

// What the user was shown, without names: enough for tools/repro.py to compare.
function screenSummary(s) {
  if (!s) return null;
  return { state: s.state, headline: s.headline?.text, band: s.band?.code || null,
           people: (s.people || []).map(p => `${p.ref}:${p.status}`) };
}

// ------------------------------------------------------------------ API
export class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.detail || body.error)) || `HTTP ${status}`);
    this.status = status; this.body = body || {};
  }
}

async function call(path, opts = {}) {
  // Our own id, so a request that never reaches the server still has one in the trail.
  const rid = uuid();
  const t0 = performance.now();
  const entry = { method: opts.method || "GET", path: path.split("?")[0], request_id: rid };
  let res;
  try {
    res = await fetch(path, { ...opts, headers: { ...(opts.headers || {}), "X-Request-ID": rid } });
  } catch (e) {
    record("api", { ...entry, status: 0, ms: Math.round(performance.now() - t0), error: String(e?.name || "network") });
    throw new ApiError(0, { error: "offline", detail: "No connection.", request_id: rid });
  }
  let body = null;
  try { body = await res.json(); } catch { /* empty body */ }
  record("api", {
    ...entry, status: res.status, ms: Math.round(performance.now() - t0),
    request_id: res.headers.get("x-request-id") || rid,
    error: body?.error || null,
    scan_id: body?.scan_id || null,
    shown: path === "/scan" ? screenSummary(body?.screen) : undefined,
  });
  // A refused scan (422) still carries a screen to render (D-037).
  if (!res.ok && !(res.status === 422 && body && body.screen)) throw new ApiError(res.status, body);
  return { status: res.status, body };
}

export async function scanRequest({ barcode, barcodeSource, back, front, pairing }) {
  const fd = new FormData();
  fd.append("device_id", deviceId());
  fd.append("profiles", JSON.stringify(profilesForServer()));
  if (barcode) fd.append("barcode", barcode);
  if (barcode && barcodeSource) fd.append("barcode_source", barcodeSource);     // D-104: camera or photo
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

export const problemRequest = payload =>
  call("/problem", { method: "POST", headers: { "Content-Type": "application/json" },
                     body: JSON.stringify({ ...payload, device_id: deviceId(), app_version: APP_VERSION,
                                            client: clientInfo(), events: trailSnapshot() }) });

// D-070: the refused scans of a pack the app couldn't read, oldest first.
export const sendToUsRequest = scanIds =>
  call("/send-to-us", { method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ device_id: deviceId(), scan_ids: scanIds }) });

// D-104: the tick or cross on a photo as soon as it is picked. The server
// reads any barcode on it (never typed) and checks the file; no model call.
export async function checkPhotoRequest(role, blob) {
  const fd = new FormData();
  fd.append("device_id", deviceId());
  fd.append("role", role);
  fd.append("photo", blob, role + ".jpg");
  return call("/check-photo", { method: "POST", body: fd });
}

// D-102: the invite-only beta. The server says whether it needs a code and
// whether this phone has joined; the code comes from the tester's link.
export const accessRequest = () =>
  call("/access?device_id=" + encodeURIComponent(deviceId()));

export const joinRequest = code =>
  call("/join", { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ code, device_id: deviceId() }) });

export const feedbackRequest = ({ comment, rating, screen }) =>
  call("/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ comment, rating, screen, device_id: deviceId(),
                                             app_version: APP_VERSION }) });

export const updatesRequest = () =>
  call("/updates?device_id=" + encodeURIComponent(deviceId()));

// Barcodes are checked on the server (D-103), from the camera or a photo (D-104).

// ------------------------------------------------------------------ images
// Phone photos are 3-12 MB; the label only needs ~1600 px on the long edge.
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
    record("photo", { mime: file.type, kb_in: Math.round(file.size / 1024),
                      kb_out: blob ? Math.round(blob.size / 1024) : null,
                      px: `${canvas.width}x${canvas.height}` });
    return blob || file;
  } catch (e) {
    record("photo", { mime: file.type, kb_in: Math.round(file.size / 1024), resize_failed: String(e?.name) });
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
