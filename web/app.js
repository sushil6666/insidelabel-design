// app.js - InsideLabel PWA: views and navigation.
//
// The result screen is rendered from the `screen` block that /scan returns
// (src/insidelabel/lenses/screen.py). This file adds layout and buttons, not
// judgements: no score is shown (D-064), no band is renamed here (D-063), and
// every sentence about the pack comes from the server, where the wording lint
// checks it (D-042). Text in this file is linted too (tests/test_web.py).

import {
  AGES, APP_VERSION, MAX_PROFILES, ApiError, addHistory, allergenList, answerBand, bandToAsk, clientInfo,
  compareRequest,
  deviceId, el, fill, history, historyItem, lastIncident, prepareImage, problemRequest, profileByRef,
  profiles, record, reportRequest, saveProfiles, scanRequest, sendToUsRequest, store, trailSnapshot,
  accessRequest, agreeRequest, checkPhotoRequest, feedbackRequest, termsRequest,
  updatesRequest, forgetRequest, clearTrail, packPhoto, savePackPhoto, sidePhotoRequest, saveSidePhoto,
} from "./lib.js";
import { barcodeSupported, labelCameraSupported, startLabelCamera, startScanner } from "./camera.js";
import { icon, kindIcon, spot } from "./icons.js";

const main = document.getElementById("main");
let stopCamera = null;
let liveShutter = false;      // D-171: the server's switch for the app's own label shutter (/access)
let navSeq = 0;               // async views check this so a late result can't replace a newer page
// The scan in progress: barcode (if read), photos, and how many times it was refused
// (with the refused scans' ids, for "Send it to us", D-070).
// frontWanted: offer the front photo (D-100); off for a re-check of a pack whose front is on file.
// acceptUnconfirmed: "use this one anyway" after a request for a clearer photo (D-118).
// parts: the ingredient list's 2nd and 3rd photos, when it doesn't fit one (D-119), or the
// nutrition table's photo; partKinds says which ("list" or "table", D-171).
// barcodeAnswer: "confirmed" or "rescanned", the answer to D-146's digit check; rescanned:
// the user tapped "Scan again" on an earlier code for this pack.
let pending = { barcode: null, barcodeSource: null, back: null, front: null, backSource: null,
                frontSource: null, pairing: false, attempts: 0, refused: [], frontWanted: true,
                acceptUnconfirmed: false, parts: [], partSources: [], partKinds: [],
                screenPack: null, shopItem: null, barcodeAnswer: null, rescanned: false, recheck: false };

// ------------------------------------------------------------------ navigation
const routes = {
  "": home, welcome, who, household, person, scan, photo, front, result, report, compare, problem, send,
  agree, feedback, data, table, tablephoto, scans, listpart, side,
};

// D-176: the app's frame around each screen. Home and the first-run screens show the wordmark
// (D-152); every other screen shows its name in the header and a back arrow. The bottom bar is
// on every screen but the first-run ones and the camera and photo steps, where it would cover
// the shutter or pull a hand away from the pack.
const TITLES = {
  household: "Household", person: "Household", scan: "Scan", photo: "Photo", front: "Photo", listpart: "Photo", side: "Photo",
  table: "Nutrition table", tablephoto: "Nutrition table", result: "Result", report: "Report a mistake",
  compare: "Compare", problem: "Report a problem", send: "Send it to us", feedback: "Send feedback",
  data: "Your data", scans: "Your scans",
};
const FIRST_RUN = ["welcome", "who", "agree"];
const NO_TABBAR = [...FIRST_RUN, "scan", "photo", "front", "table", "tablephoto", "listpart", "side"];
let screenName = "home";      // the screen being shown, set by route() before its view is built
let routed = 0;               // screens shown since the app opened: Back goes home from the first

// Setting the hash it already has fires no hashchange, so the page wouldn't
// change (e.g. "Skip for now" on a welcome shown at #/ after joining).
function go(path) {
  const hash = "#/" + path;
  if (location.hash === hash) route();
  else location.hash = hash;
}

// app-polish: which way the next screen enters. A tile's page comes in from the right
// (deeper); its result, returned to, doesn't move; everything else rises a little.
let enterFrom = "up";
let lastSub = "";

function route() {
  if (stopCamera) { stopCamera(); stopCamera = null; }
  const [name, arg, ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  const sub = rest.join("/");
  routed++;
  enterFrom = sub.startsWith("look") ? "right" : lastSub.startsWith("look") && name === "result" ? "back" : "up";
  lastSub = sub;
  // D-092: screens in the trail. `arg` is a scan id or a profile ref, never a name;
  // `sub` a result's own page (D-134: "look/<tile id>").
  record("route", { to: name || "home", arg: arg || undefined, sub: rest.join("/") || undefined });
  if (name !== "feedback") store.set("lastScreen", name || "home");     // where feedback was sent from
  // D-105: "Before you start": the rules are agreed before anything else.
  if (!["agree", "problem", "data"].includes(name)) {
    const seq = ++navSeq;
    return checkAccess().then(a => {
      if (seq !== navSeq) return;
      if (a.needAgree) { screenName = "agree"; return show(agree()); }
      routeAfterAgree(name, arg, rest);
    });
  }
  routeAfterAgree(name, arg, rest);
}

function routeAfterAgree(name, arg, rest = []) {
  if (!store.get("welcomed", false) && !["welcome", "who", "household", "person", "agree", "data"].includes(name)) {
    screenName = "welcome";
    return show(welcome());
  }
  screenName = routes[name] ? name || "home" : "home";
  const seq = ++navSeq;
  const view = routes[name] || home;
  const out = view(arg && decodeURIComponent(arg), ...rest.map(decodeURIComponent));
  Promise.resolve(out).then(node => { if (seq === navSeq) show(node); });
  updateNav();
}

// app-polish (docs/APP_DESIGN.md 8.6): the first screen paints at once; later ones enter
// with a 200 ms rise or slide (transform and opacity only, interactive from the first
// frame, and the next screen simply replaces it). A result's people block never moves
// (D-060): it is there at once and the blocks after it follow, 40 ms apart.
let shownOnce = false;
function show(node) {
  if (!node) return;
  if (shownOnce && node instanceof Element) {
    if (node.classList.contains("result")) { if (enterFrom !== "back") revealAfterPeople(node); }
    else if (enterFrom !== "back") node.dataset.enter = enterFrom;
  }
  shownOnce = true;
  frame(node instanceof Element ? node.dataset.back : null, node instanceof Element ? node.dataset.backLabel : null,
        node instanceof Element ? node.backTo : null);
  main.replaceChildren(node);
  // The footer shows once a screen is in place (CLS). A screen still loading its words
  // (aria-busy, e.g. "Before you start" on a first visit) calls settled() when they're in:
  // shown under "Loading…", the footer jumped down when the terms arrived (D-153 step 2).
  if (!(node instanceof Element && node.getAttribute("aria-busy") === "true")) settled();
  window.scrollTo(0, 0);
  const h = main.querySelector("h1, h2");
  if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
}

function settled(view) {
  if (view) view.removeAttribute("aria-busy");
  document.body.classList.add("ready");
}

// D-176: the header and the bottom bar for the screen in screenName. A result's own page (D-134)
// goes back to its result; a result goes home (the photo steps behind it are done); any other
// screen goes where the phone's Back would, or home when it is the first screen opened.
// backTo: a screen shown in place (a camera step) says where its arrow goes, so the arrow
// returns to the photos in hand instead of leaving the scan (Sushil, 2026-10-08: no loose
// "Back" links on the camera pages).
function frame(href, label, backTo = null) {
  const name = screenName;
  // D-180 (Sushil): the wordmark stays in the centre on every screen; an inner screen (one with a
  // name in TITLES) gets the back arrow beside it, never its name in the wordmark's place.
  const title = FIRST_RUN.includes(name) ? null : TITLES[name] || null;
  const slot = document.getElementById("top-left");
  if (slot) {
    let back = "";
    if (backTo) back = el("button", { type: "button", class: "top-back", "aria-label": "Back", onclick: backTo }, icon("back"));
    else if (href) back = el("a", { class: "top-back", href, "aria-label": label || "Back" }, icon("back"));
    else if (name === "result") back = el("a", { class: "top-back", href: "#/", "aria-label": "Back to home" }, icon("back"));
    else if (title) back = el("button", { type: "button", class: "top-back", "aria-label": "Back",
      onclick: () => { if (routed > 1) window.history.back(); else go(""); } }, icon("back"));
    slot.replaceChildren(back);
  }
  const bar = document.getElementById("tabbar");
  if (bar) bar.hidden = NO_TABBAR.includes(name);
  // The bottom bar and, from 1024 px, the header's places (D-185) mark the screen in view.
  for (const a of document.querySelectorAll("a[data-tab]")) {
    const here = a.dataset.tab === name || (a.dataset.tab === "household" && name === "person");
    if (here) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  document.body.classList.toggle("has-tabbar", !NO_TABBAR.includes(name));
  document.body.classList.toggle("at-home", name === "home");
  document.body.dataset.screen = name;                      // D-185: desktop widths per screen (app.css)
}

function revealAfterPeople(view) {
  let i = 0;
  for (const c of view.children) {
    if (c.matches(".product, .rescan, .people, .result-top")) continue;
    c.classList.add("reveal");
    c.style.setProperty("--i", String(Math.min(i++, 6)));
    // D-185 Phase 2 (Sushil, 2026-10-08: "result cards arriving"): a tab's own blocks arrive one after
    // another, after the headline and the tabs.
    if (c.matches(".tab-panel")) {
      let j = 0;
      for (const card of c.children) card.style.setProperty("--j", String(Math.min(j++, 5)));
    }
  }
}

function updateNav() {
  const n = store.get("compare", []).filter(x => comparable(historyItem(x))).length;   // D-202: never an infant pack
  // D-176: the bottom bar's Compare count; D-185: the header's too.
  for (const badge of document.querySelectorAll("[data-compare-count]")) {
    badge.textContent = n ? String(n) : "";
    badge.hidden = !n;
  }
}

// D-201 (Sushil, accepting): the brand shows only when the name doesn't already contain it, case
// and spacing ignored: "Amulspray" + "Amulspray" is "Amulspray", "Amul" + "Amul Butter" is "Amul
// Butter", "Britannia" + "Good Day" stays "Britannia Good Day". Every screen names a pack with it.
function productName(product) {
  const p = product || {};
  const flat = s => String(s || "").toLowerCase().replace(/\s+/g, "");
  const brand = p.brand && !(p.name && flat(p.name).includes(flat(p.brand))) ? p.brand : null;
  return [brand, p.name, p.variant].filter(Boolean).join(" ") || "Unnamed pack";
}

function button(label, onclick, cls = "") {
  return el("button", { type: "button", class: "btn " + cls, onclick }, label);
}

// ------------------------------------------------------------------ before you start (D-105)
// Asked once per session. D-184: no invite codes; /access says whether this phone
// agreed to the current rules and carries the app's switches (D-171).
let accessChecked = null;
function checkAccess() {
  if (!accessChecked) {
    accessChecked = accessRequest().then(({ body }) => {
      store.set("termsVersion", body.terms_version);
      liveShutter = !!body.live_shutter;                                 // D-171
      // D-105: agreed on the server, or (a server without a database) on this phone.
      const needAgree = !body.agreed && store.get("agreed", null) !== body.terms_version;
      return { needAgree };
    }).catch(() => ({                // offline: open the app
      needAgree: !store.get("agreed", null),
    }));
  }
  return accessChecked;
}

function agree() {
  const view = el("section", { class: "stack", "aria-busy": "true" }, el("p", { class: "muted" }, "Loading…"), skeleton(5));
  termsRequest().then(({ body: t }) => {
    const box = el("input", { type: "checkbox", id: "agree" });
    const err = errorLine();
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
      accessChecked = Promise.resolve({ needAgree: false });
      go("");
    });
    view.replaceChildren(
      el("h1", {}, t.title),
      el("p", { class: "lead" }, t.intro),
      el("ol", { class: "rules" }, t.points.map(p => el("li", {}, p))),
      // Sushil, 2026-10-08: what a good photo looks like, as a suggestion (the server's words).
      t.examples && el("section", { class: "examples" },
        el("h2", {}, t.examples.title),
        el("div", { class: "example-row" }, t.examples.items.map(x => exampleShot(x.kind, x.label))),
        el("p", { class: "muted small" }, t.examples.note)),
      el("label", { class: "choice", for: "agree" }, box, " " + t.agree_label),
      err, go_);
    settled(view);
  }).catch(e => { view.replaceChildren(apiErrorView(e, () => show(agree()))); settled(view); });
  return view;
}

function feedback() {
  const from = store.get("lastScreen", "home");
  const comment = el("textarea", { id: "fb", maxlength: "4000", rows: "5", required: true });
  const err = errorLine();
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
    button("Cancel", () => window.history.back(), "link end"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const text = comment.value.trim();
    if (!text) { err.textContent = "Write a few words first."; return; }
    try {
      await feedbackRequest({ comment: text, rating, screen: from });
      show(el("section", { class: "stack done-step" }, doneSpot(), el("h1", {}, "Thank you"),
        el("p", {}, "We read every note. It shapes what we build next."),
        button("Done", () => go(""), "primary")));
    } catch (ex) {
      err.textContent = ex.status === 0 ? "No connection. Try again when you're online." : apiMessage(ex);
    }
  });
  return form;
}

// ------------------------------------------------------------------ first run (D-069, D-074)
function welcome() {
  return el("section", { class: "stack" },
    // D-185: the first screen shows what a scan does, with the drawing from home's "Scan here".
    el("div", { class: "welcome-art", "aria-hidden": "true" }, scanLoop()),
    el("h1", {}, "See what's inside the pack"),
    el("p", { class: "lead" },
      "Scan a barcode, or photograph the ingredient list. We tell you what's in it, " +
      "starting with anything on your family's avoid list."),
    el("ul", { class: "plain points" },
      el("li", {}, "An AI reads the label. Fixed rules, based on FSSAI regulations, make every judgement."),
      el("li", {}, "Nicknames you add stay on this phone. Our server only sees an age band and an avoid list."),
      el("li", {}, "It shows ingredient facts, not medical advice.")),
    // D-127: ask the question people can answer, not "set up your household".
    el("div", { class: "card note" },
      el("h2", {}, "Does anyone you shop for avoid a food, like peanut, milk or gluten?"),
      el("p", { class: "muted" }, "We check every pack for it first. You can change this any time."),
      el("div", { class: "row wrap" },
        button("Yes", () => { store.set("welcomed", true); go("who"); }, "primary"),
        button("No", () => { store.set("welcomed", true); go(""); }))));
}

// D-127: who the avoid list is for. Adults other than you aren't profiles (D-074).
function who() {
  return el("section", { class: "stack" },
    el("h1", {}, "Who avoids it?"),
    button("Me", () => go("person/me"), "primary"),
    profiles().length < MAX_PROFILES && button("A child I shop for", () => go("person/new")),
    el("p", { class: "muted" }, "You can add more people afterwards, up to " + MAX_PROFILES + " including you."),
    button("Done", () => go(""), "link end"));
}

// ------------------------------------------------------------------ home
async function home() {
  const done = history().filter(h => h.screen?.state === "result").length;
  // D-185: six on a desktop, where the recent scans fill their own column.
  const recent = history().slice(0, matchMedia("(min-width: 1024px)").matches ? 6 : 5);
  const updates = el("div", {});
  loadUpdates(updates);

  // site-desktop (Sushil, 2026-10-02): one wide "Scan here" bar, nothing above it but the
  // header; it opens what "Scan a pack" opened. Everything else follows in the same order.
  // D-185: two columns from 1024 px; the recent scans take the second.
  return el("section", { class: "stack home" },
    el("div", { class: "home-a stack" },
      playWhileSeen(el("button", { type: "button", class: "scan-cta", onclick: () => { resetPending(); go("scan"); } },
        el("span", { class: "scan-cta-words" },
          el("span", { class: "scan-cta-title" }, "Scan here"),
          el("span", { class: "scan-cta-icon", "aria-hidden": "true" }, icon("forward"))),
        scanLoop())),
      updates,
      checkingFor(),
      shopListCard(),
      done < 3 && startAtHome(done)),     // D-185: the counts (yourScans) live on Your scans
    recent.length > 0 && el("div", { class: "home-b stack" },
      el("div", { class: "section-head" },
        el("h2", {}, "Recent scans"),
        history().length > recent.length && el("a", { href: "#/scans" }, "See all")),
      scanList(recent)));
}

// D-185: the drawing on "Scan here" (app.css .loop): a pack's barcode swept, its label read in the
// logo's gold, a result card with a tick. Decoration only, so hidden from screen readers.
function scanLoop() {
  const tick = icon("check");                            // its stroke is 1 long (icons.js), so it draws in
  return el("span", { class: "loop", "aria-hidden": "true" },
    el("span", { class: "pk" }, el("span", { class: "bars" }), el("span", { class: "sweep" }),
      ...[1, 2, 3].map(n => el("span", { class: "ln ln" + n }, el("i", {})))),
    el("span", { class: "res" }, el("span", { class: "tick" }, tick), el("span", { class: "rl" }, el("i", {}), el("i", {}))));
}

// "Start at home" (D-178), D-185: compact; the three packs as three segments that fill in.
function startAtHome(done) {
  return el("div", { class: "card start" },
    el("h2", {}, "Start at home"),
    el("span", { class: "start-count muted" }, `${done} of 3 done`),
    el("p", { class: "muted" }, "Scan 3 packs from your kitchen. You'll see how it works without a trip to the shop."),
    el("div", { class: "segs", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "3",
                "aria-valuenow": String(done), "aria-label": "Start at home" },
      [0, 1, 2].map(i => el("i", { class: i < done ? "on" : "" }))));
}

