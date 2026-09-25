// app.js — InsideLabel PWA: views and navigation.
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
  updatesRequest, validGtin,
} from "./lib.js";
import { barcodeSupported, startScanner } from "./camera.js";

const main = document.getElementById("main");
let stopCamera = null;
let navSeq = 0;               // async views check this so a late result can't replace a newer page
// The scan in progress: barcode (if read), photos, and how many times it was refused
// (with the refused scans' ids, for "Send it to us", D-070).
let pending = { barcode: null, back: null, front: null, pairing: false, attempts: 0, refused: [] };

// ------------------------------------------------------------------ navigation
const routes = {
  "": home, welcome, household, person, scan, photo, result, report, compare, problem, send,
};

function go(path) { location.hash = "#/" + path; }

function route() {
  if (stopCamera) { stopCamera(); stopCamera = null; }
  const [name, arg] = location.hash.replace(/^#\/?/, "").split("/");
  // D-092: screens in the trail. `arg` is a scan id or a profile ref, never a name.
  record("route", { to: name || "home", arg: arg || undefined });
  if (!store.get("welcomed", false) && name !== "welcome" && name !== "household" && name !== "person") {
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
    recent.length > 0 && el("h2", {}, "Recent scans"),
    recent.length > 0 && el("ul", { class: "list" }, recent.map(h =>
      el("li", {}, el("a", { href: `#/result/${encodeURIComponent(h.id)}` },
        el("strong", {}, productName(h.product)),
        el("span", { class: "muted" }, peopleSummary(h.screen) || h.screen?.headline?.text || ""))))));
}

function peopleSummary(screen) {
  const p = screen?.people?.[0];
  return p ? fill(p.line, p.ref) : "";
}

// D-070: "we'll tell you when it's ready" — checked on open; push comes later.
async function loadUpdates(slot) {
  let rows;
  try { rows = (await updatesRequest()).body.updates || []; } catch { return; }
  const seen = new Set(store.get("seenUpdates", []));
  const fresh = rows.filter(r => !seen.has(r.review_id));
  if (!fresh.length) return;
  slot.replaceChildren(el("div", { class: "card note", role: "status" },
    el("h2", {}, "News on packs you sent"),
    el("ul", { class: "plain" }, fresh.map(r => el("li", {},
      r.ready
        ? `Checked by our team: ${r.product_name || r.barcode || "a pack you scanned"}. Scan its barcode for the result.`
        : `Our team looked at ${r.product_name || "a pack you sent"} and couldn't add it yet.`))),
    button("Got it", () => {
      store.set("seenUpdates", [...seen, ...fresh.map(r => r.review_id)]);
      slot.replaceChildren();
    })));
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
  pending = { barcode: null, back: null, front: null, pairing: false, attempts: 0, refused: [] };
}

async function scan() {
  const video = el("video", { class: "viewfinder", muted: true, playsinline: true, "aria-label": "Camera" });
  const status = el("p", { class: "muted", role: "status" }, "Starting the camera…");
  const manual = manualEntry();
  const view = el("section", { class: "stack" },
    el("h1", {}, "Scan the barcode"),
    el("div", { class: "viewfinder-wrap" }, video, el("div", { class: "frame", "aria-hidden": "true" })),
    status,
    manual,
    button("No barcode? Photograph the ingredients", () => { pending.barcode = null; go("photo"); }, "link"));

  const seq = navSeq;
  if (await barcodeSupported()) {
    startScanner(video, code => lookUp(code)).then(stop => {
      if (seq !== navSeq) return stop();          // the user left before the camera opened
      record("camera", { started: true });
      stopCamera = stop;
      status.textContent = "Point the camera at the barcode on the pack.";
    }).catch(e => {
      record("camera", { started: false, error: String(e?.name || e) });
      video.parentElement.remove();
      status.textContent = "We couldn't open the camera. Type the number under the barcode instead.";
    });
  } else {
    record("camera", { barcode_detector: false });
    video.parentElement.remove();
    status.textContent = "This phone can't read barcodes in the browser. Type the number under the barcode.";
  }
  return view;
}

function manualEntry() {
  const input = el("input", { id: "code", inputmode: "numeric", autocomplete: "off", maxlength: "14",
                              placeholder: "e.g. 8901063010321" });
  const err = el("p", { class: "error", role: "alert" });
  const form = el("form", { class: "row" },
    el("label", { for: "code", class: "sr" }, "Barcode number"),
    input, el("button", { type: "submit", class: "btn" }, "Look up"));
  form.addEventListener("submit", e => {
    e.preventDefault();
    const code = input.value.replace(/\D/g, "");
    if (!validGtin(code)) { err.textContent = "That number doesn't look right. Check the digits under the barcode."; return; }
    lookUp(code, "typed");
  });
  return el("div", {}, form, err);
}

async function lookUp(code, how = "camera") {
  if (stopCamera) { stopCamera(); stopCamera = null; }
  record("barcode", { how, digits: code.length });
  pending.barcode = code;
  show(working("Looking up this pack…", false));
  try {
    const { body } = await scanRequest({ barcode: code });
    finish(body);
  } catch (e) {
    // 404 not_in_catalogue: the normal first-time path, not an error (D-068).
    if (e instanceof ApiError && e.status === 404 && e.body.error === "not_in_catalogue") return go("photo");
    show(apiErrorView(e, () => lookUp(code)));
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

  const picker = (role, label, preview, onPick) => {
    const input = el("input", { type: "file", accept: "image/*", capture: "environment", class: "sr",
                                id: "pick-" + role });
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      preview.replaceChildren(el("p", { class: "muted" }, "Preparing photo…"));
      const blob = await prepareImage(file);
      onPick(blob);
      const url = URL.createObjectURL(blob);
      preview.replaceChildren(el("img", { src: url, alt: `Your ${role} photo` }));
    });
    return el("div", {}, input, el("label", { for: "pick-" + role, class: "btn" }, label));
  };

  return el("section", { class: "stack" },
    el("h1", {}, "Photograph the ingredients"),
    firstTime,
    el("figure", { class: "sample" }, sampleBack(),
      el("figcaption", { class: "muted" }, "Fill the frame with the ingredient list. Hold steady and avoid glare.")),
    picker("back", pending.back ? "Retake the ingredients photo" : "Take the ingredients photo", backPreview,
           b => { pending.back = b; go_.disabled = false; }),
    backPreview,
    el("details", {},
      el("summary", {}, "Add the front of the pack (optional)"),
      el("p", { class: "muted" }, "Helps our team name the product."),
      picker("front", "Take the front photo", frontPreview, b => { pending.front = b; pairRow.hidden = false; }),
      frontPreview, pairRow),
    go_);
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
  const t0 = Date.now();
  const timer = setInterval(() => {
    if (!secs.isConnected) return clearInterval(timer);
    secs.textContent = String(Math.round((Date.now() - t0) / 1000));
  }, 1000);
  return el("section", { class: "stack center", "aria-busy": "true" },
    el("div", { class: "pulse", "aria-hidden": "true" }),
    el("h1", {}, text),
    reading && el("p", { class: "muted" }, "The first read of a pack takes about 8–15 seconds."),
    el("p", { class: "muted", role: "timer" }, secs, " s"));
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
    if (body.scan_id) pending.refused.push(body.scan_id);
  }
  go("result/" + encodeURIComponent(id));
}

