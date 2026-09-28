// app.js - InsideLabel PWA: views and navigation.
//
// The result screen is rendered from the `screen` block that /scan returns
// (src/insidelabel/lenses/screen.py). This file adds layout and buttons, not
// judgements: no score is shown (D-064), no band is renamed here (D-063), and
// every sentence about the pack comes from the server, where the wording lint
// checks it (D-042). Text in this file is linted too (tests/test_web.py).

import {
  AGES, APP_VERSION, MAX_PROFILES, ApiError, addHistory, allergenList, clientInfo, compareRequest,
  deviceId, el, fill, history, historyItem, lastIncident, prepareImage, problemRequest, profileByRef,
  profiles, record, reportRequest, saveProfiles, scanRequest, sendToUsRequest, store, trailSnapshot,
  accessRequest, agreeRequest, checkPhotoRequest, feedbackRequest, joinRequest, termsRequest,
  updatesRequest,
} from "./lib.js";
import { barcodeSupported, startScanner } from "./camera.js";

const main = document.getElementById("main");
let stopCamera = null;
let navSeq = 0;               // async views check this so a late result can't replace a newer page
// The scan in progress: barcode (if read), photos, and how many times it was refused
// (with the refused scans' ids, for "Send it to us", D-070).
// frontWanted: offer the front photo (D-100); off for a re-check of a pack whose front is on file.
// acceptUnconfirmed: "use this one anyway" after a request for a clearer photo (D-118).
// parts: the ingredient list's 2nd and 3rd photos, when it doesn't fit one (D-119).
let pending = { barcode: null, barcodeSource: null, back: null, front: null, backSource: null,
                frontSource: null, pairing: false, attempts: 0, refused: [], frontWanted: true,
                acceptUnconfirmed: false, parts: [], partSources: [] };

// ------------------------------------------------------------------ navigation
const routes = {
  "": home, welcome, household, person, scan, photo, front, result, report, compare, problem, send,
  join, agree, feedback,
};

// Setting the hash it already has fires no hashchange, so the page wouldn't
// change (e.g. "Skip for now" on a welcome shown at #/ after joining).
function go(path) {
  const hash = "#/" + path;
  if (location.hash === hash) route();
  else location.hash = hash;
}