// D-178: who every pack is checked for, on home, with a way to change it. Nicknames stay on
// this phone (D-074); the avoid list is named with the server's own allergen labels.
// D-178 follow-up (Sushil, 2026-10-08): one short line per person, "You · 9 to avoid"; a tap
// opens that person's list underneath. <details> gives the keyboard and screen readers the
// open and close; closed on every visit, nothing remembered.
function checkingFor() {
  const list = profiles();
  const line = p => [avatar(p), el("span", { class: "who-name" }, p.nickname),
    el("span", { class: "who-count muted" }, p.avoid.length ? `· ${p.avoid.length} to avoid` : "· no avoid list")];
  return el("div", { class: "card checking" },
    el("div", { class: "section-head" },
      el("h2", {}, "Checking for"),
      el("a", { href: "#/household" }, "Edit")),
    el("ul", { class: "who-chips" }, list.map(p => el("li", {},
      p.avoid.length
        ? el("details", { class: "who" }, el("summary", {}, ...line(p)),
            el("p", { class: "who-avoid muted" }, avoidNames(p.avoid).join(", ")))
        : el("div", { class: "who-line" }, ...line(p))))));
}

function avatar(p) {
  return el("span", { class: "avatar av-" + p.ref, "aria-hidden": "true" }, (p.nickname || "?").trim().charAt(0).toUpperCase());
}

// The labels saved the last time the allergen list was loaded (the avoid-list form loads it);
// before that, the code itself.
function avoidNames(codes) {
  const known = new Map([...(store.get("allergens", null) || []), ...(store.get("diets", null) || [])]
    .map(a => [a.code, a.label]));
  return codes.map(c => known.get(c) || c.replace(/_/g, " "));
}

// D-178: a scan as a card: the user's own photo of the pack (D-177) or a drawn pack, the
// name, the server's chips or first person line (D-091), and when it was scanned.
function scanList(items) {
  return el("ul", { class: "scan-cards" }, items.map((h, i) =>
    el("li", { style: `--i:${Math.min(i, 5)}` }, el("a", { class: "scan-card", href: `#/result/${encodeURIComponent(h.id)}` },
      packThumb(h),
      el("span", { class: "scan-text" },
        el("strong", {}, productName(h.product)),
        scanPerson(h.screen),
        h.screen?.summary?.length
          ? el("span", { class: "chips" }, cardChips(h.screen.summary).map(toneChip))
          : el("span", { class: "muted" }, peopleSummary(h.screen) || h.screen?.headline?.text || ""),
        h.at && el("span", { class: "scan-when" }, whenText(h.at)))))));
}

// D-188: a scan card names a match (or a line we can't confirm) for the first person it concerns,
// in the result's colour; a person with no match isn't named.
function scanPerson(screen) {
  const p = cardPeople(screen).find(x => x.status !== "worth_knowing");     // an allergen line only
  if (!p || !screen.summary?.length) return null;          // without chips, peopleSummary says it
  const who = profileByRef(p.ref);
  return el("span", { class: `scan-person ${PERSON_TONE[p.status] || "calm"}` },
    who && el("b", {}, who.nickname + " "), fill(p.line, p.ref));
}

// D-185: a card shows at most two of the server's chips, those worth a look first, in the server's
// order (D-123); the result shows all three.
function cardChips(summary) {
  const worth = summary.filter(r => r.tone === "worth");
  return (worth.length ? worth : summary).slice(0, 2);
}

function packThumb(h) {
  const src = h?.photo || packPicture(h)?.url;
  return el("span", { class: "scan-thumb", "aria-hidden": "true" },
    src ? el("img", { src, alt: "" }) : icon("pack"));
}

// D-182: the pack picture the server sends for a catalogue pack (a reviewed photo of its front),
// used only when this phone kept no photo of its own. The server words its alt text and caption.
function packPicture(h) {
  return h?.photo ? null : h?.screen?.pack_picture || null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function whenText(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  return days === 0 ? "Today" : days === 1 ? "Yesterday" : `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// D-176: the bottom bar's "Your scans": every result kept on this phone (D-074), newest first,
// under D-123's counts.
function scans() {
  const all = history();
  return el("section", { class: "stack" },
    el("h1", {}, "Your scans"),
    yourScans(),
    all.length
      ? scanList(all)
      : el("div", { class: "card empty" }, spot("pack", "barcode"),
          el("p", {}, "Nothing scanned yet. Your results stay on this phone."),
          button("Scan a pack", () => { resetPending(); go("scan"); }, "primary")));
}

// D-130: packs planned from a screen, to scan from the pack in the shop. Kept
// on this phone only, like history (D-074); the server sees one list at a time,
// when "Scan it now" sends it with the pack.
function shopList() { return store.get("shoplist", []); }

function shopListCard() {
  const items = shopList();
  if (!items.length) return null;
  return el("div", { class: "card" },
    el("h2", {}, "Your shop list"),
    el("p", { class: "muted" }, "Checked from a screen. Scan each pack in the shop to confirm."),
    el("ul", { class: "list" }, items.map(x => el("li", {},
      el("a", { href: `#/result/${encodeURIComponent(x.id)}` }, el("strong", {}, productName(x.product))),
      el("div", { class: "row wrap" },
        button("Scan it now", () => {
          resetPending();
          pending.screenPack = x.pack;
          pending.shopItem = x.id;
          go("scan");
        }, "primary"),
        button("Remove", () => { store.set("shoplist", shopList().filter(y => y.id !== x.id)); route(); }, "link"))))));
}

// D-123: what came up across this phone's own results. Counted here, worded on
// the server (screen.tallies, D-091); nothing is sent anywhere (D-074).
function yourScans() {
  const done = history().filter(h => h.screen?.state === "result" && Array.isArray(h.screen.tallies));
  if (done.length < 2) return null;
  const counts = new Map();
  done.forEach(h => h.screen.tallies.forEach(t => counts.set(t, (counts.get(t) || 0) + 1)));
  const rows = [...counts].sort((a, b) => b[1] - a[1]);
  // D-185: on Your scans only, under its own title, so the card doesn't repeat it.
  return el("div", { class: "card tallies-card" },
    el("p", { class: "muted" }, `${done.length} packs checked, kept on this phone.`),
    rows.length
      ? el("div", { class: "tallies" }, rows.map(([label, n]) => el("div", { class: "tally" },
          el("div", { class: "row between" }, el("span", {}, label), el("span", { class: "muted" }, `${n} of ${done.length}`)),
          el("div", { class: "progress" }, el("span", { style: `width:${(n / done.length) * 100}%` })))))
      : el("p", {}, "Nothing came up often enough to list yet."));
}

function peopleSummary(screen) {
  const p = cardPeople(screen)[0];
  return p ? fill(p.line, p.ref) : "";
}