// ------------------------------------------------------------------ result (D-060 – D-066)
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
      button("Retake the photo", () => { pending.back = null; go("photo"); }, "primary"),
      pending.attempts >= 2 && el("p", { class: "muted" },
        "Still not working? Try daylight, or another pack. Some labels are printed too small or too shiny to read."),
      // D-070: after two refusals, a person reads the photos instead.
      pending.refused.length >= 2 && button("Send it to us", () => go("send")),
      reportLink(h), problemLink());
    return view;
  }

  // 3. Band (D-063), then what was checked (D-062).
  put(el("div", { class: `band band-${s.band.code}` },
    el("strong", {}, s.band.label),
    s.band.note && el("details", {}, el("summary", {}, "What does this mean?"), el("p", {}, s.band.note))));
  put(el("p", { class: "muted" }, s.checked, " ", s.scope));

  if (s.retake) put(el("div", { class: "card warn" }, el("p", {}, s.retake),
    button("Retake the ingredients photo", () => { pending = { ...pending, back: null, barcode: h.barcode }; go("photo"); })));
  if (s.last_verified) put(el("p", { class: "muted" }, s.last_verified));
  if (s.recheck) put(el("div", { class: "card note" }, el("p", {}, s.recheck),
    button("Photograph the back", () => { resetPending(); pending.barcode = h.barcode; go("photo"); })));

  // 4. Claim check, once released (D-051).
  if (s.claims?.length) {
    put(el("h2", {}, "The front of the pack"),
      el("ul", { class: "plain" }, s.claims.map(c => el("li", { class: c.contradicted ? "flag" : "" }, c.text))));
  }

  // 5. Worth knowing, each with its why one tap away (D-056, D-066).
  if (s.worth_knowing?.length) {
    put(el("h2", {}, "Worth knowing"),
      el("div", { class: "items" }, s.worth_knowing.map(w => el("details", { class: `item concern-${w.concern}` },
        el("summary", {}, w.name),
        el("p", {}, w.why),
        el("p", { class: "muted" }, "On the label: ", el("q", {}, w.label_text)),
        el("p", { class: "tech" }, w.technical)))));
  }

  // 6. Ordinary ingredients, grouped (D-065), then the full list as read.
  if (s.ordinary?.text) {
    put(el("details", { class: "item" },
      el("summary", {}, s.ordinary.text),
      s.ordinary.additives.length > 0 && el("ul", { class: "plain" }, s.ordinary.additives.map(a =>
        el("li", {}, el("strong", {}, a.name), " — ", a.why)))));
  }
  put(el("details", { class: "item" },
    el("summary", {}, "The ingredient list as read"),
    el("ol", {}, s.ingredients.map(i => el("li", {}, i)))));

  if (h.catalogue?.queued_for_review) {
    put(el("p", { class: "muted" },
      "Our team will check this pack. After that, scanning its barcode gives the result straight away."));
  }

  // 7. What this covers — stated, never silent (D-037).
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
  const form = el("form", { class: "stack" },
    el("h1", {}, "Report a mistake"),
    el("p", { class: "muted" }, productName(h.product)),
    el("label", { for: "field" }, "What's wrong?"), field,
    el("label", { for: "said" }, "What does the pack say? (optional)"), said,
    el("label", { for: "note" }, "Anything else? (optional)"), note,
    err,
    el("button", { type: "submit", class: "btn primary" }, "Send to our team"),
    button("Cancel", () => window.history.back(), "link"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await reportRequest({ scan_id: h.scan_id, field: field.value,
                            proposed_value: said.value.trim() || null, note: note.value.trim() || null });
      show(el("section", { class: "stack" }, el("h1", {}, "Thank you"),
        el("p", {}, "Our team will look at the pack. You'll see what they found on the home screen."),
        button("Done", () => go(""), "primary")));
    } catch (ex) {
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online."
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
      el("summary", {}, p.name + (p.id === r.best ? " — better pick" : "")),
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
  if (e.status === 413) return "That photo is too large. Take it again a little further away.";
  if (e.status === 415) return "That file isn't a photo we can read. Use the camera instead.";
  return "Something went wrong on our side. Try again in a minute.";
}

function apiErrorView(e, retry) {
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