function route() {
  if (stopCamera) { stopCamera(); stopCamera = null; }
  const [name, arg] = location.hash.replace(/^#\/?/, "").split("/");
  // D-092: screens in the trail. `arg` is a scan id or a profile ref, never a name.
  record("route", { to: name || "home", arg: arg || undefined });
  if (name !== "feedback") store.set("lastScreen", name || "home");     // where feedback was sent from
  // D-102: an invite-only server lets a phone in once it has joined with a code.
  // D-105: then "Before you start": the rules are agreed before anything else.
  if (!["join", "agree", "problem"].includes(name)) {
    const seq = ++navSeq;
    return checkAccess().then(a => {
      if (seq !== navSeq) return;
      if (!a.joined) return show(join());
      if (a.needAgree) return show(agree());
      routeAfterJoin(name, arg);
    });
  }
  routeAfterJoin(name, arg);
}

function routeAfterJoin(name, arg) {
  if (!store.get("welcomed", false) && !["welcome", "household", "person", "join", "agree"].includes(name)) {
    return show(welcome());
  }
  const seq = ++navSeq;
  const view = routes[name] || home;
  const out = view(arg && decodeURIComponent(arg));
  Promise.resolve(out).then(node => { if (seq === navSeq) show(node); });
  updateNav();
}

function show(node) {
  if (!node) return;
  main.replaceChildren(node);
  window.scrollTo(0, 0);
  const h = main.querySelector("h1, h2");
  if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
}

function updateNav() {
  const n = store.get("compare", []).length;
  document.getElementById("nav-compare").textContent = n ? `Compare (${n})` : "Compare";
}

function productName(product) {
  const p = product || {};
  return [p.brand, p.name, p.variant].filter(Boolean).join(" ") || "Unnamed pack";
}

function button(label, onclick, cls = "") {
  return el("button", { type: "button", class: "btn " + cls, onclick }, label);
}

// ------------------------------------------------------------------ invite-only beta (D-102)
// Asked once per session; a phone that has joined remembers it. If the server
// says otherwise later (403 invite_required), the flag is cleared and the
// join screen comes back.
let accessChecked = null;
function checkAccess() {
  if (!accessChecked) {
    accessChecked = accessRequest().then(({ body }) => {
      const joined = !body.invite_only || body.joined;
      if (joined) store.set("joined", true);
      store.set("termsVersion", body.terms_version);
      // D-105: agreed on the server, or (a server without a database) on this phone.
      const needAgree = !body.agreed && store.get("agreed", null) !== body.terms_version;
      return { joined, needAgree };
    }).catch(() => ({                // offline: open the app; the server still checks every scan
      joined: store.get("joined", true),
      needAgree: !store.get("agreed", null),
    }));
  }
  return accessChecked;
}

// A 403 from the server means this phone isn't (or is no longer) let in: no
// invite (D-102), or the rules not agreed, e.g. after they changed (D-105).
// Returns the screen to show, or null.
function accessProblem(e) {
  if (!(e instanceof ApiError)) return null;
  if (e.body?.error === "invite_required") {
    store.set("joined", false);
    accessChecked = null;
    return "join";
  }
  if (e.body?.error === "terms_required") {
    store.set("agreed", null);
    accessChecked = null;
    return "agree";
  }
  return null;
}

function agree() {
  const view = el("section", { class: "stack" }, el("p", { class: "muted" }, "Loading…"));
  termsRequest().then(({ body: t }) => {
    const box = el("input", { type: "checkbox", id: "agree" });
    const err = el("p", { class: "error", role: "alert" });
    const go_ = el("button", { type: "button", class: "btn primary", disabled: true }, t.button);
    box.addEventListener("change", () => { go_.disabled = !box.checked; });
    go_.addEventListener("click", async () => {
      go_.disabled = true;
      try {
        await agreeRequest(t.version);
      } catch (ex) {
        if (ex.body?.error === "terms_changed") { accessChecked = null; return show(agree()); }
        // A server without a database can't record it; the phone keeps it (it doesn't gate).
        if (ex.body?.error !== "storage_unavailable") {
          go_.disabled = false;
          err.textContent = ex.status === 0 ? "No connection. Try again when you're online." : apiMessage(ex);
          return;
        }
      }
      store.set("agreed", t.version);
      record("agreed", { version: t.version });
      accessChecked = Promise.resolve({ joined: true, needAgree: false });
      go("");
    });
    view.replaceChildren(
      el("h1", {}, t.title),
      el("p", { class: "lead" }, t.intro),
      el("ol", { class: "rules" }, t.points.map(p => el("li", {}, p))),
      el("label", { class: "choice", for: "agree" }, box, " " + t.agree_label),
      err, go_);
  }).catch(e => view.replaceChildren(apiErrorView(e, () => show(agree()))));
  return view;
}

function join(code) {
  const input = el("input", { id: "invite", autocomplete: "off", autocapitalize: "characters",
                              maxlength: "12", placeholder: "e.g. K7PM4QXT", value: code || "" });
  const err = el("p", { class: "error", role: "alert" });
  const go_ = el("button", { type: "submit", class: "btn primary" }, "Join the beta");
  const form = el("form", { class: "stack" },
    el("h1", {}, "Welcome to the InsideLabel beta"),
    el("p", { class: "lead" }, "InsideLabel is being tried by a small group first. Your invite has a code; " +
                               "the link in your message fills it in for you."),
    el("label", { for: "invite" }, "Invite code"), input, err, go_);
  const submit = async () => {
    const typed = input.value.trim();
    if (!typed) { err.textContent = "Type the code from your invite."; return; }
    go_.disabled = true;
    try {
      await joinRequest(typed);
      store.set("joined", true);
      accessChecked = null;                  // ask again: next comes "Before you start" (D-105)
      record("joined", {});
      go("");
    } catch (ex) {
      go_.disabled = false;
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online."
        : (ex.body?.detail || "That didn't work. Check the code and try again.");
    }
  };
  form.addEventListener("submit", e => { e.preventDefault(); submit(); });
  if (code) setTimeout(submit, 0);          // opened from the invite link
  return form;
}

function feedback() {
  const from = store.get("lastScreen", "home");
  const comment = el("textarea", { id: "fb", maxlength: "4000", rows: "5", required: true });
  const err = el("p", { class: "error", role: "alert" });
  let rating = null;
  const stars = el("div", { class: "row rating", role: "radiogroup", "aria-label": "How useful is it so far?" },
    [1, 2, 3, 4, 5].map(n => {
      const r = el("input", { type: "radio", name: "rating", id: "r" + n, value: String(n),
                              onchange: () => { rating = n; } });
      return el("label", { for: "r" + n, class: "choice" }, r, " " + n);
    }));
  const form = el("form", { class: "stack" },
    el("h1", {}, "Send feedback"),
    el("p", {}, "What worked, what was confusing, what you wished it did. Every note is read."),
    el("p", { class: "muted" }, "How useful is it so far? (1 = not at all, 5 = very)"), stars,
    el("label", { for: "fb" }, "Your feedback"), comment,
    err,
    el("button", { type: "submit", class: "btn primary" }, "Send"),
    button("Cancel", () => window.history.back(), "link"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const text = comment.value.trim();
    if (!text) { err.textContent = "Write a few words first."; return; }
    try {
      await feedbackRequest({ comment: text, rating, screen: from });
      show(el("section", { class: "stack" }, el("h1", {}, "Thank you"),
        el("p", {}, "We read every note. It shapes what we build next."),
        button("Done", () => go(""), "primary")));
    } catch (ex) {
      const gate = accessProblem(ex);
      if (gate) return go(gate);
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online." : apiMessage(ex);
    }
  });
  return form;
}

// ------------------------------------------------------------------ first run (D-069, D-074)
function welcome() {
  return el("section", { class: "stack" },
    el("h1", {}, "See what's inside the pack"),
    el("p", { class: "lead" },
      "Scan a barcode, or photograph the ingredient list. We tell you what's in it, " +
      "starting with anything on your family's avoid list."),
    el("ul", { class: "plain" },
      el("li", {}, "An AI reads the label. Fixed rules, based on FSSAI regulations, make every judgement."),
      el("li", {}, "Nicknames you add stay on this phone. Our server only sees an age band and an avoid list."),
      el("li", {}, "It shows ingredient facts, not medical advice.")),
    button("Set up your household", () => { store.set("welcomed", true); go("household"); }, "primary"),
    button("Skip for now", () => { store.set("welcomed", true); go(""); }, "link"));
}

// ------------------------------------------------------------------ home
async function home() {
  const done = history().filter(h => h.screen?.state === "result").length;
  const recent = history().slice(0, 8);
  const updates = el("div", {});
  loadUpdates(updates);

  return el("section", { class: "stack" },
    updates,
    el("button", { type: "button", class: "scan-cta", onclick: () => { resetPending(); go("scan"); } },
      el("span", { class: "scan-cta-icon", "aria-hidden": "true" }, barcodeIcon()),
      el("span", {}, "Scan a pack")),
    done < 3 && el("div", { class: "card note" },
      el("h2", {}, "Start at home"),
      el("p", {}, "Scan 3 packs from your kitchen. You'll see how it works without a trip to the shop."),
      el("div", { class: "progress", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "3",
                  "aria-valuenow": String(done) },
        el("span", { style: `width:${(done / 3) * 100}%` })),
      el("p", { class: "muted" }, `${done} of 3 done`)),
    yourScans(),
    recent.length > 0 && el("h2", {}, "Recent scans"),
    recent.length > 0 && el("ul", { class: "list" }, recent.map(h =>
      el("li", {}, el("a", { href: `#/result/${encodeURIComponent(h.id)}` },
        el("strong", {}, productName(h.product)),
        h.screen?.summary?.length
          ? el("span", { class: "chips" }, h.screen.summary.map(r => el("span", { class: `chip tone-${r.tone}` }, r.chip)))
          : el("span", { class: "muted" }, peopleSummary(h.screen) || h.screen?.headline?.text || ""))))));
}

// D-123: what came up across this phone's own results. Counted here, worded on
// the server (screen.tallies, D-091); nothing is sent anywhere (D-074).
function yourScans() {
  const done = history().filter(h => h.screen?.state === "result" && Array.isArray(h.screen.tallies));
  if (done.length < 2) return null;
  const counts = new Map();
  done.forEach(h => h.screen.tallies.forEach(t => counts.set(t, (counts.get(t) || 0) + 1)));
  const rows = [...counts].sort((a, b) => b[1] - a[1]);
  return el("div", { class: "card" },
    el("h2", {}, "Your scans"),
    el("p", { class: "muted" }, `${done.length} packs checked, kept on this phone.`),
    rows.length
      ? el("div", { class: "tallies" }, rows.map(([label, n]) => el("div", { class: "tally" },
          el("div", { class: "row between" }, el("span", {}, label), el("span", { class: "muted" }, `${n} of ${done.length}`)),
          el("div", { class: "progress" }, el("span", { style: `width:${(n / done.length) * 100}%` })))))
      : el("p", {}, "Nothing came up often enough to list yet."));
}

function peopleSummary(screen) {
  const p = screen?.people?.[0];
  return p ? fill(p.line, p.ref) : "";
}

// D-070: "we'll tell you when it's ready" - checked on open; push comes later.
async function loadUpdates(slot) {
  let rows;
  try { rows = (await updatesRequest()).body.updates || []; } catch { return; }
  const seen = new Set(store.get("seenUpdates", []));
  const fresh = rows.filter(r => !seen.has(r.review_id));
  if (!fresh.length) return;
  slot.replaceChildren(el("div", { class: "card note", role: "status" },
    el("h2", {}, "News on packs you sent"),
    el("ul", { class: "plain" }, fresh.map(r => el("li", {}, updateLine(r)))),
    button("Got it", () => {
      store.set("seenUpdates", [...seen, ...fresh.map(r => r.review_id)]);
      slot.replaceChildren();
    })));
}

function updateLine(r) {
  const name = r.product_name || r.barcode;
  if (r.kind === "front_photo") {                                   // D-100
    return r.ready
      ? `Thanks: the front of ${name || "a pack you scanned"} is now on file.`
      : `Our team couldn't use the front photo of ${name || "a pack you scanned"}.`;
  }
  return r.ready
    ? `Checked by our team: ${name || "a pack you scanned"}. Scan its barcode for the result.`
    : `Our team looked at ${r.product_name || "a pack you sent"} and couldn't add it yet.`;
}

// ------------------------------------------------------------------ household (D-074)
function household() {
  const list = profiles();
  return el("section", { class: "stack" },
    el("h1", {}, "Your household"),
    el("p", { class: "muted" },
      `Up to ${MAX_PROFILES} people, including you. Nicknames stay on this phone.`),
    el("ul", { class: "list" }, list.map(p => el("li", {},
      el("a", { href: `#/person/${p.ref}` },
        el("strong", {}, p.nickname),
        el("span", { class: "muted" },
          [p.age === "adult" ? "Adult" : AGES.find(a => a.id === p.age)?.label,
           p.avoid.length ? `avoids ${p.avoid.length}` : "no avoid list"].join(" · ")))))),
    list.length < MAX_PROFILES && button("Add a child", () => go("person/new"), "primary"),
    button("Done", () => go(""), "link"));
}

async function person(ref) {
  const isNew = ref === "new";
  const list = profiles();
  const existing = isNew ? null : list.find(p => p.ref === ref);
  if (!isNew && !existing) return household();
  if (isNew && list.length >= MAX_PROFILES) return household();
  const isMe = existing?.ref === "me";
  const p = existing ? { ...existing, avoid: [...existing.avoid] }
                     : { ref: nextRef(list), nickname: "", age: "kid", avoid: [] };

  let allergens;
  try { allergens = await allergenList(); } catch {
    return errorView("We couldn't load the allergen list. Check your connection and try again.");
  }

  const form = el("form", { class: "stack", novalidate: true });
  const nameInput = !isMe && el("input", { id: "nick", maxlength: "20", required: true,
                                           value: p.nickname, autocomplete: "off" });
  const consent = !isMe && el("input", { type: "checkbox", id: "consent", checked: !!p.consent_at });
  const err = el("p", { class: "error", role: "alert" });

  form.append(...[
    el("h1", {}, isMe ? "Your avoid list" : isNew ? "Add a child" : `Edit ${p.nickname}`),
    !isMe && el("label", { for: "nick" }, "Nickname (stays on this phone)"),
    nameInput,
    !isMe && el("fieldset", {},
      el("legend", {}, "Age"),
      AGES.map(a => el("label", { class: "choice" },
        el("input", { type: "radio", name: "age", value: a.id, checked: p.age === a.id,
                      onchange: () => { p.age = a.id; } }),
        ` ${a.label} `, el("span", { class: "muted" }, a.sub)))),
    el("fieldset", {},
      el("legend", {}, "Avoid list"),
      el("p", { class: "muted" }, "We put these first on every result."),
      allergens.map(a => el("label", { class: "choice" },
        el("input", { type: "checkbox", value: a.code, checked: p.avoid.includes(a.code),
                      onchange: e => {
                        p.avoid = e.target.checked ? [...p.avoid, a.code] : p.avoid.filter(c => c !== a.code);
                      } }),
        el("span", {}, a.label,
          !a.fssai_mandatory && el("span", { class: "muted" }, " (brands don't have to declare it)"))))),
    !isMe && el("label", { class: "choice consent" }, consent,
      " I am this child's parent or guardian. I agree to InsideLabel using this age band and " +
      "avoid list to check labels for them."),
    err,
    el("button", { type: "submit", class: "btn primary" }, "Save"),
    !isNew && !isMe && button("Remove", () => {
      saveProfiles(profiles().filter(x => x.ref !== p.ref));
      go("household");
    }, "link danger"),
    button("Cancel", () => go("household"), "link"),
  ].flat().filter(x => x != null && x !== false));

  form.addEventListener("submit", e => {
    e.preventDefault();
    if (!isMe) {
      p.nickname = nameInput.value.trim();
      if (!p.nickname) { err.textContent = "Add a nickname."; return; }
      if (!consent.checked) { err.textContent = "Tick the parent or guardian box to save."; return; }
      p.consent_at = p.consent_at || new Date().toISOString();
    }
    const all = profiles();
    const i = all.findIndex(x => x.ref === p.ref);
    if (i >= 0) all[i] = p; else all.push(p);
    saveProfiles(all);
    go("household");
  });
  return form;
}

function nextRef(list) {
  for (let i = 1; i <= MAX_PROFILES; i++) if (!list.some(p => p.ref === "p" + i)) return "p" + i;
  return "p" + Date.now().toString(36).slice(-6);
}

// ------------------------------------------------------------------ scan: barcode first (D-024)
function resetPending() {
  pending = { barcode: null, barcodeSource: null, back: null, front: null, backSource: null,
              frontSource: null, pairing: false, attempts: 0, refused: [], frontWanted: true,
              acceptUnconfirmed: false, parts: [], partSources: [] };
}

async function scan() {
  const video = el("video", { class: "viewfinder", muted: true, playsinline: true, "aria-label": "Camera" });
  const status = el("p", { class: "muted", role: "status" }, "Starting the camera…");
  // D-104: a barcode comes from the live scanner or from a photo read on the
  // server, never typed: a mistyped number would file a pack under someone
  // else's product.
  const preview = el("div", { class: "thumb" });
  const next = el("div", {});
  const view = el("section", { class: "stack" },
    el("h1", {}, "Scan the barcode"),
    el("div", { class: "viewfinder-wrap" }, video, el("div", { class: "frame", "aria-hidden": "true" })),
    status,
    // D-107: a pack without a barcode can still be checked from its ingredients
    // photo; it just isn't added to the catalogue. Kept near the top, where it's seen.
    button("No barcode? Photograph the ingredients", () => { pending.barcode = null; go("photo"); }),
    el("h2", {}, "Or use a photo of the barcode"),
    photoPicker("barcode", "Take a photo of the barcode", preview, (_blob, res) => {
      next.replaceChildren();
      if (res?.ok && res.barcode) {
        next.append(button("Look up this pack", () => lookUp(res.barcode, "photo"), "primary"));
      }
    }),
    preview,
    next);

  const seq = navSeq;
  if (await barcodeSupported()) {
    startScanner(video, code => lookUp(code, "camera")).then(stop => {
      if (seq !== navSeq) return stop();          // the user left before the camera opened
      record("camera", { started: true });
      stopCamera = stop;
      status.textContent = "Point the camera at the barcode on the pack.";
      // D-124: a light for dim shelves, and help if nothing reads after a while.
      if (stop.hasTorch) {
        let on = false;
        const t = button("Turn on the light", async () => {
          if (await stop.torch(!on)) { on = !on; t.textContent = on ? "Turn off the light" : "Turn on the light"; }
        }, "link");
        status.after(t);
      }
      setTimeout(() => {
        if (seq === navSeq && stopCamera === stop) {
          status.textContent = "Hold the phone about a hand's width away, with the barcode flat and in good light. "
            + "Or take a photo of the barcode below.";
        }
      }, 8000);
    }).catch(e => {
      record("camera", { started: false, error: String(e?.name || e) });
      video.parentElement.remove();
      status.textContent = "We couldn't open the camera here. Take or upload a photo of the barcode instead.";
    });
  } else {
    record("camera", { barcode_detector: false });
    video.parentElement.remove();
    status.textContent = "This browser can't read barcodes live. Take or upload a photo of the barcode instead.";
  }
  return view;
}

async function lookUp(code, how) {
  if (stopCamera) { stopCamera(); stopCamera = null; }
  record("barcode", { how, digits: code.length });
  pending.barcode = code;
  pending.barcodeSource = how;
  show(working("Looking up this pack…", false));
  try {
    const { body } = await scanRequest({ barcode: code, barcodeSource: how });
    finish(body);
  } catch (e) {
    // 404 not_in_catalogue: the normal first-time path, not an error (D-068).
    if (e instanceof ApiError && e.status === 404 && e.body.error === "not_in_catalogue") return go("photo");
    show(apiErrorView(e, () => lookUp(code, how)));
  }
}

// ------------------------------------------------------------------ scan: the back photo (D-025, D-068)
function photo() {
  const firstTime = pending.barcode
    ? el("div", { class: "card note" },
        el("h2", {}, "First time we've seen this pack"),
        el("p", {}, "Photograph the ingredient list and we'll read it now. Our team then checks it, " +
                    "so the next scan of this barcode is instant, for everyone."))
    : el("p", { class: "lead" }, "Photograph the ingredient list, usually on the back of the pack.");

  const backPreview = el("div", { class: "thumb" });
  const frontPreview = el("div", { class: "thumb" });
  const pairing = el("input", { type: "checkbox", id: "pairing", checked: pending.pairing,
                                onchange: e => { pending.pairing = e.target.checked; } });
  const pairRow = el("label", { class: "choice", hidden: !pending.front }, pairing,
                     " Both photos are of the same pack");
  const go_ = el("button", { type: "button", class: "btn primary", disabled: !pending.back,
                             onclick: () => sendPhotos() }, "Check this pack");

  // D-119: a long list in up to three photos; the server joins them into one.
  // Most lists fit one photo, so the app asks first and shows the part camera
  // only on "No" (Sushil, 2026-09-27). Not answering means one photo.
  const parts = el("div", { class: "stack" });
  let more = false;              // "No, it continues" for the part now being asked about
  const drawParts = () => {
    parts.replaceChildren();
    if (!pending.back) return;
    pending.parts.forEach((_b, i) => parts.append(
      el("p", { class: "check ok", role: "status" }, el("span", { "aria-hidden": "true" }, "✓ "),
         `Part ${i + 2} of the list added.`)));
    if (pending.parts.length >= 2 || more === null) return;
    const n = pending.parts.length + 2;
    const ask = n === 2 ? "Is the whole ingredient list in this photo?" : "Is that the end of the list?";
    if (!more) {
      parts.append(el("div", { class: "card" },
        el("h2", {}, ask),
        el("p", { class: "muted" }, n === 2
          ? "On a big pack the list may not fit one clear photo. You can take it in parts instead."
          : "You can add one more part if the list still goes on."),
        el("div", { class: "row wrap" },
          el("button", { type: "button", class: "btn", onclick: () => { more = null; drawParts(); } },
             n === 2 ? "Yes, one photo is enough" : "Yes, that's all"),
          el("button", { type: "button", class: "btn", onclick: () => { more = true; drawParts(); } },
             `No, add part ${n}`))));
      return;
    }
    const prev = el("div", { class: "thumb" });
    parts.append(el("div", { class: "card" },
      el("h2", {}, `Part ${n} of the list`),
      el("p", { class: "muted" }, "Start where the last photo ended; a little overlap is fine."),
      photoPicker("back" + n, `Take part ${n} of the list`, prev, (b, res, source) => {
        if (!b || (res && !res.ok)) return;
        pending.parts.push(b);
        pending.partSources.push(source);
        more = false;            // ask again about the next part
        drawParts();
      }, "back"),
      prev));
  };
  drawParts();

  return el("section", { class: "stack" },
    el("h1", {}, "Photograph the ingredients"),
    firstTime,
    el("figure", { class: "sample" }, sampleBack(),
      el("figcaption", { class: "muted" }, "Fill the frame with the ingredient list. Hold steady and avoid glare.")),
    photoPicker("back", pending.back ? "Retake the ingredients photo" : "Take the ingredients photo", backPreview,
                (b, res, source) => {
                  // A red cross keeps "Check this pack" off; an unchecked photo (the
                  // check couldn't run) is let through, and /scan checks it again anyway.
                  pending.back = res && !res.ok ? null : b;
                  pending.backSource = source;
                  // A new first photo starts the list again (D-119).
                  pending.parts = []; pending.partSources = []; more = false;
                  drawParts();
                  go_.disabled = !pending.back;
                  if (res?.barcode && !pending.barcode) { pending.barcode = res.barcode; pending.barcodeSource = "photo"; }
                }),
    backPreview,
    parts,
    // D-100: asked for once per pack, not once per scan. A re-check of a pack
    // whose front is already on file doesn't ask again.
    pending.frontWanted && el("div", { class: "card" },
      el("h2", {}, "The front of the pack"),
      el("p", { class: "muted" }, "Optional. The front shows the pack's name and what it promises. " +
                                  "Our team records it once for each pack."),
      photoPicker("front", "Take the front photo", frontPreview, (b, res, source) => {
        pending.front = res && !res.ok ? null : b;
        pending.frontSource = source;
        pairRow.hidden = !pending.front;
      }),
      frontPreview, pairRow),
    go_);
}

// D-102: take a photo now, or upload one already on the phone or computer
// (a saved picture, a pack photographed earlier). `capture` makes a phone open
// the camera straight away, so the upload button is a second input without it.
// On a computer (no touch screen) there is only "choose", and a photo can be
// dropped onto the box.
const TOUCH = window.matchMedia?.("(pointer: coarse)").matches ?? true;

// D-104: every photo is checked on the server as soon as it is picked, and
// gets a green tick or a red cross with the reason. onPick(blob, result):
// result is {ok, message, barcode}, or null when the check couldn't run.
// D-106: onPick also gets where the photo came from, "camera" or "upload".
function photoPicker(role, label, preview, onPick, checkAs = role) {
  const use = async (file, source) => {
    if (!file || !file.type.startsWith("image/")) return;
    preview.replaceChildren(el("p", { class: "muted" }, "Preparing photo…"));
    const blob = await prepareImage(file);
    const img = el("img", { src: URL.createObjectURL(blob), alt: `Your ${role} photo` });
    preview.replaceChildren(img, el("p", { class: "muted", role: "status" }, "Checking the photo…"));
    let res = null;
    try {
      res = (await checkPhotoRequest(checkAs, blob)).body;
    } catch (e) {
      const gate = accessProblem(e);
      if (gate) return go(gate);
      if (e.status === 429 || e.status === 413 || e.status === 415) res = { ok: false, message: apiMessage(e) };
    }
    record("photo_check", { role, ok: res ? res.ok : null, problem: res?.problem || null, barcode: !!res?.barcode });
    const line = res === null
      ? el("p", { class: "check unknown", role: "status" },
          role === "barcode" ? "We couldn't check this photo just now. Try again in a moment."
                             : "We couldn't check this photo just now. It will be checked when you continue.")
      : el("p", { class: "check " + (res.ok ? "ok" : "bad"), role: "status" },
          el("span", { "aria-hidden": "true" }, res.ok ? "✓ " : "✗ "), res.message);
    preview.replaceChildren(img, line);
    onPick(blob, res, source);
  };
  const input = (id, capture) => {
    const i = el("input", { type: "file", accept: "image/*", class: "sr", id, ...(capture ? { capture: "environment" } : {}) });
    i.addEventListener("change", () => { record("photo_source", { role, source: capture ? "camera" : "upload" });
                                         use(i.files && i.files[0], capture ? "camera" : "upload"); });
    return i;
  };
  const box = TOUCH
    ? el("div", { class: "row" },
        input("pick-" + role, true), el("label", { for: "pick-" + role, class: "btn" }, label),
        input("upload-" + role, false), el("label", { for: "upload-" + role, class: "btn link" }, "Upload a photo"))
    : el("div", { class: "drop" },
        input("pick-" + role, false), el("label", { for: "pick-" + role, class: "btn" }, "Choose a photo"),
        el("span", { class: "muted" }, " or drop one here"));
  if (!TOUCH) {
    box.addEventListener("dragover", e => { e.preventDefault(); box.classList.add("over"); });
    box.addEventListener("dragleave", () => box.classList.remove("over"));
    box.addEventListener("drop", e => {
      e.preventDefault(); box.classList.remove("over");
      record("photo_source", { role, source: "drop" });
      use(e.dataTransfer?.files?.[0], "upload");
    });
  }
  return box;
}

// ------------------------------------------------------------------ the front alone (D-100)
// For a pack the catalogue has without its front: one photo, no model call.
function front(id) {
  const h = historyItem(id);
  if (!h || !h.barcode) return errorView("We couldn't find that pack on this phone.");
  const preview = el("div", { class: "thumb" });
  let blob = null, blobSource = null;
  const send = el("button", { type: "button", class: "btn primary", disabled: true, onclick: async () => {
    resetPending();
    pending.barcode = h.barcode;
    show(working("Sending the photo…", false));
    try {
      const { body } = await scanRequest({ barcode: h.barcode, front: blob, frontSource: blobSource });
      finish(body);
    } catch (e) {
      show(apiErrorView(e, () => go("front/" + encodeURIComponent(id))));
    }
  } }, "Send the front photo");
  return el("section", { class: "stack" },
    el("h1", {}, "Photograph the front"),
    el("p", { class: "product" }, productName(h.product)),
    el("p", { class: "lead" }, "Fill the frame with the front of the pack, including any words printed on it."),
    photoPicker("front", "Take the front photo", preview, (b, res, source) => {
      blob = res && !res.ok ? null : b;
      blobSource = source;
      send.disabled = !blob;
    }),
    preview,
    send,
    button("Not now", () => go("result/" + encodeURIComponent(id)), "link"));
}

async function sendPhotos() {
  show(working("Reading the ingredient list…", true));
  try {
    const { body } = await scanRequest(pending);
    finish(body);
  } catch (e) {
    show(apiErrorView(e, sendPhotos));
  }
}

// D-068: honest about speed. The API has no progress events yet, so we show
// time passing and what a first read usually takes, not invented steps.
function working(text, reading) {
  const secs = el("span", {}, "0");
  const slow = el("p", { class: "muted" });
  const t0 = Date.now();
  const timer = setInterval(() => {
    if (!secs.isConnected) return clearInterval(timer);
    const n = Math.round((Date.now() - t0) / 1000);
    secs.textContent = String(n);
    // D-124: a slow read should not look like a hang.
    if (reading && n >= 20 && !slow.textContent) {
      slow.textContent = "Taking longer than usual: the reader is busy right now. It is still working.";
    }
  }, 1000);
  return el("section", { class: "stack center", "aria-busy": "true" },
    el("div", { class: "pulse", "aria-hidden": "true" }),
    el("h1", {}, text),
    reading && el("p", { class: "muted" },
      "The first read of a pack takes about 8 to 15 seconds. Once a pack is in our catalogue, its barcode gives the result at once."),
    el("p", { class: "muted", role: "timer" }, secs, " s"),
    slow);
}

function finish(body) {
  const id = body.scan_id || "local-" + Date.now().toString(36);
  const rel = body.reliability || {};
  addHistory({
    id, at: new Date().toISOString(), barcode: pending.barcode,
    scan_id: body.scan_id || null,
    product: body.product || null,
    screen: body.screen,
    catalogue: body.catalogue || null,
    disclosures: body.disclosures || [],
    // What /compare needs later, kept so a comparison costs no new scan (D-057).
    pack: body.screen?.state === "result" ? {
      ingredients: body.extracted?.ingredients || [],
      allergen_statement: body.extracted?.allergen_statement || null,
      confidence: rel.confidence?.ingredients ?? 1.0,
      reliable: rel.source === "catalogue" || (!!rel.verdict_safe_to_display && !!rel.ingredients_complete),
    } : null,
  });
  if (body.screen?.state === "retake") {
    pending.attempts += 1;
    // D-103: a photo that isn't a pack (a screen, anything else) can't be sent to a reviewer.
    if (body.scan_id && body.screen.can_send !== false) pending.refused.push(body.scan_id);
  }
  go("result/" + encodeURIComponent(id));
}

// ------------------------------------------------------------------ result (D-060 to D-066)
function result(id) {
  const h = historyItem(id);
  if (!h || !h.screen) return errorView("We couldn't find that result on this phone.");
  const s = h.screen;
  const view = el("section", { class: "stack result" });
  // el() drops false/null children; the DOM's own append() would print "false".
  const put = (...nodes) => view.append(...nodes.filter(x => x != null && x !== false));

  put(el("p", { class: "product" }, productName(h.product)));

  // 1. People first (D-060, D-064).
  if (s.people?.length) put(el("div", { class: "people" }, s.people.map(personCard)));

  // 2. The headline finding (D-061).
  put(el("h1", { class: "headline" }, s.headline.text));

  if (s.state === "retake") {
    put(
      el("p", { class: "card warn" }, s.retake),
      button("Retake the photo", () => {
        pending.back = null;
        pending.parts = []; pending.partSources = [];
        pending.acceptUnconfirmed = false;
        // D-108: after "these look like different packs", neither photo can be trusted.
        if (s.headline?.source?.ref === "product_mismatch") { pending.front = null; pending.pairing = false; }
        go("photo");
      }, "primary"),
      // D-118: our second reader couldn't confirm a new pack's list. The person
      // can still have their result from these photos.
      s.can_use_anyway && pending.back && button("Use this one anyway", () => {
        pending.acceptUnconfirmed = true;
        sendPhotos();
      }),
      pending.attempts >= 2 && s.can_send !== false && el("p", { class: "muted" },
        "Still not working? Try daylight, or another pack. Some labels are printed too small or too shiny to read."),
      // D-070: after two refusals, a person reads the photos instead.
      pending.refused.length >= 2 && button("Send it to us", () => go("send")),
      reportLink(h), problemLink());
    return view;
  }

  // D-111: an additive FSSAI doesn't permit, read with confidence. Server text only.
  if (s.additive_alert) put(el("div", { class: "add-alert", role: "note" },
    el("span", { class: "add-icon", "aria-hidden": "true" }, "!"),
    el("div", {}, el("strong", {}, s.additive_alert.text), el("p", {}, s.additive_alert.detail))));

  // D-125: "Worth a look" rows, closed until tapped; the arrow nudges until then.
  (s.alerts || []).forEach(a => put(el("details", { class: "look" },
    el("summary", {},
      el("span", { class: "add-icon look-icon", "aria-hidden": "true" }, "!"),
      el("span", {}, el("strong", {}, a.title), el("span", { class: "look-more" }, a.more)),
      el("span", { class: "look-arrow", "aria-hidden": "true" }, el("span", {}, "\u203a"))),
    el("div", { class: "look-body" },
      a.body.map(t => el("p", {}, t)),
      el("p", { class: "muted small" }, "On the label: ", el("q", {}, a.label_line)),
      a.sources.length > 0 && el("ul", { class: "plain small" }, a.sources.map(x =>
        el("li", {}, el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.title))))))));

  // 3. D-123: the same three answers on every pack. Older results kept on the
  // phone have no summary; they keep the band (D-063) as before.
  if (s.summary?.length) {
    put(el("div", { class: "answers" }, s.summary.map(r => el("div", { class: "answer" },
      el("span", { class: "q" }, r.label),
      el("div", { class: "a" },
        el("span", { class: `chip tone-${r.tone}` }, r.chip),
        el("p", {}, r.text))))));
    if (s.band.note) put(el("details", { class: "item" }, el("summary", {}, "What does \"industrial\" mean?"),
      el("p", {}, s.band.note)));
  } else {
    put(el("div", { class: `band band-${s.band.code}` },
      el("strong", {}, s.band.label),
      s.band.note && el("details", {}, el("summary", {}, "What does this mean?"), el("p", {}, s.band.note))));
    put(el("p", { class: "muted" }, s.checked, " ", s.scope));
  }
  if (s.catalogue_note) put(el("p", { class: "card note" }, s.catalogue_note));      // D-107
  if (s.front_note) put(el("p", { class: "card note" }, s.front_note));              // D-108

  if (s.retake) put(el("div", { class: "card warn" }, el("p", {}, s.retake),
    button("Retake the ingredients photo", () => { pending = { ...pending, back: null, barcode: h.barcode }; go("photo"); })));
  if (s.last_verified) put(el("p", { class: "muted" }, s.last_verified));
  if (s.recheck) put(el("div", { class: "card note" }, el("p", {}, s.recheck),
    button("Photograph the back", () => {
      resetPending();
      pending.barcode = h.barcode;
      pending.frontWanted = !!h.catalogue?.front_wanted;           // D-100
      go("photo");
    })));

  // 4. Claim check, once released (D-051).
  if (s.claims?.length) {
    put(el("h2", {}, "The front of the pack"),
      el("ul", { class: "plain" }, s.claims.map(c => el("li", { class: c.contradicted ? "flag" : "" }, c.text))));
  }

  // 5a. Every additive as a card with its badge (D-111). When the server sends
  // these, the lists below leave additives out so none shows twice.
  const cards = s.additives?.items || [];
  if (cards.length) {
    // Server order: cards that need a look first, then the ones folded behind folded_text.
    const shown = cards.slice(0, s.additives.open ?? cards.length);
    const folded = cards.slice(s.additives.open ?? cards.length);
    put(el("h2", {}, s.additives.title),
      el("div", { class: "items" }, shown.map(additiveCard),
        folded.length > 0 && el("details", { class: "item fold" }, el("summary", {}, s.additives.folded_text),
          el("div", { class: "items" }, folded.map(additiveCard)))));
  }
  const notCard = w => !(cards.length && w.source?.kind === "additive");

  // 5b. Worth knowing, each with its why one tap away (D-056, D-066).
  const worth = (s.worth_knowing || []).filter(notCard);
  if (worth.length) {
    put(el("h2", {}, "Worth knowing"),
      el("div", { class: "items" }, worth.map(w => el("details", { class: `item concern-${w.concern}` },
        el("summary", {}, w.name),
        el("p", {}, w.why),
        el("p", { class: "muted" }, "On the label: ", el("q", {}, w.label_text)),
        el("p", { class: "tech" }, w.technical)))));
  }

  // 6. Ordinary ingredients, grouped (D-065), then the full list as read.
  if (s.ordinary?.text && !s.summary?.length) {
    const plain = s.ordinary.additives.filter(notCard);
    put(el("details", { class: "item" },
      el("summary", {}, s.ordinary.text),
      plain.length > 0 && el("ul", { class: "plain" }, plain.map(a =>
        el("li", {}, el("strong", {}, a.name), ": ", a.why)))));
  }
  put(el("details", { class: "item" },
    el("summary", {}, "The ingredient list as read"),
    el("ol", {}, s.ingredients.map(i => el("li", {}, i)))));

  // D-100: a front photo for the catalogue goes to our team; the result above
  // is still the reviewed record.
  const frontSent = h.catalogue?.front_received || h.catalogue?.queued_for_review === "front_photo";
  if (frontSent) {
    put(el("p", { class: "muted" }, "Thanks. Our team has the front photo and will record what the pack says."));
  } else if (h.catalogue?.queued_for_review) {
    put(el("p", { class: "muted" },
      "Our team will check this pack. After that, scanning its barcode gives the result straight away."));
  }
  if (h.catalogue?.front_wanted && h.barcode && !frontSent) {
    put(el("div", { class: "card note" },
      el("h2", {}, "Add the front of the pack?"),
      el("p", {}, "We have this pack's ingredients but not its front. One photo lets our team record " +
                  "its name and what it promises, for everyone who scans it."),
      button("Photograph the front", () => go("front/" + encodeURIComponent(h.id)))));
  }

  if (s.summary?.length) put(el("p", { class: "muted small" }, s.checked, " ", s.scope));

  // D-123: the next useful scan is the pack beside this one on the shelf (D-057).
  if (h.pack) {
    const waiting = store.get("compare", []).filter(x => x !== h.id && historyItem(x));
    put(el("div", { class: "card note" },
      el("h2", {}, waiting.length ? "Compare with the packs you added" : "Holding another pack?"),
      el("p", {}, waiting.length
        ? `See this one next to the ${waiting.length === 1 ? "other pack" : `other ${waiting.length} packs`} you added.`
        : "Scan the one next to it on the shelf and see them side by side."),
      button(waiting.length ? "Compare them" : "Scan another to compare", () => {
        if (!store.get("compare", []).includes(h.id)) toggleCompare(h.id);
        updateNav();
        if (waiting.length) go("compare"); else { resetPending(); go("scan"); }
      }, "primary")));
  }

  // 7. What this covers - stated, never silent (D-037).
  put(el("details", { class: "item" }, el("summary", {}, "What this check covers"),
    el("ul", { class: "plain small" }, (h.disclosures || []).map(d => el("li", {}, d)))));

  // 8. Actions: compare (D-057), report (D-076, on every result).
  const inCompare = store.get("compare", []).includes(h.id);
  put(el("div", { class: "row wrap" },
    h.pack && button(inCompare ? "In compare ✓" : "Add to compare", e => {
      toggleCompare(h.id); e.target.textContent = store.get("compare", []).includes(h.id)
        ? "In compare ✓" : "Add to compare"; updateNav();
    }),
    button("Scan another", () => { resetPending(); go("scan"); }, "primary")),
    reportLink(h));
  return view;
}