// D-188: the people with a card: a match, a line we can't confirm, or a child's age line. A result
// kept on this phone from before web-66 still lists everyone; its "not listed" lines don't show.
function cardPeople(screen) {
  return (screen?.people || []).filter(p => CARD.includes(p.status));
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
// D-129 "Your data": what we keep, this phone's id, and "Delete my data"
// (DPDP Act s.12(3)). Works before "Before you start": anyone can erase.
function data() {
  const err = errorLine();
  const confirmBox = el("div", { class: "stack", hidden: true },
    el("p", {}, el("strong", {}, "Delete everything we keep about this phone?")),
    el("p", {}, "We delete your feedback, problem reports, any invite link and the photos you took. Your scans " +
      "lose any link to this phone and to your household. A pack you helped add to our catalogue stays in " +
      "it, with nothing that points to you."),
    el("p", {}, "This phone's household and scan history are cleared too."),
    err,
    button("Delete my data", async e => {
      e.target.disabled = true;
      err.textContent = "";
      try {
        await forgetRequest();
      } catch (ex) {
        e.target.disabled = false;
        err.textContent = apiMessage(ex);
        return;
      }
      store.clear();
      clearTrail();
      show(el("section", { class: "stack" }, el("h1", {}, "Deleted"),
        el("p", {}, "Everything we kept about this phone is deleted, and this phone's InsideLabel data is cleared."),
        button("Close", () => { location.hash = "#/"; location.reload(); }, "primary")));
    }, "danger"),
    button("Cancel", () => { confirmBox.hidden = true; ask.hidden = false; }, "link"));
  const ask = button("Delete my data", () => { confirmBox.hidden = false; ask.hidden = true; }, "danger");
  return el("section", { class: "stack" },
    el("h1", {}, "Your data"),
    el("p", {}, "On our server, linked to this phone: your pack photos (deleted after 30 days), your scans and " +
      "the household ages and avoid lists sent with them (unlinked after 30 days), and any feedback or " +
      "problem reports you sent (deleted after 12 months)."),
    el("p", {}, "Only on this phone: nicknames, your scan history and your household."),
    el("p", { class: "muted" }, "This phone's id: ", el("code", {}, deviceId()),
      ". Quote it if you write to us at ", el("a", { href: "mailto:connect@insidelabel.ai" }, "connect@insidelabel.ai"),
      "."),
    el("p", {}, el("a", { href: "/privacy" }, "Privacy")),
    el("p", { class: "muted" }, `App version: ${APP_VERSION}`),        // 2026-10-14: one tap to check an update
    ask, confirmBox,
    button("Done", () => go(""), "link end"));
}

function household() {
  const list = profiles();
  return el("section", { class: "stack" },
    el("h1", {}, "Your household"),
    el("p", { class: "muted" },
      `Up to ${MAX_PROFILES} people, including you. Nicknames stay on this phone.`),
    // D-178: a card per person: their initial, age band and avoid list as chips.
    el("ul", { class: "people" }, list.map((p, i) => el("li", { style: `--i:${i}` },
      el("a", { class: "person-card", href: `#/person/${p.ref}` },
        avatar(p),
        el("span", { class: "person-text" },
          el("strong", {}, p.nickname),
          el("span", { class: "muted" }, p.age === "adult" ? "Adult" : AGES.find(a => a.id === p.age)?.label),
          p.avoid.length
            ? el("span", { class: "chips" }, avoidNames(p.avoid).map(n => el("span", { class: "chip avoid-chip" }, n)))
            : el("span", { class: "muted" }, "No avoid list")))))),
    list.length < MAX_PROFILES && el("button", { type: "button", class: "add-card", onclick: () => go("person/new") },
      icon("plus"), "Add a child"),
    button("Done", () => go(""), "link end"));
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
  const err = errorLine();

  form.append(...[
    el("h1", {}, isMe ? "What do you avoid?" : isNew ? "Add a child" : `Edit ${p.nickname}`),
    !isMe && el("label", { for: "nick" }, "Nickname (stays on this phone)"),
    nameInput,
    !isMe && el("fieldset", {},
      el("legend", {}, "Age"),
      AGES.map(a => el("label", { class: "choice" },
        el("input", { type: "radio", name: "age", value: a.id, checked: p.age === a.id,
                      onchange: () => { p.age = a.id; } }),
        ` ${a.label} `, el("span", { class: "muted" }, a.sub)))),
    el("fieldset", {},
      el("legend", {}, isMe ? "Foods you avoid" : "Foods this child avoids"),
      el("p", { class: "muted" }, "We check every pack for these first and put the answer at the top of the result. "
        + "We only report what the label prints, so read the pack too. ",
        el("a", { href: "/how#avoid", target: "_blank", rel: "noopener" }, "How we check")),
      allergens.map(a => el("label", { class: "choice" },
        el("input", { type: "checkbox", value: a.code, checked: p.avoid.includes(a.code),
                      onchange: e => {
                        p.avoid = e.target.checked ? [...p.avoid, a.code] : p.avoid.filter(c => c !== a.code);
                      } }),
        el("span", {}, a.label,
          !a.fssai_mandatory && el("span", { class: "muted" }, " (brands don't have to declare it)")))),
      // D-198: two diet choices after the allergens, in the same avoid list (Sushil, 2026-10-11).
      (store.get("diets", null) || []).length > 0 && el("p", { class: "choice-group muted" }, "Diet"),
      (store.get("diets", null) || []).map(d => el("label", { class: "choice" },
        el("input", { type: "checkbox", value: d.code, checked: p.avoid.includes(d.code),
                      onchange: e => {
                        p.avoid = e.target.checked ? [...p.avoid, d.code] : p.avoid.filter(c => c !== d.code);
                      } }),
        el("span", {}, d.label)))),
    !isMe && el("label", { class: "choice consent" }, consent,
      " I am this child's parent or guardian. I agree to InsideLabel using this age band and " +
      "avoid list to check labels for them."),
    err,
    el("button", { type: "submit", class: "btn primary dock" }, "Save"),     // D-185: in thumb reach
    !isNew && !isMe && button("Remove", () => {
      saveProfiles(profiles().filter(x => x.ref !== p.ref));
      go("household");
    }, "link danger"),
    button("Cancel", () => go("household"), "link end"),
  ].flat().filter(x => x != null && x !== false));

  form.addEventListener("submit", e => {
    e.preventDefault();
    if (!isMe) {
      p.nickname = nameInput.value.trim();
      if (!p.nickname) { err.textContent = "Add a nickname."; return; }
      if (!consent.checked) { err.textContent = "Tick the parent or guardian box to save."; return; }
      p.consent_at = p.consent_at || new Date().toISOString();
      p.under2_asked = true;          // D-140: the age was chosen from the bands as they are now
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
              acceptUnconfirmed: false, parts: [], partSources: [], partKinds: [],
              screenPack: null, shopItem: null, barcodeAnswer: null, rescanned: false, recheck: false };
}

// D-146: back to the scanner after a code the user says isn't this pack's. The dropped
// code isn't kept anywhere; the next code is sent as "rescanned".
function scanAgain() {
  pending.barcode = null;
  pending.barcodeSource = null;
  pending.barcodeAnswer = null;
  pending.rescanned = true;
  record("barcode_check", { answer: "scan_again" });
  go("scan");
}

async function scan() {
  const video = el("video", { class: "viewfinder", muted: true, playsinline: true, "aria-label": "Camera" });
  // D-185 Phase 2: the camera's one line sits on the camera, where the eye already is.
  const status = el("p", { class: "cam-status", role: "status" }, "Starting the camera…");
  // D-104: a barcode comes from the live scanner or from a photo read on the
  // server, never typed: a mistyped number would file a pack under someone
  // else's product.
  const preview = el("div", { class: "thumb" });
  const next = el("div", {});
  // app-polish: corner guides say where the barcode goes; a slow gold line says the camera is looking.
  const cam = el("div", { class: "viewfinder-wrap scan-cam" }, video,
    el("div", { class: "frame", "aria-hidden": "true" }, el("i", {}), el("i", {}), el("i", {}), el("i", {}),
      el("span", { class: "scanline" })),
    status);
  const view = el("section", { class: "stack scan-step" },
    stepLine(1, "Barcode"),                                       // D-171
    el("h1", {}, "Scan the barcode"),
    playWhileSeen(cam),
    // D-185 Phase 2: the two other ways in, as two quiet buttons under the camera. D-107: a pack
    // without a barcode can still be checked from its ingredients photo; it just isn't added to the
    // catalogue. Kept first, where it's seen.
    el("div", { class: "scan-alt" },
      button("No barcode? Photograph the ingredients", () => { pending.barcode = null; go("photo"); }),
      photoPicker("barcode", "Take a photo of the barcode", preview, (_blob, res) => {
        next.replaceChildren();
        if (res?.ok && res.barcode) {
          next.append(button("Look up this pack", () => lookUp(res.barcode, "photo"), "primary"));
        }
      })),
    preview,
    next);
  // No live scanner here: a drawing of a barcode takes the camera's place, so the line under it
  // still has something to point at; the gold line stays still (nothing is being read).
  const drawn = text => {
    video.replaceWith(el("div", { class: "scan-drawn", "aria-hidden": "true" }, el("span", { class: "bars" })));
    cam.classList.add("drawn");
    status.textContent = text;
  };

  const seq = navSeq;
  if (await barcodeSupported()) {
    // 2026-10-14: a still the phone can't read goes to the server's barcode reader, as a barcode photo.
    const onStill = async blob => {
      try { return (await checkPhotoRequest("barcode", blob)).body?.barcode || null; } catch { return null; }
    };
    startScanner(video, code => lookUp(code, "camera"), onStill).then(stop => {
      if (seq !== navSeq) return stop();          // the user left before the camera opened
      record("camera", { started: true });
      stopCamera = stop;
      status.textContent = "Point the camera at the barcode on the pack.";
      // 2026-10-14: the zoom steps by itself until a read (camera.js); this says where it is.
      if (stop.zoom) {
        const z = el("span", { class: "cam-zoom", "aria-hidden": "true" }, `${stop.zoom}x`);
        stop.onZoom = level => { z.textContent = `${level}x`; };
        cam.append(z);
      }
      // D-124: a light for dim shelves, and help if nothing reads after a while.
      if (stop.hasTorch) {
        let on = false;
        const t = el("button", { type: "button", class: "cam-light", "aria-pressed": String(on) },
          icon("torch"), el("span", {}, "Turn on the light"));
        t.addEventListener("click", async () => {
          if (await stop.torch(!on)) {
            on = !on;
            t.setAttribute("aria-pressed", String(on));
            t.lastChild.textContent = on ? "Turn off the light" : "Turn on the light";
          }
        });
        cam.append(t);
      }
      setTimeout(() => {
        if (seq === navSeq && stopCamera === stop) {
          // 2026-10-14: the camera zooms by itself, so the person only holds still.
          status.textContent = "Keep the barcode inside the box and hold still: the camera zooms in by itself. "
            + "Or take a photo of the barcode below.";
        }
      }, 8000);
    }).catch(e => {
      record("camera", { started: false, error: String(e?.name || e) });
      drawn("We couldn't open the camera here. Take or upload a photo of the barcode instead.");
    });
  } else {
    record("camera", { barcode_detector: false });
    drawn("This browser can't read barcodes live. Take or upload a photo of the barcode instead.");
  }
  return view;
}

async function lookUp(code, how) {
  if (stopCamera) { stopCamera(); stopCamera = null; }
  record("barcode", { how, digits: code.length });
  pending.barcode = code;
  pending.barcodeSource = how;
  show(working("Looking up this pack…", false, null, "barcode"));
  try {
    const { body } = await scanRequest({ barcode: code, barcodeSource: how, screenPack: pending.screenPack,
                                         barcodeAnswer: pending.rescanned ? "rescanned" : null });
    finish(body, { lookedUp: true });
  } catch (e) {
    // 404 not_in_catalogue: the normal first-time path, not an error (D-068). D-146:
    // the digits are checked against the pack first; an older server sends no check.
    if (e instanceof ApiError && e.status === 404 && e.body.error === "not_in_catalogue") {
      return e.body.barcode_check ? show(digitCheck(e.body.barcode_check)) : go("photo");
    }
    show(apiErrorView(e, () => lookUp(code, how)));
  }
}

// D-146: a code for a pack we haven't checked, shown back before the ingredients photo,
// its first 3 and last 4 digits large. Every word is the server's (lenses/screen.py, D-091).
function digitCheck(c) {
  return el("section", { class: "stack digit-check" },
    stepLine(1, "Barcode"),                                       // D-185 Phase 2: still step 1
    el("h1", {}, c.title),
    el("p", {}, c.text),
    el("p", { class: "digits", "aria-label": c.code },
      el("span", { class: "big" }, c.first), el("span", { class: "small" }, c.middle),
      el("span", { class: "big" }, c.last)),
    el("div", { class: "dock" },                                  // D-185 Phase 2: in thumb reach
      button(c.yes, () => {
        pending.barcodeAnswer = pending.rescanned ? "rescanned" : "confirmed";
        record("barcode_check", { answer: pending.barcodeAnswer });
        go("photo");
      }, "primary"),
      button(c.again, scanAgain)));
}

// ------------------------------------------------------------------ scan: the label photos (D-025, D-068, D-171)
// D-171 (a tester via Sushil, 2026-10-07): the barcode step was clear, the one long label page
// was not. So the label is taken in steps, one job per screen: the ingredient list (step 2),
// then, only if it isn't in that photo, the nutrition table (step 3). D-119's extra parts of
// a long list stay possible. Every photo goes to the server as today (back, back2, back3) and
// the pack is read once. D-181 (Sushil, 2026-10-08, "make the front photo mandatory"): while the
// catalogue wants this pack's front (D-100), the front is the last step, and "Check this pack"
// waits for it and for D-035's "same pack" box.
// The camera: the app's own live view and shutter where the server has it switched on
// (/access live_shutter) and the phone can take a full-size still; otherwise the phone's
// camera app, as before.
const MAX_PHOTOS = 3;                    // D-119's limit: back, back2, back3
// D-181: the front is required while the catalogue wants it (off for a re-check of a pack
// whose front is on file, and for D-175's list-only re-check).
const frontNeeded = () => !!pending.frontWanted;
const steps = () => frontNeeded() ? 4 : 3;

// D-185 Phase 2: the steps as dots; the current one is a pill that moves over from the step before
// (app.css .step-dots). The words say the same, so the dots are hidden from a screen reader.
function stepLine(n, what) {
  const total = steps();
  return el("p", { class: "kicker step" },
    el("span", { class: "step-dots", "aria-hidden": "true", style: `--n:${n - 1}` },
      Array.from({ length: total }, (_x, i) => el("i", { class: i < n - 1 ? "done" : i === n - 1 ? "now" : "" })),
      el("b", { class: n === 1 ? "first" : "" })),
    el("span", {}, `Step ${n} of ${steps()}`), el("span", { class: "step-what" }, what));
}

function photo() {
  // D-191: the phone's Back from a result lands here with the same photos, and one tap on
  // "Check this pack" sent them again unchanged (the same photos refused twice in minutes,
  // 2026-10-07 to 10-09). Until a photo changes, this opens that result instead.
  if (pending.back && pending.resultId && samePhotos(pending.answered)) {
    location.replace("#/result/" + encodeURIComponent(pending.resultId));
    return null;
  }
  return pending.back ? shotReview() : listShot();
}

// D-191: the photos in hand, as the objects they are; any retake or new photo is a new object.
const photosInHand = () => [pending.back, ...pending.parts, pending.front];
const samePhotos = was => !!was && was.length === photosInHand().length && photosInHand().every((b, i) => b === was[i]);

// The ingredient list, or its next part (D-119). back: where the header's arrow goes, when not
// the photos in hand (D-194: the result that asked for the rest).
function listShot(back = null) {
  // D-173: counts the list's photos only; a kept table photo stays after them.
  const n = pending.back ? partRows().filter(r => r[2] === "list").length + 2 : 1;
  return labelShot({
    role: n === 1 ? "back" : "back" + n,
    step: stepLine(2, n === 1 ? "Ingredients" : `Ingredients, part ${n}`),
    title: n === 1 ? "Photograph the ingredient list" : "Photograph the rest of the list",
    kept: n === 1 && partRows().some(r => r[2] === "table"),
    line: n === 1 ? "Fit the list, from \"Ingredients\" to the last word"
                  : "Start where the last photo ended. A little overlap is fine.",
    // D-194: a long list may come in parts; said once, on the first photo, with no new tap.
    more: n === 1 ? "Too long for one photo? Take it in parts, one photo each." : null,
    keptList: back && n > 1 ? (n === 2 ? "We kept your first photo of the list." : "We kept your photos of the list.") : null,
    back: back || (pending.back ? () => show(shotReview()) : null),
    onShot: (b, res, source) => { addShot(n, "list", b, source, res); show(shotReview(res)); },
  });
}

// The nutrition table, as the next part. `after`: what else the screen offers; `back`: where
// the header's arrow goes (the photos in hand, during a scan).
function tableShot(after = null, back = () => show(shotReview())) {
  const n = pending.parts.length + 2;
  return labelShot({
    role: "back" + n, table: true, back,
    step: stepLine(3, "Nutrition table"),
    title: "Photograph the nutrition table",
    line: "Fit the whole table, from its title to the last row",
    after: after || button("This pack has no table", () => frontNeeded() && !pending.front ? show(frontShot()) : sendPhotos()),
    onShot: (b, res, source) => { addShot(n, "table", b, source, res); show(shotReview(res)); },
  });
}

// The parts that are the table (D-171), as [blob, source, kind] rows, and the list's.
const partRows = () => pending.parts.map((b, i) => [b, pending.partSources[i], (pending.partKinds || [])[i] || "list"]);
function setParts(rows) {
  pending.parts = rows.map(r => r[0]);
  pending.partSources = rows.map(r => r[1]);
  pending.partKinds = rows.map(r => r[2]);
}

function addShot(n, kind, b, source, res) {
  pending.lastKind = kind;
  // D-173: a table photo kept from before stays the last part, after the list's photos.
  const tables = partRows().filter(r => r[2] === "table");
  if (n === 1) {
    pending.back = b;
    pending.backSource = source;
    setParts(tables);                                   // a new first photo starts the list again
    if (res?.barcode && !pending.barcode) { pending.barcode = res.barcode; pending.barcodeSource = "photo"; }
    return;
  }
  if (kind === "list") {
    const list = partRows().filter(r => r[2] === "list");
    return setParts([...list.slice(0, n - 2), [b, source, "list"], ...tables]);
  }
  setParts([...partRows().slice(0, n - 2), [b, source, kind]]);
}

// D-173 (Sushil, 2026-10-07: "it should reuse as it reads properly in previous photo"): a
// refusal or a partial read is about the ingredient list, so a retake drops the list's photos
// and keeps the table's and the front. Not for photos that aren't a pack (a screen, not food,
// D-103, D-130): the table photo goes too, as before. D-108: two packs, the front goes.
// h: the result being retaken; its photos are kept only while this phone still holds them.
const NOT_A_PACK = ["back_is_a_screen", "not_a_food_pack", "screen_unread"];
function retakeList(h, code = null, keepTable = false) {
  const mine = pending.resultId === h.id;
  const tables = mine && !NOT_A_PACK.includes(code) ? partRows().filter(r => r[2] === "table") : [];
  setParts(mine && keepTable && !tables.length && pending.back ? [[pending.back, pending.backSource, "table"]] : tables);
  pending.back = null;
  pending.acceptUnconfirmed = false;
  if (!mine) pending.barcode = h.barcode;              // photos from another scan aren't this pack's
  if (!mine || code === "product_mismatch") { pending.front = null; pending.pairing = false; }
  go("photo");
}

// After a shot: the photos in hand, the check's line for the last one, and what's next.
// Not answering the table question is "yes": the pack is read from what's in hand.
// frontRes: the check's answer for a front photo just added.
function shotReview(res = undefined, frontRes = undefined) {
  const photos = [pending.back, ...pending.parts];
  const kinds = ["list", ...pending.parts.map((_p, i) => (pending.partKinds || [])[i] || "list")];
  const n = photos.length;
  const tableIn = kinds.includes("table");
  const names = kinds.map((k, i) => k === "table" ? "Nutrition table" : i === 0 ? "Ingredients" : `Ingredients, part ${i + 1}`);
  const shown = pending.front ? [...photos, pending.front] : photos;
  const shownNames = pending.front ? [...names, "Front"] : names;
  // D-173: a table kept from before a retake sits last; the shot just taken is the last list photo.
  const kept = tableIn && pending.lastKind === "list";
  const lists = kinds.filter(k => k === "list").length;
  const retake = () => {
    if (!kept && kinds[n - 1] === "table") {
      setParts(partRows().slice(0, -1));
      return show(tableShot());
    }
    if (lists === 1) { pending.back = null; return show(listShot()); }
    const list = partRows().filter(r => r[2] === "list");
    setParts([...list.slice(0, -1), ...partRows().filter(r => r[2] === "table")]);
    show(listShot());
  };
  const dropTable = () => { setParts(partRows().filter(r => r[2] !== "table")); show(tableShot()); };
  // D-185 Phase 2: the photos in hand arrive one after another (app.css .taken figure).
  const pics = el("div", { class: shown.length === 1 ? "thumb" : "taken" },
    shown.map((b, i) => shown.length === 1
      ? el("img", { src: URL.createObjectURL(b), alt: "Your photo of the ingredient list" })
      : el("figure", { class: "thumb", style: `--i:${i}` }, el("img", { src: URL.createObjectURL(b), alt: `Your photo: ${shownNames[i]}` }),
          el("figcaption", { class: "muted" }, shownNames[i]))));
  // D-191: the free table hint, once per scan; it takes the dock until it is answered.
  const hint = res?.ok && res.hint && !pending.hintUsed ? res.hint : null;
  const line = frontRes !== undefined ? checkLine(frontRes, () => show(frontShot()), "front")
    : res === undefined || hint ? null : checkLine(res, retake);
  // D-175: a re-check of a published pack asks for the list only; the table is on file or offered apart.
  const listOnly = pending.recheck === "list";
  // D-181: the front is the last photo; once it's in, the table question has had its answer.
  const frontIn = frontNeeded() && !!pending.front;
  const ask = !tableIn && n < MAX_PHOTOS && !listOnly && !frontIn;   // the table question, while there's room for its photo
  // D-181: with the front still to take, the answer leads to it; with it in, the check waits
  // for the "same pack" box (D-035), so the front can reach the reviewer.
  // D-199 (Sushil, 2026-10-11: "sometimes ... it skips step3 nutrition table"): the table
  // question's two answers look the same (class table-answer), so a hurried tap isn't steered
  // to Yes. Without the question, the one check keeps its words and the primary style.
  const yes = frontNeeded() && !pending.front ? () => show(frontShot()) : () => sendPhotos();
  const check = ask ? button("Yes, it's in this photo", yes, "table-answer")
    : frontNeeded() && !pending.front ? button("Next: the front of the pack", yes, "primary")
    : button("Check this pack", yes, "primary");
  if (frontIn && !pending.pairing) check.disabled = true;
  const m = shown.length;
  return el("section", { class: "stack shot-review" },
    // D-194: a list part added after the front (the rest of a cut-off list) names that part.
    frontIn && pending.lastKind === "front" ? stepLine(4, "Front")
      : stepLine(tableIn && !kept ? 3 : 2, kept ? names[lists - 1] : names[n - 1]),
    pics,
    // D-185 Phase 2: the retakes sit under the photos they act on.
    !hint && el("div", { class: "retakes" },
      (ask || (kept && n < MAX_PHOTOS) || (listOnly && n < MAX_PHOTOS))
        && button("The list goes on: add the next part", () => show(listShot()), "secondary more-part"),
      button(tableIn && !kept ? "Retake the table" : "Retake", retake, "link"),
      kept && button("Retake the table too", dropTable, "link"),
      pending.front && button("Retake the front", () => show(frontShot()), "link")),
    line,
    // D-185 Phase 2: once the photos are in, a check draws itself beside the words. The table
    // question sits in the dock, right above its two answers.
    !ask && el("h1", { class: "photos-in" }, kindIcon("done", true), m === 1 ? "The ingredient list is in" : m === 2 ? "Both photos are in"
        : m === 3 ? "All three photos are in" : "All four photos are in"),
    // D-185 Phase 2 (D-171): the answer docks at the bottom on a phone, in thumb reach.
    hint ? el("div", { class: "dock" }, el("h1", { class: "dock-q" }, hint.text),
      button(hint.retake, retake, "primary"),
      button(hint.use, () => { pending.hintUsed = true; show(shotReview(res)); })) :
    el("div", { class: "dock" },
      ask && el("h1", { class: "dock-q" }, "Is the nutrition table in this photo too?"),
      // D-100: the reviewer reads the brand, name and claims from the front. D-181: required while
      // the catalogue wants it, so no "optional" link; the "same pack" box sits above the check
      // it unlocks. Sent with the back in the one /scan.
      pending.front && el("label", { class: "choice" },
        el("input", { type: "checkbox", id: "pairing", checked: pending.pairing,
                      onchange: e => {
                        pending.pairing = e.target.checked;
                        if (frontIn) check.disabled = !pending.pairing;
                      } }),
        m === 2 ? " Both photos are of the same pack" : " All these photos are of the same pack"),
      check,
      ask && button("No, photograph the table", () => show(tableShot()), "table-answer")));
}

// The front photo (D-100), then back to the same answer screen. D-181: a required step while
// the catalogue wants it (the header's arrow returns to the photos in hand; no "Not now").
function frontShot() {
  return labelShot({
    role: "front", checkAs: "front", front: true,
    back: () => show(shotReview()),
    step: stepLine(4, "Front"),
    title: "Photograph the front",
    line: "Fill the frame with the front of the pack, including any words printed on it.",
    onShot: (b, res, source) => {
      pending.front = b;
      pending.frontSource = source;
      pending.lastKind = "front";
      show(shotReview(undefined, res));
    },
  });
}

// One photo of the label. o: { role, checkAs, step (a node), title, line, table, front, after,
// back (where the header's arrow goes), onShot(blob, res, source) }.
// onShot runs once a photo is in and the check didn't turn it down.
// Tips is a small pill beside the title, not a loose link under the picker (Sushil, 2026-10-08).
function labelShot(o) {
  const tips = el("button", { type: "button", class: "tips-btn", onclick: () => tipsSheet(liveOn()) },
    icon("info"), "Tips");
  const view = el("section", { class: "stack label-cam" }, o.step,
    el("div", { class: "cam-title" }, el("h1", {}, o.title), tips));
  if (o.back) view.backTo = o.back;
  const shot = el("div", { class: "stack" });
  // D-185 Phase 2 (D-171, D-181): on a phone the step's action docks at the bottom of the screen,
  // in thumb reach; what else the step offers (o.after) sits with it.
  const dock = el("div", { class: "dock" });
  view.append(shot, dock);
  if (o.after) dock.append(o.after);

  // The phone's camera app (D-102's file inputs): the default, and the way back when the live
  // camera can't open. photoPicker shows the photo and the check's line, with Retake.
  const appCamera = why => {
    const preview = el("div", { class: "thumb" });
    let picker = null;
    shot.replaceChildren(...[
      el("div", { class: "card shot-card" },
        exampleShot(o.front ? "front" : o.table ? "table" : "list", "Like this: flat, sharp, the whole panel"),
        el("p", { class: "cam-line" }, o.line),
        o.more && el("p", { class: "cam-line cam-more" }, o.more)),
      o.keptList && kinded("p", "done", { class: "muted kept-note" }, o.keptList),                         // D-194
      o.kept && kinded("p", "done", { class: "muted kept-note" }, "We kept your photo of the nutrition table."),   // D-191
      why && kinded("p", "info", { class: "muted" }, why),
      preview].filter(Boolean));
    picker = photoPicker(o.role, "Take the photo", preview, (b, res, source) => {
      if (b && !(res && !res.ok)) o.onShot(b, res, source);
    }, o.checkAs || "back");
    leadWith(picker, true);
    dock.prepend(picker);
    // D-185 Phase 2: the step's other answer ("This pack has no table") right under the main one,
    // "Upload a photo" last.
    const take = o.after && picker.querySelector("label.btn:not(.link)");
    if (take) take.after(o.after);
  };
  if (!liveOn()) {
    appCamera(null);
    return view;
  }

  // The live camera (D-171): a frame, one line, the shutter; a hint when it's dark or moving.
  const video = el("video", { class: "viewfinder", muted: true, playsinline: true, "aria-label": "Camera" });
  const hint = el("div", { class: "cam-hint-slot", "aria-live": "polite" });
  const wrap = el("div", { class: "viewfinder-wrap tall" }, video,
    el("div", { class: "frame label" + (o.table ? " table" : ""), "aria-hidden": "true" },
      el("i", {}), el("i", {}), el("i", {}), el("i", {})),
    hint);
  const shutter = el("button", { type: "button", class: "shutter", "aria-label": "Take the photo", disabled: true });
  const upload = uploadLink(o.role, file => checkShot(o, file, "upload", again));
  shot.replaceChildren(...[wrap, el("p", { class: "cam-line" }, o.line),
    o.more && el("p", { class: "cam-line cam-more" }, o.more),
    o.keptList && kinded("p", "done", { class: "muted kept-note" }, o.keptList),                           // D-194
    o.kept && kinded("p", "done", { class: "muted kept-note" }, "We kept your photo of the nutrition table."),   // D-191
    el("div", { class: "shutter-row" }, el("span", {}), shutter, upload)].filter(Boolean));

  const seq = navSeq;
  const onHint = h => hint.replaceChildren(h ? kinded("p", "problem", { class: "cam-hint check bad" },
    h === "dark" ? "Too dark" : "Hold still") : "");
  startLabelCamera(video, onHint).then(stop => {
    if (seq !== navSeq || !view.isConnected) return stop();         // the user left before it opened
    record("label_camera", { started: true });
    stopCamera = stop;
    shutter.disabled = false;
    if (stop.hasTorch) {
      let on = false;
      const t = el("button", { type: "button", class: "cam-light", "aria-pressed": String(on) }, "Light");
      t.addEventListener("click", async () => {
        if (await stop.torch(!on)) { on = !on; t.setAttribute("aria-pressed", String(on)); }
      });
      wrap.append(t);
    }
    shutter.addEventListener("click", async () => {
      shutter.disabled = true;
      let blob = null;
      try { blob = await stop.takePhoto(); } catch (e) { record("label_camera", { shot: false, error: String(e?.name || e) }); }
      if (!blob) { shutter.disabled = false; return; }
      if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) navigator.vibrate?.(15);
      stop();
      if (stopCamera === stop) stopCamera = null;
      record("photo_source", { role: o.role, source: "live" });
      checkShot(o, blob, "live", again);
    });
  }).catch(e => {
    record("label_camera", { started: false, error: String(e?.name || e) });
    appCamera("We couldn't open the camera here, so your phone's camera app takes the photo.");
  });
  // Retake after a refused photo: this same screen again.
  function again() { show(labelShot(o)); }
  return view;
}

// A photo from the live camera or "Upload a photo": shown while it's checked, then on to the
// next screen, or back with the problem named (D-170) and Retake.
async function checkShot(o, file, source, again) {
  if (!file) return;
  if (stopCamera) { stopCamera(); stopCamera = null; }
  const wait = el("div", { class: "thumb" }, el("p", { class: "muted", role: "status" }, "Preparing photo…"));
  show(el("section", { class: "stack shot-review" }, o.step, wait));
  const out = await checkPhoto(o.role, o.checkAs || "back", file, b => wait.replaceChildren(
    el("span", { class: "shot reading" }, el("img", { src: URL.createObjectURL(b), alt: "Your photo" })),
    el("p", { class: "muted", role: "status" }, "Checking the photo…")));
  if (!out) return;
  const { blob, res } = out;
  if (res && !res.ok) {
    return show(el("section", { class: "stack shot-review" }, o.step,
      el("div", { class: "thumb" }, el("img", { src: URL.createObjectURL(blob), alt: "Your photo" }), checkLine(res, again)),
      uploadLink(o.role, f => checkShot(o, f, "upload", again))));
  }
  o.onShot(blob, res, source);
}

function uploadLink(role, onFile) {
  const i = el("input", { type: "file", accept: "image/*", class: "sr", id: "upload-" + role });
  i.addEventListener("change", () => { record("photo_source", { role, source: "upload" }); onFile(i.files && i.files[0]); });
  return el("span", {}, i, el("label", { for: "upload-" + role, class: "btn link" }, "Upload a photo"));
}

// The D-163 and D-167 hints and the pack-back drawing, out of the way until asked for.
function tipsSheet(live) {
  const d = el("dialog", { class: "sheet", "aria-label": "Tips" },
    el("h2", {}, "Tips"),
    el("figure", { class: "pack-back" }, packBack(),
      el("figcaption", { class: "src" }, "The back of a pack. The ingredients first, then the nutrition table.")),
    el("dl", { class: "ruled hints" },
      el("div", {}, el("dt", {}, "Frame"), el("dd", {}, "The whole ingredient list, from \"Ingredients:\" to the last word, and the whole nutrition table.")),
      el("div", {}, el("dt", {}, "Light"), el("dd", {}, "Hold the phone close and steady. On a pouch or a shiny pack, lay it on a table, smooth it flat and tilt it away from the light.")),
      // D-163: a barcode the photos also show is confirmed by the server (D-143), so a
      // reviewer needn't check it by hand. A hint only: no extra photo or step.
      pending.barcode ? el("div", {}, el("dt", {}, "Barcode"),
        el("dd", {}, "If it's on the same side, keep it in the photo too. We check the number against it.")) : null),
    button(live ? "Back to the camera" : "Close", () => d.close(), "primary"));
  d.addEventListener("close", () => d.remove());
  main.append(d);
  d.showModal();
}

// app-polish: a picker's take-photo button carries the primary style while it is the next step.
function leadWith(picker, lead) {
  const take = picker && picker.querySelector("label.btn:not(.link)");
  if (take) take.classList.toggle("primary", !!lead);
}

// D-102: take a photo now, or upload one already on the phone or computer
// (a saved picture, a pack photographed earlier). `capture` makes a phone open
// the camera straight away, so the upload button is a second input without it.
// On a computer (no touch screen) there is only "choose", and a photo can be
// dropped onto the box.
const TOUCH = window.matchMedia?.("(pointer: coarse)").matches ?? true;

// D-171: the live camera, where the server has it on and the phone can take a full-size still.
const liveOn = () => liveShutter && TOUCH && labelCameraSupported();

// D-104: every photo is checked on the server as soon as it is picked. Returns {blob, res}:
// res is {ok, message, barcode, label}, or null when the check couldn't run. onReady(blob): the
// photo is ready to show while it's checked.
async function checkPhoto(role, checkAs, file, onReady = null) {
  const blob = await prepareImage(file);
  onReady?.(blob);
  let res = null;
  // D-191: the free table hint looks at the scan's first ingredient-list photo only, once a scan.
  const firstList = role === "back" && checkAs === "back" && !pending.hintAsked;
  if (firstList) pending.hintAsked = true;
  try {
    res = (await checkPhotoRequest(checkAs, blob, firstList)).body;
  } catch (e) {
    if (e.status === 429 || e.status === 413 || e.status === 415) res = { ok: false, message: apiMessage(e) };
  }
  record("photo_check", { role, ok: res ? res.ok : null, problem: res?.problem || null, barcode: !!res?.barcode,
                          hint: !!res?.hint });
  return { blob, res };
}

// The check's line: a green tick or the problem with a Retake (D-170).
function checkLine(res, retake, role = "back") {
  return res === null
    ? kinded("p", "problem", { class: "check unknown", role: "status" },
        role === "barcode" ? "We couldn't check this photo just now. Try again in a moment."
                           : "We couldn't check this photo just now. It will be checked when you continue.")
    : !res.ok && res.label
      // D-170: the problem named over the server's sentence, and a way straight back to the camera.
      ? kinded("div", "problem", { class: "check bad", role: "status" },
          el("strong", { class: "problem-label" }, res.label), el("p", {}, res.message),
          button("Retake", retake))
      : kinded("p", res.ok ? "done" : "problem", { class: "check " + (res.ok ? "ok" : "bad"), role: "status" },
          res.message);
}

// D-104: every photo is checked on the server as soon as it is picked, and
// gets a green tick or a red cross with the reason. onPick(blob, result):
// result is {ok, message, barcode}, or null when the check couldn't run.
// D-106: onPick also gets where the photo came from, "camera" or "upload".
function photoPicker(role, label, preview, onPick, checkAs = role) {
  const use = async (file, source) => {
    if (!file || !file.type.startsWith("image/")) return;
    preview.replaceChildren(el("p", { class: "muted" }, "Preparing photo…"));
    let img = null;
    const out = await checkPhoto(role, checkAs, file, b => {
      // D-185 Phase 2: a gold line passes over the photo while it is checked (app.css .shot.reading).
      img = el("span", { class: "shot reading" }, el("img", { src: URL.createObjectURL(b), alt: `Your ${role} photo` }));
      preview.replaceChildren(img, el("p", { class: "muted", role: "status" }, "Checking the photo…"));
    });
    if (!out) return;
    const { blob, res } = out;
    img?.classList.remove("reading");
    preview.replaceChildren(img, checkLine(res, () => document.getElementById("pick-" + role)?.click(), role));
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
        input("pick-" + role, true), el("label", { for: "pick-" + role, class: "btn" }, icon("camera"), label),
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
  let blob = null, blobSource = null, picker = null;
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
    (picker = photoPicker("front", "Take the front photo", preview, (b, res, source) => {
      blob = res && !res.ok ? null : b;
      blobSource = source;
      send.disabled = !blob;
      leadWith(picker, !blob);
    }), leadWith(picker, true), picker),
    preview,
    send);                                                 // the header's arrow goes back to the result
}

// D-201: "Photograph the side" on an infant result: one photo of the pack's side, read for
// regulation 4's notices only (Cloud Vision, no model call, not one of the day's photo scans).
// The result's notices block comes back in the server's words and replaces the one shown.
function side(id) {
  const h = historyItem(id);
  const w = h?.screen?.infant?.good?.blocks?.find(b => b.id === "notices")?.side;
  if (!h || !w) return errorView("We couldn't find that pack on this phone.");
  const preview = el("div", { class: "thumb" });
  let blob = null, blobSource = null, picker = null;
  const send = el("button", { type: "button", class: "btn primary", disabled: true, onclick: async () => {
    show(working("Reading the side of the pack…", false));
    try {
      const { body } = await sidePhotoRequest({ blob, source: blobSource, side: w, scanId: h.scan_id });
      saveSidePhoto(id, body);
      record("side_photo", { read: !!body.read, found: (body.found || []).length });
      go("result/" + encodeURIComponent(id));
    } catch (e) {
      show(apiErrorView(e, () => go("side/" + encodeURIComponent(id))));
    }
  } }, "Send the side photo");
  return el("section", { class: "stack" },
    el("h1", {}, w.title),
    el("p", { class: "product" }, productName(h.product)),
    el("p", { class: "lead" }, w.line),
    (picker = photoPicker("side", "Take the side photo", preview, (b, res, source) => {
      blob = res && !res.ok ? null : b;
      blobSource = source;
      send.disabled = !blob;
      leadWith(picker, !blob);
    }, "back"), leadWith(picker, true), picker),
    preview,
    send);                                                 // the header's arrow goes back to the result
}

// D-073, D-175: a photo of a published pack's list, compared with the published list for free
// first (recheck=true). listOnly: D-175's card asks for the list alone ("list"), no table question.
function recheckPhoto(h, listOnly = false) {
  resetPending();
  pending.barcode = h.barcode;
  pending.recheck = listOnly ? "list" : "full";
  pending.frontWanted = !!h.catalogue?.front_wanted;      // D-100, D-181: required only while wanted
  if (listOnly) pending.frontWanted = false;              // D-175: one ask; a front would cost the free check
  go("photo");
}

// ------------------------------------------------------------------ a table photo (D-168)
// For a pack the catalogue has without its nutrition table: one photo, read once; only the
// table is used. Every word is the server's (screen.TABLE_OFFER, TABLE_ANSWER).
const tableSent = barcode => !!store.get("tableSent", {})[barcode];

function tablephoto(id) {
  const h = historyItem(id);
  const offer = h && h.screen && h.screen.table_offer;
  if (!h || !h.barcode || !offer) return errorView("We couldn't find that pack on this phone.");
  const w = offer.photo;
  const back = () => go("result/" + encodeURIComponent(id));
  const send = async (blob, blobSource) => {
    show(working("Sending the photo…", false));
    try {
      const { body } = await scanRequest({ barcode: h.barcode, back: blob, backSource: blobSource, tableOnly: true });
      const t = body.table || {};
      if (t.status === "added" || t.status === "already_waiting") {
        store.set("tableSent", { ...store.get("tableSent", {}), [h.barcode]: true });
      }
      show(el("section", { class: "stack" },
        el("h1", {}, w.title),
        kinded("p", t.kind || "problem", { class: "lead" }, t.text),
        button("Back to the result", back)));
    } catch (e) {
      show(apiErrorView(e, () => go("tablephoto/" + encodeURIComponent(id))));
    }
  };
  // D-171: the step 3 camera, with the server's words (screen.TABLE_OFFER).
  const o = {
    role: "back", table: true,
    step: el("p", { class: "kicker product" }, productName(h.product)),
    title: w.title, line: w.lead,
    after: el("p", { class: "muted" }, w.barcode),         // the header's arrow goes back to the result
    onShot: (b, res, source) => show(el("section", { class: "stack shot-review" }, o.step,
      el("div", { class: "thumb" }, el("img", { src: URL.createObjectURL(b), alt: "Your photo of the table" }),
        res === undefined ? null : checkLine(res, () => show(labelShot(o)))),
      el("h1", {}, w.title),
      button(w.button, () => send(b, source), "primary"),
      button("Retake", () => show(labelShot(o)), "link"))),
  };
  return labelShot(o);
}

async function sendPhotos() {
  // app-polish: one photo has two stages the app really knows: going up, then being
  // read. With more photos the wait keeps one stage ("the photo" would be untrue).
  const one = !pending.front && !pending.parts.length;
  const wait = working("Reading the ingredient list…", true,
                       one ? ["Sending the photo…", "Reading the ingredient list…"] : null);
  show(wait);
  try {
    const { body } = await scanRequest(pending, one ? { onUploaded: () => wait.next() } : {});
    finish(body);
  } catch (e) {
    show(apiErrorView(e, sendPhotos));
  }
}

// D-068: honest about speed. The API has no progress events, so we show time passing,
// what a first read usually takes and, for one photo, the two stages the app knows
// (app-polish): the photo going up, then the reading. No percentage, no invented steps.
// D-185 Phase 2: a drawing of what is happening (readArt) above the track, moving from the first frame.
function working(text, reading, stages = null, art = "label") {
  const secs = el("span", {}, "0");
  const slow = el("p", { class: "muted" });
  const t0 = Date.now();
  const timer = setInterval(() => {
    if (!secs.isConnected) return clearInterval(timer);
    const n = Math.round((Date.now() - t0) / 1000);
    secs.textContent = String(n);
    if (n >= 3) time.classList.remove("early");          // D-185 Phase 2: no "0 s" while it has only begun
    // D-124: a slow read should not look like a hang. D-154: no cause is named, because the
    // app can't see one (a slow scan is usually Gemini, or the fallback reader, not "busy").
    if (reading && n >= 20 && !slow.textContent) {
      slow.textContent = "Taking longer than usual. It is still working.";
    }
  }, 1000);
  const title = el("h1", {}, stages ? stages[0] : text);
  const time = el("p", { class: "muted wait-time early", role: "timer" }, secs, " s");
  const parts = (stages || [text]).map((_s, i) => el("span", { class: i === 0 ? "now" : "" }));
  const view = el("section", { class: "stack center wait" + (reading ? " reading" : ""), "aria-busy": "true" },
    art === "barcode" && stepLine(1, "Barcode"),                  // D-185 Phase 2: a lookup is still step 1
    readArt(art),
    el("div", { class: "track", "aria-hidden": "true" }, parts),
    title,
    reading && el("p", { class: "muted wait-note" },
      "The first read of a pack takes about 8 to 15 seconds. Once a pack is in our catalogue, its barcode gives the result at once."),
    time,
    slow);
  // The photo is up: the first stage is done and the reading is the one running.
  view.next = () => {
    if (!stages || !view.isConnected || title.textContent === stages[1]) return;
    parts[0].className = "done"; parts[1].className = "now";
    title.textContent = stages[1];
  };
  return view;
}

// D-185 Phase 2: the waiting screen's drawing. "label": a label whose lines light up in the logo's
// gold, one after another, while a lens moves down them (a 4.8 s loop). "barcode": a barcode with
// the gold line passing over it. Decoration only; the title says what is happening.
function readArt(art) {
  if (art === "barcode") {
    return el("div", { class: "read-art barcode", "aria-hidden": "true" },
      el("span", { class: "sheet" }, el("span", { class: "bars" }), el("span", { class: "sweep" })));
  }
  return el("div", { class: "read-art", "aria-hidden": "true" },
    el("span", { class: "sheet" }, el("b", {}, "INGREDIENTS:"),
      [100, 86, 94, 70, 90, 62, 80].map((w, i) => el("span", { class: "ln", style: `width:${w}%;--i:${i}` }, el("i", {})))),
    el("span", { class: "lens" }));
}

function finish(body, { lookedUp = false } = {}) {
  const id = body.scan_id || "local-" + Date.now().toString(36);
  const rel = body.reliability || {};
  addHistory({
    id, at: new Date().toISOString(), barcode: pending.barcode,
    looked_up: lookedUp,            // D-146: a catalogue hit from the scanner offers "Scan again"
    scan_id: body.scan_id || null,
    product: body.product || null,
    screen: body.screen,
    catalogue: body.catalogue || null,
    disclosures: body.disclosures || [],
    // What /compare needs later, kept so a comparison costs no new scan (D-057).
    // D-139, D-140: only a kind that can be compared keeps what /compare needs; D-202: or one with
    // a shop list (an infant pack: the shop list stays, Compare doesn't).
    pack: body.screen?.state === "result" && (!body.screen.parts || body.screen.parts.includes("compare")
                                              || body.screen.parts.includes("shop_list")) ? {
      ingredients: body.extracted?.ingredients || [],
      allergen_statement: body.extracted?.allergen_statement || null,
      confidence: rel.confidence?.ingredients ?? 1.0,
      reliable: rel.source === "catalogue" || (!!rel.verdict_safe_to_display && !!rel.ingredients_complete),
      // D-140: the server re-checks the kind on /compare, from these too.
      kind: body.pack_kind?.code || "food",
      pack_statements: body.extracted?.pack_statements || [],
      veg_mark: body.product?.veg_mark || null,                     // D-198: "Vegetarian only" in Compare
      facts: body.compare_input || null,         // D-200: what Compare sets side by side (a supplement, an infant food)
    } : null,
  });
  // D-130: the pack from the shop list has been scanned in the shop; it's done.
  if (pending.shopItem && body.screen?.state === "result") {
    store.set("shoplist", shopList().filter(x => x.id !== pending.shopItem));
    pending.shopItem = null;
  }
  if (body.screen?.state === "retake") {
    pending.attempts += 1;
    // D-103: a photo that isn't a pack (a screen, anything else) can't be sent to a reviewer.
    if (body.scan_id && body.screen.can_send !== false) pending.refused.push(body.scan_id);
    pending.sendNow = !!body.screen.send_now;                   // D-172: one blocked scan is enough
  }
  pending.resultId = id;           // D-133: the photos in hand belong to this result
  pending.answered = photosInHand();                         // D-191: what this result answered
  // D-177: a small copy of the photo for the result's pack card, kept on this phone only.
  const shot = body.screen?.state === "result" && (pending.front || pending.back);
  if (shot) packPhoto(shot).then(url => {
    if (!url) return;
    savePackPhoto(id, url);
    for (const img of document.querySelectorAll(`img[data-photo="${CSS.escape(id)}"]`)) { img.src = url; img.hidden = false; }
    const ph = document.querySelector(`[data-photo-ph="${CSS.escape(id)}"]`);
    if (ph) ph.hidden = true;
  });
  go("result/" + encodeURIComponent(id));
}

// D-133: no nutrition table in the photos. One more photo, of the table, joins the
// back photos as the next part (the D-119 parts flow), and the pack is read again.
function table() {
  if (!pending.back || pending.parts.length >= 2) return errorView("Scan the pack again to add its nutrition table.");
  // D-171: the same step 3 screen as a new pack's table photo.
  return tableShot(el("span", {}), null);                // the header's arrow goes back
}

// D-194 (Sushil, 2026-10-11, "Ask only when cut off"): a partial read asks for the rest of the
// list as its own photo. Every photo in hand stays (the list's parts, the table, the front and
// the "same pack" tick); the next part joins them as D-119's parts and the pack is read again
// in one new /scan. The header's arrow goes back to the result that asked.
function listpart() {
  if (!canAddPart()) return errorView("Scan the pack again to add the rest of the list.");
  pending.acceptUnconfirmed = false;
  const id = pending.resultId;
  return listShot(() => go("result/" + encodeURIComponent(id)));
}

// The photos in hand belong to the result h and one more back photo fits (D-119's three).
const canAddPart = (h = null) => !!(pending.back && pending.resultId && (!h || pending.resultId === h.id)
                                    && pending.parts.length < MAX_PHOTOS - 1);

// D-194: a partial read's choices, from the server's list_choices (the words are the server's,
// D-091): the rest of the list as its own photo, while the photos are in hand and one more
// fits, then the whole list again (D-173 keeps the table and the front). Older results have
// no list_choices and keep their one retake button.
function listChoices(s, h, code = "partial", keepTable = false) {
  const c = s.list_choices;
  if (!c) return [button("Retake the ingredients photo", () => retakeList(h, code, keepTable))];
  const add = !!c.add && canAddPart(h);
  return [add && button(c.add, () => go("listpart"), "primary"),
          button(c.retake, () => retakeList(h, code, keepTable), add ? "" : "primary")];
}

// D-133: the nutrition table beside ICMR-NIN's thresholds. Every sentence is the server's.
// `ask`: offer the table photo here; off when the first screen already offers it (D-134).
// D-185 Phase 2 (D-177): a row leads with its label and amount, then its bar, then the rest of its
// sentence (`why`); the server cuts both from the sentence (screen.py), so no word is the app's.
// A row without them (an older result) shows its sentence whole.
function nutritionView(n, h, ask = true) {
  return el("div", { class: "card nutrition" },
    el("div", { class: "card-head" }, el("h2", {}, n.title), n.basis && el("span", { class: "chip basis" }, n.basis)),
    n.rows.map((r, i) => el("div", { class: `nut-row tone-${r.tone}` },
      r.amount && r.why
        ? [el("p", { class: "nut-head" },
            el("span", { class: "nut-label" }, r.tone === "worth" && kindIcon("worth"), r.label),
            el("span", { class: "nut-amount" }, r.amount)),
          r.bar && nutBar(r, i),
          el("p", { class: "nut-why" }, r.why)]
        : [el("p", {}, r.tone === "worth" && kindIcon("worth"), r.text), r.bar && nutBar(r, i)])),
    n.servings.map(x => el("p", { class: "nut-serving" }, x.text)),
    n.adults && el("p", { class: "muted small" }, n.adults),
    n.also && el("p", { class: "muted small" }, n.also),
    n.text && el("p", {}, n.text),
    ask && canAskTable(n, h) && button(n.ask, () => go("table")),
    n.checked && el("p", { class: "muted small" }, n.checked),
    n.sources?.length > 0 && el("details", { class: "more" }, el("summary", {}, "Sources"),
      el("ul", { class: "plain small" }, n.sources.map(x =>
        el("li", {}, el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.cite))))));
}

// The photos in hand belong to this result and one more part can still join them.
function canAskTable(n, h) {
  return !!(n.ask_photo && pending.resultId === h.id && pending.back && pending.parts.length < 2);
}

function sourceList(sources) {
  return el("ul", { class: "plain small" }, sources.map(x =>
    el("li", {}, el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.cite || x.title))));
}