function personCard(p) {
  const who = profileByRef(p.ref);
  const detail = [...p.allergens.slice(1).map(a => a.text), ...p.child_facts.map(f => f.text)];
  return el("div", { class: `person status-${p.status}` },
    el("span", { class: "who" }, who ? who.nickname : "Someone in your household"),
    el("p", { class: "line" }, fill(p.line, p.ref)),
    detail.length > 0 && el("details", {}, el("summary", {}, "More"),
      el("ul", { class: "plain small" }, detail.map(t => el("li", {}, fill(t, p.ref))))));
}

// D-111: one additive, laid out from the server's item. The badge words and the
// kind come from lenses/screen.py; the icon is decoration (aria-hidden).
const BADGE_ICON = { not_permitted: "✕", worth_knowing: "!", permitted: "•" };
function additiveCard(a) {
  const kind = a.badge?.kind || "none";
  return el("article", { class: `add add-${kind}` },
    el("div", { class: "add-top" },
      el("p", { class: "add-name" }, a.ins && el("small", {}, "INS " + a.ins), a.name),
      a.badge && el("span", { class: "badge" },
        el("span", { class: "add-icon", "aria-hidden": "true" }, BADGE_ICON[kind] || ""), a.badge.text)),
    el("p", { class: "muted small" }, "On the label: ", el("q", {}, a.label_line || a.label_text)),
    el("p", { class: "small" }, a.why),
    a.badge?.note && el("p", { class: "small add-note" }, a.badge.note));
}

function reportLink(h) {
  return el("p", {}, el("a", { href: `#/report/${encodeURIComponent(h.id)}`, class: "report" },
    "Report a mistake"));
}

// ------------------------------------------------------------------ report a mistake (D-076)
const REPORT_FIELDS = [
  ["ingredients", "The ingredient list is wrong"],
  ["allergens", "An allergen is missing or wrong"],
  ["product_name", "Wrong product name"],
  ["claim", "Something on the front of the pack"],
  ["other", "Something else"],
];

function report(id) {
  const h = historyItem(id);
  if (!h) return errorView("We couldn't find that result on this phone.");
  if (!h.scan_id) {
    return el("section", { class: "stack" }, el("h1", {}, "Report a mistake"),
      el("p", {}, "This result wasn't saved on our server, so we can't look into it. " +
                  "Scan the pack again when you're online and report it from that result."),
      button("Back", () => window.history.back()));
  }
  const field = el("select", { id: "field" }, REPORT_FIELDS.map(([v, t]) => el("option", { value: v }, t)));
  const said = el("textarea", { id: "said", maxlength: "4000", rows: "3" });
  const note = el("textarea", { id: "note", maxlength: "2000", rows: "3" });
  const err = el("p", { class: "error", role: "alert" });
  // D-109: one of the two boxes needs real text; the server says the same sentence.
  const needText = "Tell us what the pack says, or what looks wrong. One of the two is enough.";
  const form = el("form", { class: "stack" },
    el("h1", {}, "Report a mistake"),
    el("p", { class: "muted" }, productName(h.product)),
    el("label", { for: "field" }, "What's wrong?"), field,
    el("p", { class: "small muted" }, needText),
    el("label", { for: "said" }, "What does the pack say?"), said,
    el("label", { for: "note" }, "What looks wrong?"), note,
    err,
    el("button", { type: "submit", class: "btn primary" }, "Send to our team"),
    button("Cancel", () => window.history.back(), "link"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (said.value.trim().length < 3 && note.value.trim().length < 3) {
      err.textContent = needText;
      return (said.value.trim() ? note : said).focus();
    }
    try {
      await reportRequest({ scan_id: h.scan_id, field: field.value,
                            proposed_value: said.value.trim() || null, note: note.value.trim() || null });
      show(el("section", { class: "stack" }, el("h1", {}, "Thank you"),
        el("p", {}, "Our team will look at the pack. You'll see what they found on the home screen."),
        button("Done", () => go(""), "primary")));
    } catch (ex) {
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online."
                      : ex.body?.error === "empty_report" ? needText
                      : "We couldn't send that just now. Try again in a minute.";
    }
  });
  return form;
}