// ------------------------------------------------------------------ result (D-060 to D-066, D-134)
// D-134: one screen. The allergen lines, the headline, the tiles, the three answers,
// At a glance and the buttons; everything else sits in one closed "More about this
// pack". A tile opens its own page, #/result/<id>/look/<tile id>.
function result(id, sub, tileId) {
  const h = historyItem(id);
  if (!h || !h.screen) return errorView("We couldn't find that result on this phone.");
  if (sub === "look") return lookView(h, tileId);
  const s = h.screen;
  const view = el("section", { class: "stack result" });
  // el() drops false/null children; the DOM's own append() would print "false".
  const put = (...nodes) => view.append(...nodes.flat().filter(x => x != null && x !== false));

  // 1. D-153: the deep panel opens the result: the pack's name, then each person's line, the
  // largest words on the screen (D-060, D-064). The name is the h1, so focus and a screen
  // reader start here, above the people.
  put(el("div", { class: "deep opener result-top" },
    packHead(h),
    // D-146: a catalogue hit names the product; if it isn't this pack, back to the scanner.
    s.rescan && h.looked_up && el("p", { class: "rescan" }, s.rescan.text, " ",
      button(s.rescan.button, () => { resetPending(); scanAgain(); }, "link")),
    cardPeople(s).length > 0 && el("div", { class: "people" }, cardPeople(s).map(p => personCard(p, h)))));
  // D-140: an older toddler profile is asked once whether the child is under 2. The
  // server leaves it out after D-146's digit check, so a scan never asks twice.
  if (s.band_question && s.state === "result") put(bandQuestion(s.band_question));

  // D-130: read from a screen. Said before anything about the product.
  if (s.from_screen) put(kinded("div", "info", { class: "card", role: "note" },
    el("strong", {}, s.from_screen.title), el("p", {}, s.from_screen.text),
    s.from_screen.pack && el("p", {}, s.from_screen.pack)));

  // 2. The headline finding (D-061), in the report voice: a heading, not an alarm.
  put(el("h2", { class: "headline h-serif" }, s.headline.text));

  // D-130: this pack, scanned from the shop list, against the screenshot.
  if (s.since_screen) put(kinded("div", s.since_screen.differs ? "worth" : "info", { class: "card", role: "note" },
    el("h2", {}, s.since_screen.title), s.since_screen.lines.map(t => el("p", {}, t))));

  if (s.state === "retake") {
    put(
      // D-170: the user's own photo with its problem named; older results keep the one line.
      s.problem ? photoProblem(s.problem, heldPhotos(h, s.problem.code === "product_mismatch"))
                : kinded("p", "problem", { class: "card" }, s.retake),
      s.repeat && el("p", { class: "muted" }, s.repeat),
      pending.attempts >= 2 && s.can_send !== false && el("p", { class: "muted" },
        "Still not working? Try daylight, or another pack. Some labels are printed too small or too shiny to read."),
      // D-070: after two refusals, a person reads the photos instead. Beside the hint, so the dock
      // below stays one button high (D-185 Phase 2).
      !s.send_now && pending.refused.length >= 2 && button("Send it to us", () => go("send")),
      // D-185 Phase 2: the way on stays in thumb reach, docked above the bar while the photo scrolls.
      el("div", { class: "dock retake-dock" },
        // D-172: Gemini's guard blocked the read; the photos are fine, so a person reads them now.
        s.send_now && pending.refused.length >= 1 && button("Send it to us", () => go("send"), "primary"),
        // D-173: the list is retaken; the table photo and the front stay (D-108: not after two packs).
        // D-194: a list read only in part offers its rest first (list_choices).
        s.list_choices ? listChoices(s, h, s.problem?.code, s.keep_table) :
        button(s.retake_button || "Retake the photo", () => retakeList(h, s.problem?.code || s.headline?.source?.ref, s.keep_table),
               s.send_now ? "" : "primary"),
        // D-118: our second reader couldn't confirm a new pack's list. The person
        // can still have their result from these photos.
        s.can_use_anyway && pending.back && button("Use this one anyway", () => {
          pending.acceptUnconfirmed = true;
          sendPhotos();
        })),
      // D-170: nothing was read, so there is no mistake to report; an app problem still can be.
      problemLink());
    return view;
  }

  // D-139, D-140: a supplement, an infant food, a special medical food or a pack that
  // isn't food: the allergen lines above, then the server's lines, and nothing that
  // judges it as a food. Which parts show is the server's (screen.parts).
  if (s.kind) {
    put(kindView(s), forYouLines(s));
    // D-139: a supplement's own tiles, each opening its page, its sugar chip for a food
    // format, and its sections (amounts, statements, additives), all in the server's words.
    if (s.tiles?.length) put(el("ul", { class: "tiles" }, s.tiles.map(t => el("li", {}, tileLink(h, t)))));
    if (s.infant) put(...infantView(s, h));                             // D-201
    if (s.summary?.length) put(answersView(s.summary));
    (s.sections || []).forEach(x => put(el("div", { class: "card section" },
      el("h2", {}, x.title), x.lines.map(t => el("p", {}, t)),
      x.sources?.length > 0 && el("details", { class: "more" }, el("summary", {}, "Sources"), sourceList(x.sources)))));
    if (s.retake) put(partialRetake(s, h, ...listChoices(s, h)));
    if (s.recheck) put(el("div", { class: "card note" }, el("p", {}, s.recheck),
      button("Photograph the ingredients list", () => recheckPhoto(h))));
    // D-200: a supplement, and an infant food with its results shown, can be compared (with its own
    // kind only, no pick) and put on the shop list; the server says so in screen.parts.
    if (h.pack) put(shopListButton(s, h), resultNext(s, h), reportLink(h));
    else put(el("div", { class: "row wrap" }, button("Scan another", () => { resetPending(); go("scan"); }, "primary")),
      reportLink(h));
    put(el("details", { class: "item more-pack" }, el("summary", {}, s.more_title || "More about this pack"),
      el("div", { class: "stack more-body" }, moreAbout(h, false))));
    return view;
  }

  // 3. D-177: the rest of a food result sits under three tabs, so the first screen stays short
  // (D-153) and nothing is folded away: "For you" (what this pack means for the people above,
  // with its sources), "What's inside" (the nutrition table, additives, notes) and "On the pack"
  // (the user's photo and the list as printed). The people block above stays put (D-060).
  const tabs = [["you", "For you"], ["inside", "What's inside"], ["pack", "On the pack"]];
  const panels = {};
  for (const [key] of tabs) {
    panels[key] = el("div", { class: "stack tab-panel", id: `tp-${key}`, role: "tabpanel", "aria-labelledby": `tab-${key}`,
                              tabindex: "0" });
  }
  put(tabBar(h, tabs, panels));
  put(...Object.values(panels));
  const you = (...nodes) => panels.you.append(...nodes.flat().filter(x => x != null && x !== false));

  // For you. D-153's order: an additive not permitted in India first (D-111), then "Worth
  // knowing (n)", each tile a numbered note with its source opening its own page (D-134), then
  // the three answers (D-123) and the ring (D-127). Results kept on the phone from before
  // web-27 have no tiles: their rows show as before.
  const tiles = s.tiles || [];
  const serious = tiles.filter(t => t.kind === "not_permitted");
  const notes = tiles.filter(t => t.kind !== "not_permitted");
  you(forYouLines(s));
  // D-133's table card. D-199: first in For you, under the per-person lines (D-060, D-188),
  // so it shows on the first screen; it was last, below the three answers.
  const askTable = s.nutrition && canAskTable(s.nutrition, h);
  if (askTable) you(el("div", { class: "card note" }, el("p", {}, s.nutrition.text),
    button(s.nutrition.ask, () => go("table"))));
  if (serious.length) you(el("ul", { class: "tiles" }, serious.map(t => el("li", {}, tileLink(h, t)))));
  const answers = s.summary?.length
    ? answersView(s.summary)
    // Older results kept on the phone have no summary; they keep the band (D-063).
    : el("div", { class: `band band-${s.band.code}` },
        el("strong", {}, s.band.label),
        s.band.note && el("details", {}, el("summary", {}, "What does this mean?"), el("p", {}, s.band.note)));
  if (notes.length) you(el("div", { class: "worth card" },
    el("h2", { class: "h-serif" }, `Worth knowing (${notes.length})`),
    el("ol", { class: "notes" }, notes.map(t => noteItem(h, t)))));
  you(el("details", { class: "item answers-fold" },
    el("summary", {}, "The three answers"),
    el("div", { class: "stack worth-body" }, !s.tiles && legacyLooks(s), answers, s.glance && glanceView(s.glance, true))));

  // A partial read, the table photo and the D-073 re-check ask for something now,
  // with the pack in hand, so they stay on the first tab.
  // D-188: an amber allergen card above carries the retake button; the card here keeps its words.
  // D-194 (Sushil, accepting): a result with list_choices shows them here, once, for everyone,
  // whether or not anyone has an avoid list; the allergen card keeps its words and no buttons.
  const cardRetake = !s.list_choices && cardPeople(s).some(p => p.status === "cannot_confirm") && !h.looked_up;
  if (s.retake) you(partialRetake(s, h, ...(cardRetake ? [] : listChoices(s, h))));
  if (s.recheck) you(el("div", { class: "card note" }, el("p", {}, s.recheck),
    button("Photograph the ingredients and nutrition table", () => recheckPhoto(h))));
  // D-175: a pack last checked over 15 days ago; one optional photo of the list, after the answers.
  if (s.recheck_card) you(el("div", { class: "card note" }, el("p", {}, s.recheck_card.text),
    button(s.recheck_card.button, () => recheckPhoto(h, true))));
  // D-175: this photo matched the published list; said where the ask was.
  if (s.rechecked) you(kinded("p", "done", { class: "card" }, s.rechecked));

  // Actions: compare (D-057), the shop list (D-130), report (D-076, on every result).
  // D-130: a screen result goes on the shop list, to be scanned from the pack in the shop.
  you(shopListButton(s, h), resultNext(s, h), reportLink(h));

  // D-153: what's promised and not built yet, said plainly (D-058/D-059 alternatives, D-113 Ask).
  // D-185 Phase 2 (D-177): one quiet line at the end, not two dashed boxes.
  you(el("p", { class: "soon" }, el("span", { class: "pending-tag" }, "In preparation"),
    el("span", { class: "pending" }, "Other packs without what's on your avoid list"),
    el("span", { class: "pending" }, "Ask about this pack")));

  // What's inside: everything D-153 kept under "More about this pack", open.
  panels.inside.append(...moreAbout(h, !askTable, false));
  // D-168: a published pack without a nutrition table: one photo of it, offered last (never
  // above the allergen lines, D-060), and not again on this phone once it sent one for the pack.
  const offer = s.table_offer;
  if (offer && h.barcode && !tableSent(h.barcode)) {
    panels.inside.append(el("div", { class: "card note" },
      el("h2", {}, offer.title),
      el("p", {}, offer.text),
      button(offer.button, () => go("tablephoto/" + encodeURIComponent(h.id)))));
  }

  // On the pack: the user's own photo and the list as it was read, the label's words quoted.
  panels.pack.append(...onThePack(h));
  return view;
}