// ------------------------------------------------------------------ compare (D-057)
function toggleCompare(id) {
  const list = store.get("compare", []);
  store.set("compare", list.includes(id) ? list.filter(x => x !== id) : [...list, id].slice(-4));
}

function compare() {
  const ids = store.get("compare", []);
  const packs = ids.map(historyItem).filter(h => h && h.pack);
  const kids = profiles().filter(p => p.age !== "adult");
  const others = history().filter(h => h.pack && !ids.includes(h.id)).slice(0, 10);
  let whoRef = kids[0]?.ref || null;
  let age = kids[0]?.age || "kid";
  const out = el("div", { class: "stack", "aria-live": "polite" });
  const refresh = id => { toggleCompare(id); updateNav(); route(); };

  const run = async () => {
    const who = whoRef ? profileByRef(whoRef) : null;
    out.replaceChildren(el("p", { class: "muted" }, "Comparing…"));
    try {
      const { body } = await compareRequest({
        packs: packs.map(h => ({ id: h.id, name: productName(h.product), ...h.pack,
                                 confidence: Math.min(1, Math.max(0, h.pack.confidence)) })),
        age: who ? who.age : age,
        avoid: who ? who.avoid : [],
        who: who ? "{name}" : null,           // D-074: the nickname is filled in here, not sent
      });
      out.replaceChildren(compareResult(body, whoRef));
    } catch (e) {
      out.replaceChildren(el("p", { class: "error" }, apiMessage(e)));
    }
  };

  return el("section", { class: "stack" },
    el("h1", {}, "Compare packs"),
    el("p", { class: "muted" },
      "Scan 2 to 4 packs from the same shelf. We name the better pick of these for a child."),
    packs.length
      ? el("ul", { class: "list" }, packs.map(h => el("li", { class: "row between" },
          el("span", {}, productName(h.product)), button("Remove", () => refresh(h.id), "link"))))
      : el("p", {}, "Nothing added yet."),
    others.length > 0 && packs.length < 4 && el("details", {},
      el("summary", {}, "Add from recent scans"),
      el("ul", { class: "list" }, others.map(h => el("li", { class: "row between" },
        el("span", {}, productName(h.product)), button("Add", () => refresh(h.id), "link"))))),
    kids.length > 0
      ? el("fieldset", {}, el("legend", {}, "For"), kids.map(k => el("label", { class: "choice" },
          el("input", { type: "radio", name: "who", checked: k.ref === whoRef,
                        onchange: () => { whoRef = k.ref; } }), " " + k.nickname)))
      : el("fieldset", {}, el("legend", {}, "Child's age"), AGES.map(a => el("label", { class: "choice" },
          el("input", { type: "radio", name: "age", checked: a.id === age, onchange: () => { age = a.id; } }),
          ` ${a.label} `, el("span", { class: "muted" }, a.sub)))),
    el("button", { type: "button", class: "btn primary", disabled: packs.length < 2, onclick: run }, "Compare"),
    button("Scan a pack to add", () => { resetPending(); go("scan"); }, "link"),
    out);
}

// Outcome headings are the only compare wording written here; every reason
// comes from compare.py (D-057), which the wording lint checks.
function compareResult(r, ref) {
  const name = id => r.packs.find(p => p.id === id)?.name || "";
  const who = fill(r.who, ref);
  const heading = {
    best: `Better pick of these for ${who}: ${name(r.best)}`,
    tie: `These are level for ${who}: ${r.tie.map(name).join(", ")}`,
    no_clear_pick: `No clear pick of these for ${who}.`,
    unknown_additives: "We can't pick yet: a pack has an additive we haven't checked.",
    unreadable: "We couldn't read enough of these packs to compare. Scan them again.",
  }[r.outcome];
  return el("div", { class: "stack" },
    el("h2", {}, heading),
    r.why_best?.length > 0 && el("ul", { class: "plain" }, r.why_best.map(t => el("li", {}, fill(t, ref)))),
    r.allergen_lines?.length > 0 && el("ul", { class: "plain" }, r.allergen_lines.map(t => el("li", {}, fill(t, ref)))),
    r.packs.map(p => el("details", { class: "item" + (p.id === r.best ? " best" : "") },
      el("summary", {}, p.name + (p.id === r.best ? " (better pick)" : "")),
      el("ul", { class: "plain small" },
        p.allergens.filter(a => a.state !== "not_listed").map(a => el("li", { class: "flag" }, fill(a.text, ref))),
        p.facts.filter(f => f.tier !== "info" || f.positive).map(f =>
          el("li", { class: f.tier === "strong" ? "flag" : "" }, f.text)),
        !p.fully_checked && el("li", { class: "muted" }, "Not fully checked, so it can't be the pick.")))));
}