// D-130: a screen result goes on the shop list, to be scanned from the pack in the shop.
function shopListButton(s, h) {
  const onList = () => shopList().some(x => x.id === h.id);
  return s.shop_list && h.pack && button(onList() ? "On your shop list ✓" : "Add to my shop list", e => {
    if (!onList()) {
      store.set("shoplist", [{ id: h.id, product: h.product, barcode: h.barcode, at: h.at, pack: {
        ingredients: h.pack.ingredients, allergen_statement: h.pack.allergen_statement } },
        ...shopList()].slice(0, 30));
    }
    e.target.textContent = "On your shop list ✓";
  }, "primary");
}

// D-123, D-153: the next useful scan is the pack beside this one on the shelf (D-057), so the
// result ends on it: this pack joins Compare and the scanner opens for the next one.
// "Compare with n saved packs" opens Compare once there are two or more.
// 2026-10-14 (Sushil: "Compare (3)"): it counted this pack too and every saved pack whatever its
// kind, so it said 3 beside the bar's 2, and an infant pack offered foods the server refuses
// (D-200). Now it counts only saved packs of this pack's kind, and opening it keeps only those.
function resultNext(s, h) {
  const kindOf = x => historyItem(x)?.pack?.kind || "food";
  // D-202 (Sushil, 2026-10-14): an infant pack is checked one pack at a time: no Compare.
  const canCompare = comparable(h) && (!s.parts || s.parts.includes("compare"));
  const same = canCompare ? store.get("compare", []).filter(x => x !== h.id && comparable(historyItem(x))
                                                               && kindOf(x) === kindOf(h.id)) : [];
  const next = () => { resetPending(); go("scan"); };
  return el("div", { class: "result-next" },
    canCompare && !s.shop_list
      ? el("button", { type: "button", class: "btn-big", onclick: () => {
          if (!store.get("compare", []).includes(h.id)) toggleCompare(h.id);
          updateNav();
          next();
        } }, s.compare_button || "Holding another pack? Scan it to compare")     // D-201: the server's words
      : el("button", { type: "button", class: "btn-big", onclick: next }, "Scan another pack"),
    el("div", { class: "row wrap" },
      same.length > 0 && button(`Compare with ${same.length} saved pack${same.length > 1 ? "s" : ""}`, () => {
        store.set("compare", [...same, h.id].slice(-4));
        updateNav();
        go("compare");
      }),
      canCompare && !s.shop_list && button("Scan another", next, "link")));
}