// ------------------------------------------------------------------ errors
function apiMessage(e) {
  if (!(e instanceof ApiError)) return "Something went wrong. Try again.";
  if (e.status === 0) return "No connection. Check your internet and try again.";
  // Our setup (key, credit), not a busy moment: "in a minute" would be untrue.
  if (e.body?.error === "vision_not_configured") return "The label reader isn't available right now. Please try again later today.";
  if (e.status === 503) return "The label reader is busy right now. Try again in a minute.";
  // D-095: the server's own text says how long to wait.
  if (e.status === 429) return e.body?.detail || "You've checked a lot of packs in a short time. Please wait a few minutes.";
  // D-103: the server names what's wrong with a barcode or a photo file.
  const own = ["bad_barcode", "not_an_image", "photo_too_small", "photo_blank", "back_required", "rate_limited"];
  if (own.includes(e.body?.error) && e.body.detail) return e.body.detail;
  if (e.status === 413) return "That photo is too large. Take it again a little further away.";
  if (e.status === 415) return "That file isn't a photo we can read. Use the camera instead.";
  return "Something went wrong on our side. Try again in a minute.";
}

function apiErrorView(e, retry) {
  const gate = accessProblem(e);             // D-102/D-105: not joined, or rules not agreed
  if (gate) return gate === "join" ? join() : agree();
  return el("section", { class: "stack" },
    el("h1", {}, "That didn't work"),
    el("p", {}, apiMessage(e)),
    retry && button("Try again", retry, "primary"),
    problemLink(),
    button("Home", () => go(""), "link"));
}