// D-177: the pack card at the top of a result: the user's own photo of the pack (kept on this
// phone, D-074), its name as the h1 (focus and a screen reader start here, D-153), and Share.
function packHead(h) {
  const id = h.id;
  const src = h.photo || packPicture(h)?.url || null;          // D-182: else the pack picture
  return el("div", { class: "pack-head" },
    el("div", { class: "pack-thumb" },
      el("img", { "data-photo": id, alt: "", src, hidden: !src }),
      el("span", { class: "pack-thumb-ph", "data-photo-ph": id, hidden: !!src }, icon("pack"))),
    el("div", { class: "pack-name" },
      el("h1", { class: "product" }, productName(h.product)),
      h.product?.net_quantity && el("p", { class: "pack-meta" }, h.product.net_quantity)),
    canShare(h.screen) && el("button", { type: "button", class: "share-btn", "aria-label": "Share this result",
                                         onclick: () => shareResult(h) }, icon("share")));
}

// D-140, D-200: an infant food's result is shared only when the server lists "share" in its parts
// (INSIDELABEL_INFANT_TO_USERS on); in shadow it isn't. Every other result keeps Share (D-177).
function canShare(s) {
  return s?.kind?.code !== "infant" || (s.parts || []).includes("share");
}

// D-177: Share sends the result's own words (D-091) as text. A child's nickname stays on this
// phone (D-074): the lines name "your child", as they do before the nickname is filled in.
function shareResult(h) {
  const s = h.screen || {};
  // D-188: a match or a line we can't confirm, as on the result's top; nothing for a person with no match.
  const text = [productName(h.product), ...cardPeople(s).map(p => fill(p.share || p.line)), s.headline?.text,
                "Read with InsideLabel: https://insidelabel.ai"].filter(Boolean).join("\n");
  record("share", { via: navigator.share ? "share" : "copy" });
  if (navigator.share) return navigator.share({ title: productName(h.product), text }).catch(() => {});
  navigator.clipboard?.writeText(text).then(() => toast("Copied. Paste it where you like."), () => {});
}

function toast(text) {
  const t = el("p", { class: "toast", role: "status" }, text);
  document.body.append(t);
  setTimeout(() => t.remove(), 2600);
}

// D-177: the three tabs. Buttons in a tablist (arrow keys move between them); the chosen tab is
// kept for this result while the app is open, so a tile's page returns to the same tab.
const tabChosen = new Map();
function tabBar(h, tabs, panels) {
  const pick = (key, focus) => {
    tabChosen.set(h.id, key);
    bar.style.setProperty("--tab", String(tabs.findIndex(([k]) => k === key)));
    for (const b of bar.querySelectorAll("[role=tab]")) {
      const on = b.dataset.key === key;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
      if (on && focus) b.focus();
    }
    for (const [k, p] of Object.entries(panels)) p.hidden = k !== key;
    record("tab", { to: key });
  };
  const bar = el("div", { class: "tabs", role: "tablist", "aria-label": "This result" },
    el("span", { class: "tabs-pill", "aria-hidden": "true" }),
    tabs.map(([key, label]) => el("button", { type: "button", role: "tab", id: `tab-${key}`, "data-key": key,
      "aria-controls": `tp-${key}`, onclick: () => pick(key, false) }, label)));
  bar.addEventListener("keydown", e => {
    const i = tabs.findIndex(([k]) => k === tabChosen.get(h.id));
    const j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (j == null) return;
    e.preventDefault();
    pick(tabs[(j + tabs.length) % tabs.length][0], true);
  });
  pick(tabChosen.get(h.id) || "you", false);
  return bar;
}

// D-177: "On the pack": the user's photo (when this phone kept one) and the ingredient list as it
// was read, quoted, with the printed allergen line. Nothing here is our wording about the pack.
function onThePack(h) {
  const s = h.screen;
  const pic = packPicture(h);
  return [
    h.photo
      ? el("figure", { class: "pack-photo" }, el("img", { src: h.photo, alt: "Your photo of the pack" }),
          el("figcaption", { class: "muted small" }, "Your photo. It stays on this phone."))
      : pic
        ? el("figure", { class: "pack-photo" }, el("img", { src: pic.url, alt: pic.alt }),     // D-182
            pic.caption && el("figcaption", { class: "muted small" }, pic.caption))
        : el("p", { class: "muted" }, "No photo of this pack is kept on this phone."),
    el("div", { class: "card as-printed" },
      el("h2", {}, "The ingredient list as read"),
      el("ol", {}, s.ingredients.map(i => el("li", {}, i))),
      h.pack?.allergen_statement && el("p", {}, el("strong", {}, "Allergen line: "), el("q", {}, h.pack.allergen_statement))),
    h.barcode && el("p", { class: "muted small" }, "Barcode ", h.barcode),
    reportLink(h)];
}


// D-139, D-140: the kind of pack, in the server's words, with what the pack prints.
function kindView(s) {
  const k = s.kind;
  return kinded("div", "info", { class: "card kind", role: "note" },
    k.lines.map(t => el("p", {}, t)),
    // D-201: why an infant pack's printed name is checked as the kind it is (e.g. 7(3)'s "Infant Milk Food").
    k.why && el("details", { class: "more" }, el("summary", {}, k.why.title), el("p", {}, k.why.text),
      sourceList(k.why.sources)),
    k.evidence.length > 0 && el("p", { class: "muted small" }, "On the pack: ",
      k.evidence.map((e, i) => [i ? ", " : "", el("q", {}, e.text)])),
    k.sources?.length > 0 && sourceList(k.sources));
}

// D-201: an infant result's "Worth knowing" and "Good to know". Every word is the server's
// (lenses/screen.py, D-091); the app lays them out and draws the range bars from its numbers.
function infantView(s, h) {
  const inf = s.infant;
  const fold = (title, ...kids) => el("details", { class: "more" }, el("summary", {}, title), ...kids);
  const worth = inf.worth && el("div", { class: "worth card infant-worth" },
    el("h2", { class: "h-serif" }, `${inf.worth.title} (${inf.worth.items.length})`),
    el("ol", { class: "notes infant-notes" }, inf.worth.items.map(it => el("li", {},
      el("p", {}, it.text),
      it.bar && rangeBar(it.bar, true),
      it.more && fold(it.more.title, it.more.lines.map(t => el("p", {}, t)), sourceList(it.more.sources))))));
  const good = inf.good && el("div", { class: "card infant-good" },        // 2026-10-14: absent when empty
    el("h2", { class: "h-serif" }, inf.good.title),
    inf.good.blocks.map(b => el("div", { class: "infant-block" },
      el("h3", {}, b.title),
      b.lines.map(t => el("p", {}, t)),
      b.all && fold(b.all.button,
        el("ul", { class: "plain infant-rows" }, b.all.rows.map(r => el("li", { "aria-label": r.text },
          el("div", { class: "infant-row-head", "aria-hidden": "true" }, el("span", {}, r.label), el("span", {}, r.value_text)),
          rangeBar(r.bar, false)))),
        b.all.after && el("p", { class: "muted small" }, b.all.after)),
      b.which && fold(b.which.title, el("ol", { class: "infant-which" }, b.which.items.map(x =>
        el("li", {}, x.text, el("span", { class: "muted small" }, " " + x.basis))))),
      b.side && button(b.side.button, () => go("side/" + encodeURIComponent(h.id))))),
    // One "Sources" for the card, each source once.
    (() => {
      const seen = new Set();
      const all = inf.good.blocks.flatMap(b => b.sources || []).filter(x => !seen.has(x.cite) && seen.add(x.cite));
      return all.length > 0 && fold("Sources", sourceList(all));
    })());
  return [worth, good];
}

// D-201: FSSAI's range as a track with its limits printed, the pack's number as a marker. The
// numbers and their words are the server's (D-091); one neutral tone, no zones, no colours, no
// score: a fact beside FSSAI's own table, not a band.
function rangeBar(b, showValue) {
  const [a, z] = b.scale;
  const at = v => Math.max(0, Math.min(100, ((v - a) / (z - a)) * 100));
  const lo = at(b.low ?? a), hi = at(b.high ?? z), mark = at(b.value);
  const label = (text, x, cls = "") => el("span", { class: "rb-lim " + cls, style: `left:${Math.max(6, Math.min(94, x))}%` }, text);
  return el("div", { class: "range-bar" + (showValue ? " with-value" : ""), "aria-hidden": "true" },
    el("span", { class: "rb-axis" }),
    el("span", { class: "rb-track" + (b.high == null ? " open-end" : "") + (b.low == null ? " open-start" : ""),
                 style: `left:${lo}%;width:${hi - lo}%` }),
    b.low_text && label(b.low_text, lo, b.high == null ? "start" : ""),
    b.high_text && label(b.high_text, hi, b.low == null ? "end" : ""),
    el("span", { class: "rb-mark", style: `left:${mark}%` }),
    showValue && el("span", { class: "rb-val", style: `left:${Math.max(6, Math.min(94, mark))}%` }, b.value_text));
}

// D-134: a tile. Its words (title, chip) are the server's; the icon is decoration.
function tileLink(h, t) {
  return el("a", { class: `tile tile-${t.tone}`, href: `#/result/${encodeURIComponent(h.id)}/look/${encodeURIComponent(t.id)}` },
    el("span", { class: "tile-icon" }, kindIcon(t.kind === "not_permitted" ? "notpermitted" : "worth")),
    el("span", { class: "tile-text" }, el("strong", {}, t.title), el("span", { class: "tile-chip" }, t.chip)),
    el("span", { class: "tile-arrow", "aria-hidden": "true" }, icon("chevron-right")));
}

// D-134: a tile's own page, laid out from the server's `details[tile id]`.
function lookView(h, tileId) {
  const d = h.screen.details?.[tileId];
  // site-desktop: "Back to the result" is the header's back button now (setBack, in show()).
  const back = { "data-back": `#/result/${encodeURIComponent(h.id)}`, "data-back-label": "Back to the result" };
  if (!d) return el("section", { class: "stack look-page", ...back }, el("p", {}, "We couldn't find that on this result."));
  const part = (title, ...kids) => el("div", { class: "look-part" }, el("h2", {}, title), ...kids);
  return el("section", { class: "stack look-page", ...back },
    el("p", { class: "product" }, productName(h.product)),
    el("h1", {}, d.title),
    el("span", { class: `chip ${d.kind === "not_permitted" ? "tone-alert" : "tone-worth"}` },
      kindIcon(d.kind === "not_permitted" ? "notpermitted" : "worth", true), d.chip),
    d.note && kinded("p", d.kind === "not_permitted" ? "notpermitted" : "worth", { class: "card" }, d.note),
    d.what_it_is && part("What it is", el("p", {}, d.what_it_is)),
    d.what_research_found?.length > 0 && part("What the sources say", d.what_research_found.map(t => el("p", {}, t))),
    d.who_it_concerns && part("Who it concerns", el("p", {}, d.who_it_concerns)),
    part("On the label", el("p", {}, el("q", {}, d.on_the_label)), d.where && el("p", { class: "muted small" }, d.where)),
    d.sources?.length > 0 && part("Sources", sourceList(d.sources)),
    reportLink(h));
}

// D-123: the three answers as chips. One sentence open at a time, under the chips.
function answersView(summary) {
  const panel = el("div", { class: "answer-panel", id: "answer-panel", role: "region", hidden: true });
  const chips = summary.map(r => el("button", {
    // aria-expanded from a boolean: the wording lint reads every string literal in web/.
    type: "button", class: "answer-chip", "aria-expanded": String(false), "aria-controls": "answer-panel",
    onclick: e => {
      const b = e.currentTarget;
      const open = b.getAttribute("aria-expanded") === "true";
      chips.forEach(c => c.setAttribute("aria-expanded", String(c === b && !open)));
      if (open) { panel.hidden = true; return; }
      // replaceChildren() would print "false": the children go through el().
      panel.replaceChildren(el("div", {}, el("p", {}, el("strong", {}, r.label + ": "), r.text),
        // D-132: what ICMR-NIN and WHO say, one tap away under the sugar answer.
        r.more && el("details", { class: "more" }, el("summary", {}, r.more.title),
          r.more.body.map(t => el("p", {}, t)), sourceList(r.more.sources))));
      panel.hidden = false;
    },
  }, el("span", { class: "q" }, r.label), toneChip(r)));
  return el("div", { class: "answers-compact" }, el("div", { class: "answer-chips" }, chips), panel);
}

// Results kept on the phone from before web-27 (no tiles): the D-111 alert and the
// D-125/D-132/D-133 "Worth a look" rows, closed until tapped. Server text only.
function legacyLooks(s) {
  const look = (heading, more, body) => el("details", { class: "look" },
    el("summary", {},
      el("span", { class: "look-icon" }, kindIcon("worth")),
      el("span", {}, el("strong", {}, heading), el("span", { class: "look-more" }, more)),
      el("span", { class: "look-arrow", "aria-hidden": "true" }, el("span", {}, icon("chevron-right")))),
    el("div", { class: "look-body" }, body));
  const noteBody = n => [n.body.map(t => el("p", {}, t)),
    el("p", { class: "muted small" }, "On the label: ", el("q", {}, n.label_line)), sourceList(n.sources)];
  return [
    s.additive_alert && el("div", { class: "add-alert", role: "note" },
      el("span", { class: "add-icon" }, kindIcon("notpermitted")),
      el("div", {}, el("strong", {}, s.additive_alert.text), el("p", {}, s.additive_alert.detail))),
    ...(s.alerts || []).map(a => look(a.title, a.more, [a.body.map(t => el("p", {}, t)),
      el("p", { class: "muted small" }, "On the label: ", el("q", {}, a.label_line)),
      a.sources.length > 0 && sourceList(a.sources)])),
    ...(s.ingredient_notes?.tiles || []).map(n => look(n.heading, n.more, noteBody(n))),
    ...(s.nutrition?.tiles || []).map(n => look(n.heading, n.more, noteBody(n))),
  ];
}

// D-134: "More about this pack": what used to follow the answers, in the same order.
// D-177: the amount beside the line its sentence names, drawn from the server's numbers
// (screen.py `bar`). Decoration: the sentence says the same, so the bar is hidden from a
// screen reader. Amber only where the server's tone is "worth" (D-169); it fills in as it
// scrolls into view.
function nutBar(r, i = 0) {
  const top = Math.max(r.bar.value, r.bar.line) * 1.25 || 1;
  const pct = x => `${Math.min(100, (x / top) * 100).toFixed(1)}%`;
  const fill = el("span", { class: "nut-fill", style: `--to:${(Math.min(r.bar.value, top) / top).toFixed(3)}` });
  const bar = el("div", { class: `nut-bar nb-${r.tone}`, "aria-hidden": "true", style: `--i:${Math.min(i, 5)}` },
    el("span", { class: "nut-track" }, fill),
    el("span", { class: "nut-line", style: `left:${pct(r.bar.line)}` }),
    el("span", { class: "nut-line-label", style: `left:${pct(r.bar.line)}` }, `${fmtNum(r.bar.line)} ${r.bar.unit}`));
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { bar.classList.add("in"); io.disconnect(); } });
    io.observe(bar);
  } else bar.classList.add("in");
  return bar;
}
function fmtNum(x) { return Number.isInteger(x) ? String(x) : x.toFixed(1); }

function moreAbout(h, askTable, withList = true) {
  const s = h.screen;
  const out = [];
  const put = (...nodes) => out.push(...nodes.flat().filter(x => x != null && x !== false));
  const notes = s.ingredient_notes;

  if (s.nutrition) put(nutritionView(s.nutrition, h, askTable));
  if (notes?.lines?.length) put(el("details", { class: "item" }, el("summary", {}, notes.title),
    el("div", { class: "items" }, notes.lines.map(n => el("div", { class: "note-line" },
      el("strong", {}, n.title), " ", el("span", { class: "muted small" }, n.where),
      n.body.map(t => el("p", {}, t)),
      el("p", { class: "muted small" }, "On the label: ", el("q", {}, n.label_line)),
      sourceList(n.sources))))));
  if (s.band?.note && s.summary?.length) put(el("details", { class: "item" },
    el("summary", {}, "What does \"industrial\" mean?"), el("p", {}, s.band.note)));
  if (s.catalogue_note) put(kinded("p", "info", { class: "card" }, s.catalogue_note));  // D-107
  if (s.front_note) put(kinded("p", "problem", { class: "card" }, s.front_note));       // D-108
  if (s.last_verified) put(el("p", { class: "muted" }, s.last_verified));

  // Claim check, once released (D-051).
  if (s.claims?.length) {
    put(el("h2", {}, "The front of the pack"),
      el("ul", { class: "plain" }, s.claims.map(c => el("li", { class: c.contradicted ? "flag" : "" }, c.text))));
  }

  // Every additive as a card with its badge (D-111). When the server sends
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

  // Worth knowing, each with its why one tap away (D-056, D-066).
  const worth = (s.worth_knowing || []).filter(notCard);
  if (worth.length) {
    put(el("h2", {}, "Worth knowing"),
      el("div", { class: "items" }, worth.map(w => el("details", { class: `item concern-${w.concern}` },
        el("summary", {}, w.name),
        el("p", {}, w.why),
        el("p", { class: "muted" }, "On the label: ", el("q", {}, w.label_text)),
        el("p", { class: "tech" }, w.technical)))));
  }

  // Ordinary ingredients, grouped (D-065), then the full list as read.
  if (s.ordinary?.text && !s.summary?.length) {
    const plain = s.ordinary.additives.filter(notCard);
    put(el("details", { class: "item" },
      el("summary", {}, s.ordinary.text),
      plain.length > 0 && el("ul", { class: "plain" }, plain.map(a =>
        el("li", {}, el("strong", {}, a.name), ": ", a.why)))));
  }
  if (withList) put(el("details", { class: "item" },
    el("summary", {}, "The ingredient list as read"),
    el("ol", {}, s.ingredients.map(i => el("li", {}, i)))));

  // D-100: a front photo for the catalogue goes to our team; the result above
  // is still the reviewed record.
  const frontSent = h.catalogue?.front_received || h.catalogue?.queued_for_review === "front_photo";
  if (frontSent) {
    put(kinded("p", "done", { class: "muted" }, "Thanks. Our team has the front photo and will record what the pack says."));
  } else if (h.catalogue?.queued_for_review) {
    put(kinded("p", "info", { class: "muted" },
      "Our team will check this pack. After that, scanning its barcode gives the result straight away."));
  }
  if (h.catalogue?.front_wanted && h.barcode && !frontSent) {
    put(el("div", { class: "card note" },
      el("h2", {}, "Add the front of the pack?"),
      el("p", {}, "We have this pack's ingredients but not its front. One photo lets our team record " +
                  "its name and what it promises, for everyone who scans it."),
      button("Photograph the front", () => go("front/" + encodeURIComponent(h.id)))));
  }

  // D-127: what the words on this result mean, each linked to "How we check".
  if (s.glossary?.length) {
    put(el("details", { class: "item" }, el("summary", {}, "What these words mean"),
      el("dl", { class: "words" }, s.glossary.map(g => [
        el("dt", {}, g.term),
        el("dd", {}, g.text, " ", el("a", { href: g.url, target: "_blank", rel: "noopener" }, "More")),
      ]).flat())));
  }

  // What this covers - stated, never silent (D-037).
  put(el("details", { class: "item" }, el("summary", {}, "What this check covers"),
    el("ul", { class: "plain small" }, (h.disclosures || []).map(d => el("li", {}, d)))));
  put(el("p", { class: "muted small" }, s.checked ? [s.checked, " "] : null, s.scope));
  return out;
}

// D-127: the ring and the strip. Everything drawn comes from the server's `glance`
// block (types, counts, labels, caption); only the geometry is worked out here.
const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs, ...kids) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  kids.forEach(k => n.append(k));
  return n;
}
// `compact`: the result's first screen (D-134), with the one-sentence caption.
function glanceView(g, compact = false) {
  const order = ["worth", "sugar", "industrial", "additive", "other"].filter(t => g.counts[t]);
  const r = 46, c = 2 * Math.PI * r;
  const ring = svgEl("svg", { viewBox: "0 0 124 124", role: "img",
    "aria-label": order.map(t => `${g.labels[t]} ${g.counts[t]}`).join(", ") },
    svgEl("circle", { cx: 62, cy: 62, r, fill: "none", style: "stroke: var(--line)", "stroke-width": 18 }));
  // D-185 Phase 2: each entry's arc starts its own circle (rotated to its place), so it can fill from
  // its start: stroke-dashoffset from its length to 0, one after another (app.css .ring-seg).
  let off = 0;
  order.forEach((t, i) => {
    const len = Math.max(c * g.counts[t] / g.total - (order.length > 1 ? 2 : 0), 1);
    ring.append(svgEl("circle", { cx: 62, cy: 62, r, fill: "none", class: "ring-seg",
      style: `stroke: var(--g-${t}); --len: ${len.toFixed(2)}; --i: ${i}`, "stroke-width": 18,
      "stroke-dasharray": `${len} ${c}`, transform: `rotate(${(-90 + off / c * 360).toFixed(2)} 62 62)` }));
    off += c * g.counts[t] / g.total;
  });
  ring.append(svgEl("text", { x: 62, y: 64, "text-anchor": "middle", "font-size": 22, "font-weight": 700 }, String(g.total)));
  const dark = t => t === "worth" || t === "industrial";
  return el("div", { class: "glance" },
    el("h2", {}, "At a glance"),
    el("div", { class: "glance-row" }, ring,
      el("div", { class: "g-legend" }, order.map(t => el("div", {},
        el("i", { class: `g-${t}` }, t === "worth" ? "!" : ""), el("span", {}, g.labels[t]), el("b", {}, String(g.counts[t])))))),
    el("div", {}, el("div", { class: "g-strip", "aria-hidden": "true" }, g.entries.map(e =>
      el("span", { class: `g-${e.type}${dark(e.type) ? " dark" : ""}`, title: `${e.n}. ${e.text}` },
        e.type === "worth" ? "!" : String(e.n)))),
      el("div", { class: "g-ends" }, el("span", {}, "First: most"), el("span", {}, "Last: least"))),
    el("p", { class: "muted small" }, compact ? g.caption_short || g.caption : g.caption));
}

// D-153: one person's line in the deep panel. Red only for the avoid list and "may contain";
// amber for what couldn't be confirmed; calm otherwise. The words carry it all (D-060).
const PERSON_TONE = { contains: "stop", may_contain: "stop",
                      cannot_confirm: "unsure", uncertain: "unsure", worth_knowing: "unsure" };
// D-169: the symbol beside the line. The avoid list's cross only for "contains" and "may
// contain"; "worth a look" for the amber lines; the calm lines have none.
const PERSON_KIND = { contains: "avoid", may_contain: "avoid",
                      cannot_confirm: "worth", uncertain: "worth", worth_knowing: "worth" };
// D-188: a card only for a match (red) or a line we can't confirm (amber); the server sends no
// other. Any further match stays in view under the first line; a child's facts sit in More.
// A photo scan's amber card offers the retake (D-170, D-173); a barcode-only hit took no photo.
const LISTED = ["contains", "may_contain", "uncertain"];
const CARD = [...LISTED, "cannot_confirm", "worth_knowing"];          // cardPeople()
function personCard(p, h) {
  const who = profileByRef(p.ref);
  // D-198: the diet lines join the allergen lines under the first one; an amber diet line shows too.
  const also = [...p.allergens.slice(1).filter(a => LISTED.includes(a.state)),
                ...(p.diet || []).filter(d => d.state !== "not_listed" && !d.quiet && d.line !== p.line)];
  // D-140: a baby line carries its source; the cite is the server's words.
  const detail = p.status === "cannot_confirm" ? [] : p.child_facts;
  const kind = PERSON_KIND[p.status];
  const retake = h && p.status === "cannot_confirm" && h.screen?.state === "result" && !h.looked_up
    && !h.screen.list_choices;                                           // D-194: once, on the partial card
  // D-185 Phase 2 (D-177): the person's initial beside their line, the same disc as on home.
  return el("div", { class: `person-line ${PERSON_TONE[p.status] || "calm"}`, "data-status": p.status },
    who && avatar(who),
    el("span", { class: "who" }, who ? who.nickname : "Someone in your household"),
    el("b", { class: "line" }, kind && kindIcon(kind), fill(p.line, p.ref)),
    p.more && el("p", { class: "line-more" }, fill(p.more, p.ref)),          // D-198: the fact under a diet line
    also.length > 0 && el("ul", { class: "plain also" }, also.map(a => el("li", {}, fill(a.text, p.ref)))),
    retake && button("Retake the ingredients photo", () => retakeList(h, "partial")),
    detail.length > 0 && el("details", {}, el("summary", {}, "More"),
      el("ul", { class: "plain small" }, detail.map(f => el("li", {}, fill(f.text, p.ref),
        f.sources?.length > 0 && el("span", { class: "src" }, " ",
          f.sources.map(x => el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.cite))))))));
}

// D-188: "For you" opens with "Nothing extra for {name}'s age came up.", the weaker-check line
// for sesame when it isn't listed, then the one "may contain" reminder. A person with no match
// has no line here (Sushil, 2026-10-08, option B); a child's age line is a card at the top.
// Every word is the server's (screen.for_you, screen.for_you_note).
function forYouLines(s) {
  const rows = s.for_you || [];
  if (!rows.length && !s.for_you_note) return null;
  return el("ul", { class: "plain for-you-lines" }, rows.map(r => {
    const who = profileByRef(r.ref);
    return el("li", {},
      who && avatar(who),
      el("div", {}, r.lines.map(t => el("p", {}, fill(t, r.ref))),
        r.child_facts?.length > 0 && el("details", {}, el("summary", {}, "More"),
          el("ul", { class: "plain small" }, r.child_facts.map(f => el("li", {}, fill(f.text, r.ref),
            f.sources?.length > 0 && el("span", { class: "src" }, " ",
              f.sources.map(x => el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.cite)))))))));
  }), s.for_you_note && el("li", { class: "note-line" }, el("p", {}, s.for_you_note)));
}

// D-153: a tile as a note: the server's title and chip, its first source by name, and the way to the
// tile's page (D-134). D-185 Phase 2 (D-177): a row led by its kind's symbol (D-169), the chip under
// the title, and the first source's title on one line (its page and the full citations are on the
// tile's page).
function noteItem(h, t) {
  const d = h.screen.details?.[t.id];
  const names = (d?.sources || []).map(x => x.title || x.cite).filter(Boolean);
  const src = names.length > 1 ? `${names[0]} · and ${names.length - 1} more` : names[0];
  const kind = t.tone === "worth" ? "worth" : "info";
  return el("li", {},
    el("a", { class: "note-link", href: `#/result/${encodeURIComponent(h.id)}/look/${encodeURIComponent(t.id)}` },
      el("span", { class: `note-icon k-${kind}` }, kindIcon(kind, true)),
      el("span", { class: "note-text" }, el("strong", {}, t.title),
        el("span", { class: `chip tone-${t.tone === "worth" ? "worth" : "calm"}` }, t.chip),
        src && el("span", { class: "src" }, src)),
      el("span", { class: "tile-arrow", "aria-hidden": "true" }, icon("chevron-right"))));
}

// D-140: one question, for one profile, until it's answered; every word is the server's.
function bandQuestion(q) {
  const ref = bandToAsk(q.refs);
  if (!ref) return null;
  const box = el("div", { class: "card note", role: "group" });
  const answer = under2 => {
    answerBand(ref, under2);
    record("band_question", { answer: under2 ? "under_2" : "two_or_older" });
    box.replaceChildren(el("p", {}, fill(under2 ? q.done_yes : q.done_no, ref)));
  };
  box.append(
    el("p", {}, el("strong", {}, fill(q.text, ref))),
    el("p", { class: "muted small" }, q.why),
    el("div", { class: "row wrap" }, button(q.yes, () => answer(true)), button(q.no, () => answer(false))));
  return box;
}