function errorView(text) {
  return el("section", { class: "stack" }, el("h1", {}, "Sorry"), el("p", {}, text),
    button("Home", () => go(""), "primary"), problemLink());
}

// ------------------------------------------------------------------ report a problem (D-092)
// "Report a mistake" is about the answer (reviewers fix the data). This is about
// the app misbehaving: it sends the trail so the developer can replay it.
function problemLink() {
  return el("p", {}, el("a", { href: "#/problem", class: "report" }, "Something not working? Report a problem"));
}

function problem() {
  const incident = lastIncident();
  const comment = el("textarea", { id: "comment", maxlength: "2000", rows: "3" });
  const err = el("p", { class: "error", role: "alert" });
  const preview = el("pre", { class: "tech preview" });
  const form = el("form", { class: "stack" },
    el("h1", {}, "Report a problem"),
    el("p", {}, "Tell us what went wrong. We'll send what the app did in the last few minutes, " +
                "so we can see exactly what happened."),
    el("label", { for: "comment" }, "What happened? (optional)"), comment,
    el("details", { class: "item", ontoggle: () => {
        preview.textContent = JSON.stringify({ client: clientInfo(), events: trailSnapshot(), ...incident }, null, 1);
      } },
      el("summary", {}, "What we'll send"),
      el("ul", { class: "plain small" },
        el("li", {}, "The screens you opened and the requests the app made, with their times and results."),
        el("li", {}, "Your phone and browser type, screen size and connection."),
        el("li", {}, "Age bands and avoid lists. Nicknames stay on this phone."),
        el("li", {}, "If a pack was scanned, we keep its photos until we've looked into it.")),
      preview),
    err,
    el("button", { type: "submit", class: "btn primary" }, "Send report"),
    button("Cancel", () => window.history.back(), "link"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      const { body } = await problemRequest({ kind: "user", comment: comment.value.trim() || null, ...incident });
      show(el("section", { class: "stack" }, el("h1", {}, "Thank you"),
        el("p", {}, `We've got it. Your reference is #${body.problem_id}.`),
        el("p", { class: "muted" }, "Quote it if you write to us about this."),
        button("Done", () => go(""), "primary")));
    } catch (ex) {
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online."
                                        : "We couldn't send that just now. Try again in a minute.";
    }
  });
  return form;
}

// ------------------------------------------------------------------ send it to us (D-070)
function send() {
  const ids = pending.refused.slice(-6);
  if (ids.length < 2) return errorView("Take the photo twice first; then you can send it to us.");
  const err = el("p", { class: "error", role: "alert" });
  const go_ = el("button", { type: "button", class: "btn primary" }, "Send the photos");
  const view = el("section", { class: "stack" },
    el("h1", {}, "Send it to us"),
    el("p", {}, "We'll read this pack's label by hand and tell you here when it's ready."),
    el("ul", { class: "plain small" },
      el("li", {}, `We keep the ${ids.length} photos you took until our team has read them.`),
      el("li", {}, "Nothing else is sent. Nicknames stay on this phone.")),
    err, go_,
    button("Cancel", () => window.history.back(), "link"));
  go_.addEventListener("click", async () => {
    go_.disabled = true;
    try {
      await sendToUsRequest(ids);
      resetPending();
      show(el("section", { class: "stack" }, el("h1", {}, "Thank you"),
        el("p", {}, "Our team will read the label. You'll see it on the home screen when it's ready."),
        button("Done", () => go(""), "primary")));
    } catch (ex) {
      go_.disabled = false;
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online." : apiMessage(ex);
    }
  });
  return view;
}

// Crashes nobody reports: sent automatically, once per error per session, with
// the trail but no comment. Only errors from our own scripts.
const sentCrashes = new Set();
function crash(kind, message, where) {
  record("error", { kind, message: String(message).slice(0, 300), where });
  const signature = `${kind}:${String(message).slice(0, 80)}@${where}`;
  if (sentCrashes.has(signature)) return;
  sentCrashes.add(signature);
  problemRequest({ kind: "auto", signature, ...lastIncident() }).catch(() => {});
}
window.addEventListener("error", e => {
  if (e.filename && !e.filename.startsWith(location.origin)) return;
  const file = (e.filename || "").split("/").pop();
  crash("error", e.message, `${file}:${e.lineno}:${e.colno}`);
});
window.addEventListener("unhandledrejection", e => {
  const r = e.reason;
  const top = String(r?.stack || "").split("\n").find(l => l.includes(location.origin)) || "";
  crash("rejection", r?.message || r, top.split("/").pop().replace(/\)$/, "") || "?");
});

// ------------------------------------------------------------------ pictures
const SVG = "http://www.w3.org/2000/svg";
function svg(markup, cls, label) {
  const tmp = document.createElementNS(SVG, "svg");
  tmp.setAttribute("viewBox", "0 0 120 80");
  tmp.setAttribute("class", cls);
  if (label) { tmp.setAttribute("role", "img"); tmp.setAttribute("aria-label", label); }
  else tmp.setAttribute("aria-hidden", "true");
  tmp.innerHTML = markup;              // our own constant markup, never server text
  return tmp;
}

// D-068: a sample of which side to shoot.
function sampleBack() {
  return svg(
    `<rect x="18" y="4" width="84" height="72" rx="6" class="s-pack"/>
     <rect x="26" y="12" width="68" height="34" rx="3" class="s-hi"/>
     <text x="30" y="21" class="s-t">INGREDIENTS:</text>
     <rect x="30" y="25" width="58" height="3" class="s-line"/>
     <rect x="30" y="31" width="52" height="3" class="s-line"/>
     <rect x="30" y="37" width="56" height="3" class="s-line"/>
     <rect x="26" y="52" width="40" height="18" class="s-dim"/>
     <rect x="72" y="54" width="22" height="14" class="s-dim"/>`,
    "sample-svg", "Back of a pack with the ingredient list highlighted");
}

function barcodeIcon() {
  return svg(`<path d="M20 15v50M30 15v50M36 15v50M48 15v50M56 15v50M62 15v50M74 15v50M84 15v50M90 15v50M100 15v50" class="s-bars"/>`,
             "icon-svg");
}

// ------------------------------------------------------------------ start
window.addEventListener("hashchange", route);
deviceId();
record("start", { app_version: APP_VERSION });
route();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