// D-111: one additive, laid out from the server's item. The badge words and the
// kind come from lenses/screen.py; the icon is decoration (aria-hidden).
// D-169: "Not permitted in India" and "Worth knowing" take their kind's symbol; the badge's
// words say the same, so the symbol is decoration there. "Permitted" keeps its dot.
const BADGE_KIND = { not_permitted: "notpermitted", worth_knowing: "worth" };
function additiveCard(a) {
  const kind = a.badge?.kind || "none";
  return el("article", { class: `add add-${kind}` },
    el("div", { class: "add-top" },
      el("p", { class: "add-name" }, a.ins && el("small", {}, "INS " + a.ins), a.name),
      a.badge && el("span", { class: "badge" },
        BADGE_KIND[kind] ? kindIcon(BADGE_KIND[kind], true)
          : el("span", { class: "add-icon", "aria-hidden": "true" }, kind === "permitted" ? icon("dot") : ""),
        a.badge.text)),
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
  const err = errorLine();
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
    button("Cancel", () => window.history.back(), "link end"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (said.value.trim().length < 3 && note.value.trim().length < 3) {
      err.textContent = needText;
      return (said.value.trim() ? note : said).focus();
    }
    try {
      await reportRequest({ scan_id: h.scan_id, field: field.value,
                            proposed_value: said.value.trim() || null, note: note.value.trim() || null });
      show(el("section", { class: "stack done-step" }, doneSpot(), el("h1", {}, "Thank you"),
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
// D-202: an infant pack never joins Compare, even one saved before D-202.
function comparable(h) {
  return !!h?.pack && h.pack.kind !== "infant";
}

function toggleCompare(id) {
  const list = store.get("compare", []);
  store.set("compare", list.includes(id) ? list.filter(x => x !== id) : [...list, id].slice(-4));
}

function compare() {
  const ids = store.get("compare", []);
  const packs = ids.map(historyItem).filter(comparable);
  // D-200: supplements and infant foods are set side by side for anyone's avoid list, with no
  // pick and no age; food keeps D-057's pick for a child. The server checks the kinds again.
  const sideBySide = packs.length > 0 && packs.every(h => ["supplement", "infant"].includes(h.pack.kind));
  const kids = sideBySide ? profiles() : profiles().filter(p => p.age !== "adult");
  const others = history().filter(h => comparable(h) && !ids.includes(h.id)).slice(0, 10);
  let whoRef = kids[0]?.ref || null;
  let age = kids[0]?.age || "kid";
  const out = el("div", { class: "stack", "aria-live": "polite" });
  const refresh = id => { toggleCompare(id); updateNav(); route(); };

  const run = async () => {
    const who = whoRef ? profileByRef(whoRef) : null;
    out.replaceChildren(el("p", { class: "muted" }, "Comparing…"), skeleton(3));
    try {
      const { body } = await compareRequest({
        packs: packs.map(h => ({ id: h.id, name: productName(h.product), ...h.pack,
                                 confidence: Math.min(1, Math.max(0, h.pack.confidence)) })),
        age: who && !sideBySide && who.age !== "adult" ? who.age : sideBySide ? "kid" : age,
        avoid: who ? who.avoid : [],
        who: who && who.ref !== "me" ? "{name}" : null,     // D-074: the nickname is filled in here, not sent
      });
      out.replaceChildren(compareResult(body, whoRef));
      // D-178: the answer lands below the fold on a phone; bring it up.
      out.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    } catch (e) {
      out.replaceChildren(kinded("p", "problem", { class: "error" }, apiMessage(e)));
    }
  };

  return el("section", { class: "stack" },
    el("h1", {}, "Compare packs"),
    el("p", { class: "muted" }, sideBySide
      ? "Scan 2 to 4 packs of the same kind. We set their labels side by side and don't name a pick."
      : "Scan 2 to 4 packs from the same shelf. We name the better pick of these for a child."),
    // D-178: the chosen packs side by side, with a slot to fill until there are two.
    packs.length
      ? el("ul", { class: "compare-grid" },
          packs.map((h, i) => el("li", { class: "compare-tile", style: `--i:${i}` },
            packThumb(h),
            el("strong", {}, productName(h.product)),
            button("Remove", () => refresh(h.id), "link"))),
          packs.length < 2 && el("li", {}, el("button", { type: "button", class: "add-card slot",
            onclick: () => { resetPending(); go("scan"); } }, icon("plus"), "Scan a pack")))
      : el("div", { class: "card empty" }, spot("compare"), el("p", {}, "Nothing added yet.")),
    others.length > 0 && packs.length < 4 && el("details", {},
      el("summary", {}, "Add from recent scans"),
      el("ul", { class: "list" }, others.map(h => el("li", { class: "row between" },
        el("span", {}, productName(h.product)), button("Add", () => refresh(h.id), "link"))))),
    kids.length > 0 || sideBySide
      ? el("fieldset", {}, el("legend", {}, "For"), kids.map(k => el("label", { class: "choice" },
          el("input", { type: "radio", name: "who", checked: k.ref === whoRef,
                        onchange: () => { whoRef = k.ref; } }), " " + k.nickname)))
      : el("fieldset", {}, el("legend", {}, "Child's age"), AGES.map(a => el("label", { class: "choice" },
          el("input", { type: "radio", name: "age", checked: a.id === age, onchange: () => { age = a.id; } }),
          ` ${a.label} `, el("span", { class: "muted" }, a.sub)))),
    el("button", { type: "button", class: "btn primary", disabled: packs.length < 2, onclick: run }, "Compare"),
    button("Scan a pack to add", () => { resetPending(); go("scan"); }, "link end"),
    out);
}

// Outcome headings are the only compare wording written here; every reason
// comes from compare.py (D-057), which the wording lint checks.
function compareResult(r, ref) {
  if (r.outcome === "side_by_side") return sideBySideResult(r, ref);
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
    // D-178: the packs side by side, each with what compare.py said about it.
    el("div", { class: "compare-grid" }, r.packs.map((p, i) =>
      el("div", { class: "card compare-col" + (p.id === r.best ? " best" : ""), style: `--i:${i}` },
        packThumb(historyItem(p.id)),
        el("strong", {}, p.name),
        p.id === r.best && el("span", { class: "best-tag" }, "Better pick"),
        el("ul", { class: "plain small" },
          [...p.allergens, ...(p.diet || [])].filter(a => a.state !== "not_listed" && !a.quiet).map(a => el("li", { class: "flag" }, fill(a.text, ref))),
          p.facts.filter(f => f.tier !== "info" || f.positive).map(f =>
            el("li", { class: f.tier === "strong" ? "flag" : "" }, f.text)),
          !p.fully_checked && el("li", { class: "muted" }, "Not fully checked, so it can't be the pick."))))));
}

// D-200: supplements or infant foods, side by side. Every word is the server's
// (lenses/side_by_side.py); no pick, no badge, no order but the order the packs were added.
function sideBySideResult(r, ref) {
  const flags = p => [...p.allergens, ...p.diet];
  return el("div", { class: "stack side-by-side" },
    el("h2", {}, r.heading),
    el("p", { class: "muted" }, r.note),
    // One row per fact, the packs in columns, so each fact lines up across them (KEYS in side_by_side.py).
    el("div", { class: "sbs", style: `--n:${r.packs.length}` },
      r.packs.map((p, i) => el("div", { class: "card sbs-head", style: `--i:${i}` },
        packThumb(historyItem(p.id)),
        el("strong", {}, p.name),
        flags(p).length > 0 && el("ul", { class: "plain small" },
          flags(p).map(a => el("li", { class: "flag" }, fill(a.text, ref)))))),
      (r.packs[0]?.rows || []).map((row, k) => [
        el("h3", { class: "sbs-title" }, row.title),
        r.packs.map(p => el("div", { class: "sbs-cell" }, (p.rows[k]?.lines || []).map(t => el("p", {}, t)),
          p.rows[k]?.bar && rangeBar(p.rows[k].bar, false)))])),             // D-201: protein beside FSSAI's range
    r.sources?.length > 0 && el("details", { class: "more" }, el("summary", {}, "Sources"), sourceList(r.sources)));
}

// app-polish: grey lines where content is coming (the words beside them say what).
function skeleton(lines) {
  return el("div", { class: "skeleton", "aria-hidden": "true" },
    Array.from({ length: lines }, (_x, i) => el("span", { style: `width:${[92, 76, 84, 58, 70][i % 5]}%` })));
}

// ------------------------------------------------------------------ errors
function apiMessage(e) {
  if (!(e instanceof ApiError)) return "Something went wrong. Try again.";
  if (e.status === 0) return "No connection. Check your internet and try again.";
  // Our setup (key, credit), not a busy moment: "in a minute" would be untrue.
  if (e.body?.error === "vision_not_configured") return "The label reader isn't available right now. Please try again later today.";
  // D-154: every 503 from our server means the database is unavailable; nothing is "busy".
  if (e.status === 503) return "Something on our side isn't working right now. Try again in a minute.";
  // D-095: the server's own text says how long to wait.
  if (e.status === 429) return e.body?.detail || "You've checked a lot of packs in a short time. Please wait a few minutes.";
  // D-103: the server names what's wrong with a barcode or a photo file.
  const own = ["bad_barcode", "not_an_image", "photo_too_small", "photo_blank", "back_required", "rate_limited",
               "not_comparable"];      // D-200: a pack compares only with its own kind; the server says why
  if (own.includes(e.body?.error) && e.body.detail) return e.body.detail;
  if (e.status === 413) return "That photo is too large. Take it again a little further away.";
  if (e.status === 415) return "That file isn't a photo we can read. Use the camera instead.";
  return "Something went wrong on our side. Try again in a minute.";
}

// ------------------------------------------------------------------ message kinds (D-169)
// One symbol and one colour per kind of message, on every screen (icons.js KINDS, app.css
// .k-*): a photo or app problem, the avoid list, not permitted in India, worth a look,
// information, done. The kind comes from the server's fields; the words are unchanged.
function kinded(tag, kind, attrs, ...kids) {
  return el(tag, { ...attrs, class: `${attrs.class || ""} kmsg k-${kind}`.trim() }, kindIcon(kind), ...kids);
}

// D-170: a photo the server couldn't use, shown back to the user: their own photo (still on this
// phone, nothing uploaded again), the problem's short label, then the fix line. Every word is the
// server's (screen.PROBLEM_LABEL and the RETAKE lines); the photo shows only while it is held.
function photoProblem(p, photos = [], ...after) {
  // D-185 Phase 2: the reason and the fix first, then the photo they are about.
  return el("div", { class: "card k-problem photo-problem", role: "note" },
    el("p", { class: "problem-label" }, kindIcon("problem"), p.label),
    el("p", {}, p.fix),
    photos.length > 0 && el("div", { class: "problem-photos" },
      photos.map(([b, alt]) => el("img", { src: URL.createObjectURL(b), alt }))), ...after);
}

// The photos this result was read from, while this phone still holds them (pending is
// cleared on a new scan and lost on a reload). Different packs: the front beside the back.
function heldPhotos(h, both = false) {
  if (pending.resultId !== h.id || !pending.back) return [];
  return [both && pending.front && [pending.front, "Your front photo"], [pending.back, "Your back photo"]]
    .filter(Boolean);
}

// A partial read (D-066): its retake card names the problem over the photo too (D-170).
function partialRetake(s, h, ...after) {
  return s.problem ? photoProblem(s.problem, heldPhotos(h), ...after)
                   : kinded("div", "problem", { class: "card" }, el("p", {}, s.retake), ...after);
}

// A form's error line is a problem, never red. Every form sets its words with textContent,
// so setting it redraws the symbol beside them; "" empties the line (.error:empty hides it).
function errorLine() {
  const p = el("p", { class: "error kmsg k-problem", role: "alert" });
  const text = Object.getOwnPropertyDescriptor(Node.prototype, "textContent");
  Object.defineProperty(p, "textContent", {
    get() { return text.get.call(p); },
    set(v) { p.replaceChildren(...(v ? [kindIcon("problem"), el("span", {}, v)] : [])); },
  });
  return p;
}

// A D-123 answer chip: "worth" carries the worth-a-look symbol; "calm" stays plain.
function toneChip(r) {
  return el("span", { class: `chip tone-${r.tone}` }, r.tone === "worth" && kindIcon("worth"), r.chip);
}

// D-185 Phase 2: a screen that says something was sent opens on a check that draws itself (D-169's done).
function doneSpot() {
  const box = spot("check");
  box.classList.add("k-done");
  return box;
}

// The error and limit screens' drawing, in the problem colour.
function problemSpot(...names) {
  const box = spot(...names);
  box.classList.add("k-problem");
  return box;
}

function apiErrorView(e, retry) {
  if (e instanceof ApiError && e.status === 429 && e.body?.photo_limit) return photoLimit(e.body.photo_limit);
  return el("section", { class: "stack" },
    problemSpot(e instanceof ApiError && e.status === 0 ? "wifi" : "retake"),
    el("h1", {}, "That didn't work"),
    // D-170: a photo /scan turned down before the read names its problem (the server's label).
    e.body?.label && el("p", { class: "problem-label k-problem" }, kindIcon("problem"), e.body.label),
    el("p", {}, apiMessage(e)),
    retry && button("Try again", retry, "primary"),
    problemLink(),
    button("Home", () => go(""), "link end"));
}

// D-148: this phone's photo scans for the last 24 hours are used. One screen in place of
// an error, every word the server's (lenses/screen.py, D-091); the barcode scanner stays
// open to it. No retry button: the server says when the next photo scan is free.
function photoLimit(w) {
  record("photo_limit", {});
  return el("section", { class: "stack" },
    problemSpot("pack", "clock"),
    el("h1", {}, w.title),
    el("p", {}, w.text),
    el("p", {}, w.barcode),
    el("p", { class: "muted" }, w.when),
    button(w.scan, () => { resetPending(); go("scan"); }, "primary"),
    button("Home", () => go(""), "link end"));
}

function errorView(text) {
  return el("section", { class: "stack" }, problemSpot("pack"), el("h1", {}, "Sorry"), el("p", {}, text),
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
  const err = errorLine();
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
    button("Cancel", () => window.history.back(), "link end"));
  form.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      const { body } = await problemRequest({ kind: "user", comment: comment.value.trim() || null, ...incident });
      show(el("section", { class: "stack done-step" }, doneSpot(), el("h1", {}, "Thank you"),
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
  if (ids.length < (pending.sendNow ? 1 : 2)) return errorView("Take the photo twice first; then you can send it to us.");
  const err = errorLine();
  const go_ = el("button", { type: "button", class: "btn primary" }, "Send the photos");
  const view = el("section", { class: "stack send-step" },
    el("h1", {}, "Send it to us"),
    el("p", {}, "We'll read this pack's label by hand and tell you here when it's ready."),
    el("ul", { class: "plain small" },
      el("li", {}, ids.length === 1 ? "We keep the photos you took until our team has read them."
                                    : `We keep the ${ids.length} photos you took until our team has read them.`),
      el("li", {}, "Nothing else is sent. Nicknames stay on this phone.")),
    err, el("div", { class: "dock" }, go_, button("Cancel", () => window.history.back(), "link end")));
  go_.addEventListener("click", async () => {
    go_.disabled = true;
    try {
      await sendToUsRequest(ids);
      resetPending();
      show(el("section", { class: "stack done-step" }, doneSpot(), el("h1", {}, "Thank you"),
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

// D-068: a sample of which side to shoot. D-153: the back of a pack as panels, so "which part?"
// has an answer. Built from elements (no markup strings); the words are the app's own.
// Sushil, 2026-10-08: good example photos, shown on "Before you start" and on each camera step,
// so a shopper sees what reads well. A suggestion, never a rule: any clear photo is accepted.
// Drawn (a made-up pack), not a real brand's label. kind: "front", "list" or "table".
const EXAMPLE_LABEL = { front: "Front of the pack", list: "Ingredient list", table: "Nutrition table" };
function exampleShot(kind, caption = EXAMPLE_LABEL[kind]) {
  const tiny = t => el("span", { class: "ex-text" }, t);
  const art = kind === "front"
    ? el("div", { class: "ex-front" },
        el("span", { class: "ex-brand" }, "Sample Co."),
        el("span", { class: "ex-name" }, "Oat Biscuits"),
        el("span", { class: "ex-claim" }, "Baked with oats"),
        el("span", { class: "ex-disc" }),
        el("span", { class: "ex-net" }, "Net wt 100 g"))
    : kind === "list"
      ? el("div", { class: "ex-paper" },
          el("b", { class: "ex-head" }, "INGREDIENTS:"),
          tiny("Wheat flour (atta) (48%), oats (20%), sugar, edible vegetable oil (palm), invert syrup, " +
               "milk solids, raising agents (500(ii), 503(ii)), iodised salt, emulsifier (322), flavour."),
          el("b", { class: "ex-head" }, "ALLERGEN INFORMATION:"),
          tiny("Contains wheat, oats, milk."))
      : el("div", { class: "ex-paper" },
          el("b", { class: "ex-head" }, "NUTRITION INFORMATION"),
          tiny("Per 100 g"),
          el("table", { class: "ex-table" }, el("tbody", {},
            ...[["Energy", "468 kcal"], ["Protein", "7.2 g"], ["Carbohydrate", "68 g"], ["Total sugars", "21 g"],
                ["Added sugars", "18 g"], ["Total fat", "18 g"], ["Sodium", "310 mg"]]
              .map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, v))))));
  return el("figure", { class: "example-shot" },
    el("div", { class: "ex-photo " + kind, role: "img", "aria-label": `An example photo: the ${caption.toLowerCase()}, filling the frame, flat and sharp` },
      art, el("span", { class: "ex-ok", "aria-hidden": "true" }, icon("check"))),
    el("figcaption", {}, caption));
}

function packBack() {
  const lines = n => Array.from({ length: n }, () => el("span", { class: "pb-line" }));
  return el("div", { class: "pb", role: "img",
                     "aria-label": "The back of a pack: the ingredients list and the nutrition table are marked; the licence number is not needed" },
    el("div", { class: "pb-ing", "aria-hidden": "true" },
      el("span", { class: "pb-tag" }, "Photograph these"),
      el("span", { class: "pb-title" }, "INGREDIENTS:"), ...lines(3)),
    el("div", { class: "pb-ing pb-half", "aria-hidden": "true" }, el("span", { class: "pb-title" }, "NUTRITION"), ...lines(3)),
    el("div", { class: "pb-skip", "aria-hidden": "true" }, el("span", {}, "FSSAI licence"), ...lines(2), el("em", {}, "Not needed")));
}


// site-desktop (Sushil, 2026-10-02): the profile icon at the top right opens the menu, which
// holds every link the header and footer had (they stay in the footer too). A modal <dialog>:
// focus moves into it and back to the icon; Escape, a tap outside, a choice or the phone's
// Back close it (one history entry while it is open, dropped again when it closes).
function setupMenu() {
  const btn = document.getElementById("menu-btn");
  const menu = document.getElementById("menu");
  if (!btn || !menu || !menu.showModal) return;
  let open = 0;
  const onBack = () => close(1);
  function close(byBack) {
    if (!open) return;
    open = 0;
    removeEventListener("popstate", onBack);
    menu.close();
    btn.setAttribute("aria-expanded", String(false));   // a boolean: the wording lint reads string literals
    if (!byBack) window.history.back();     // window.history: this file's history() is the scan list
    btn.focus();
  }
  btn.addEventListener("click", () => {
    open = 1;
    menu.showModal();
    btn.setAttribute("aria-expanded", String(true));
    window.history.pushState({ menu: 1 }, "");
    addEventListener("popstate", onBack);
    record("menu");
  });
  menu.addEventListener("cancel", e => { e.preventDefault(); close(0); });       // Escape
  menu.addEventListener("click", e => {
    if (e.target === menu) return close(0);                                       // outside the panel
    const a = e.target.closest("a");
    if (!a) return;
    e.preventDefault();
    const href = a.getAttribute("href");
    close(0);
    // once Back has dropped the menu's entry, go where the link points
    addEventListener("popstate", () => { if (href.startsWith("#")) location.hash = href; else location.href = href; },
                     { once: true });
  });
}

// D-176: the bottom bar's Scan button opens what "Scan here" opens.
// D-185: the header's edge line shows once the page has moved under it.
function setupHeaderEdge() {
  let queued = false;
  const set = () => { queued = false; document.body.classList.toggle("scrolled", window.scrollY > 2); };
  window.addEventListener("scroll", () => { if (!queued) { queued = true; requestAnimationFrame(set); } }, { passive: true });
  set();
}

// D-185 (Sushil, 2026-10-08): the calm loops (home's drawing, the scan line, the reading) play on while
// they are on screen. With the app in the background they hold still (app.css .app-away), and a loop
// scrolled out of view holds where it is (playWhileSeen).
function setupLoops() {
  const away = () => document.documentElement.classList.toggle("app-away", document.hidden);
  document.addEventListener("visibilitychange", away);
  away();
}

function playWhileSeen(node) {
  if (!("IntersectionObserver" in window)) return node;
  const io = new IntersectionObserver(es => {
    if (!node.isConnected) return io.disconnect();
    node.classList.toggle("still", !es[es.length - 1].isIntersecting);
  });
  io.observe(node);
  return node;
}

function setupTabbar() {
  const scanBtn = document.getElementById("tab-scan");
  if (scanBtn) scanBtn.addEventListener("click", () => { record("tab_scan"); resetPending(); go("scan"); });
  const topScan = document.getElementById("top-scan");      // D-185: the header's "Scan a pack", 1024 px up
  if (topScan) topScan.addEventListener("click", () => { record("tab_scan"); resetPending(); go("scan"); });
  updateNav();
}

// ------------------------------------------------------------------ start
setupMenu();
setupTabbar();
setupHeaderEdge();
setupLoops();
window.addEventListener("hashchange", route);
deviceId();
record("start", { app_version: APP_VERSION });
route();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
