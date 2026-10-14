"""
The PWA in web/ (D-010). No browser here: these are static checks on the files
and on how the API serves them.

Why static checks are enough for the rules that matter:
- Wording (D-042/D-071): every string literal and every piece of HTML text in
  web/ goes through the same lint as the data tables and API output.
- No score in the consumer UI (D-064): the client never reads score or grade.
- Server text is untrusted (it quotes the label): no innerHTML except the one
  helper that draws our own constant SVG.
- Nicknames stay on the device (D-074): the request builder sends ref, age and
  avoid only. The API side is tested in test_screen.py.
"""
import json
import os
import re

from fastapi.testclient import TestClient

from insidelabel.api.main import WEB_DIR, app
from test_wording import assert_clean

c = TestClient(app)
JS = {n: open(os.path.join(WEB_DIR, n), encoding="utf-8").read()
      for n in os.listdir(WEB_DIR) if n.endswith(".js")}
HTML = open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8").read()

_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\"'`])//[^\n]*", re.S)
_STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')


def js_strings(src):
    return [m.group(0)[1:-1] for m in _STRING.finditer(_COMMENT.sub("", src))]


def test_app_is_served_with_the_right_types():
    for path in ("/", "/privacy", "/about"):                       # D-102: the public pages
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"], path
        assert 'href="/app/"' in r.text or path != "/", path
    assert "text/css" in c.get("/site.css").headers["content-type"]
    assert "text/html" in c.get("/app/").headers["content-type"]
    for name in JS:
        assert "javascript" in c.get(f"/app/{name}").headers["content-type"], name
    m = c.get("/app/manifest.webmanifest")
    assert m.headers["content-type"].startswith("application/manifest+json")
    manifest = m.json()
    assert manifest["start_url"] == manifest["scope"] == "/app/"
    assert {i["purpose"] for i in manifest["icons"]} >= {"any", "maskable"}


def test_every_shell_file_exists():
    sw = JS["sw.js"]
    shell = json.loads("[" + re.search(r"SHELL = \[(.*?)\];", sw, re.S).group(1) + "]")
    for f in shell:
        if f != "./":
            assert os.path.exists(os.path.join(WEB_DIR, f)), f


def test_service_worker_never_caches_the_api():
    # A cached /scan answer would be a stale verdict.
    assert 'url.pathname.startsWith("/app/")' in JS["sw.js"]


def test_web_wording():                                             # D-042, D-071
    for name, src in JS.items():
        assert_clean(js_strings(src), f"web/{name}")
    assert_clean([re.sub(r"<[^>]+>", " ", HTML)], "web/index.html")


def test_no_score_in_the_ui():                                      # D-064
    for name, src in JS.items():
        code = _COMMENT.sub("", src)
        assert not re.search(r"\.(score|grade|display_score|display_binary)\b", code), name


def test_no_html_from_strings():
    for name, src in JS.items():
        uses = re.findall(r"\.(?:innerHTML|outerHTML)\s*=|insertAdjacentHTML", _COMMENT.sub("", src))
        assert not uses, (name, uses)   # D-153: svg() went with the old sample drawing; none left


def test_only_ref_age_avoid_leave_the_device():                     # D-074
    m = re.search(r"export function profilesForServer\(\) \{(.*?)\n\}", JS["lib.js"], re.S)
    assert m and "({ ref: p.ref, age: p.age, avoid: p.avoid })" in m.group(1)
    assert "nickname" not in m.group(1)
    # /scan's `who` would carry a name; the app never sends it.
    assert 'fd.append("who"' not in JS["lib.js"]


# ---------------------------------------------------------------- D-092 flight recorder

def test_app_and_shell_versions_move_together():
    app = re.search(r'APP_VERSION = "web-(\d+)"', JS["lib.js"]).group(1)
    sw = re.search(r'VERSION = "il-shell-(\d+)"', JS["sw.js"]).group(1)
    assert app == sw, "bump APP_VERSION (lib.js) and VERSION (sw.js) together"


def test_slow_scan_words_name_no_cause():                            # D-124, D-154
    # The app can't see why a read is slow: with Cloud Vision down the fallback reader runs,
    # and "the reader is busy" would be untrue. The 20 s line says only what the app knows.
    app_js = JS["app.js"]
    assert "Taking longer than usual. It is still working." in app_js
    assert "reader is busy right now. It is still working" not in app_js


def test_app_never_shows_a_machine_field_as_words():                  # 2026-10-04
    # test_screen.py skips these fields when it looks for file names and table keys, so
    # the app must never draw one as text: only as a class, an attribute, a link or a test.
    # Caught: a field passed to el() as content, alone or after "words " +. Not caught: a
    # field put into a template string; fill(text, ref) picks a nickname and is allowed.
    from test_screen import MACHINE_FIELDS
    src = _COMMENT.sub("", JS["app.js"])
    child = re.compile(r",\s*(?:\"[^\"]*\"\s*\+\s*)?\b[A-Za-z_$][\w$]*\??\.(%s)\b\s*(?=[,)])"
                       % "|".join(sorted(MACHINE_FIELDS)))
    shown = [src[max(0, m.start() - 60):m.end()] for m in child.finditer(src)
             if not re.search(r"\bfill\([^()]*$", src[max(0, m.start() - 80):m.start()])]
    assert not shown, shown


def test_503_words_say_what_a_503_is():                              # D-154
    # Every 503 the server sends is storage_unavailable: the reader is never what failed.
    app_js = JS["app.js"]
    assert "Something on our side isn't working right now. Try again in a minute." in app_js
    assert all("label reader is busy" not in src for src in JS.values())


def test_trail_keeps_no_query_strings_or_names():
    lib = JS["lib.js"]
    assert 'path: path.split("?")[0]' in lib                 # /updates?device_id=… → /updates
    info = _COMMENT.sub("", re.search(r"export function clientInfo\(\) \{(.*?)\n\}", lib, re.S).group(1))
    assert "profilesForServer()" in info and "nickname" not in info
    summary = re.search(r"function screenSummary\(s\) \{(.*?)\n\}", lib, re.S).group(1)
    assert "fill(" not in summary                             # {name} placeholders, not nicknames


def test_every_request_carries_an_id():
    assert '"X-Request-ID": rid' in JS["lib.js"]


def test_problem_link_on_every_page_and_error_screen():
    assert 'href="#/problem"' in HTML
    app = _COMMENT.sub("", JS["app.js"])
    for fn in ("apiErrorView", "errorView"):
        body = re.search(rf"function {fn}\(.*?\n\}}", app, re.S).group(0)
        assert "problemLink()" in body, fn



def test_public_pages_pass_the_wording_lint():
    """D-102: the landing page and the drafts travel without the app around them."""
    site = os.path.join(WEB_DIR, "site")
    for name in os.listdir(site):
        if name.endswith(".html"):
            text = re.sub(r"<[^>]+>", " ", open(os.path.join(site, name), encoding="utf-8").read())
            assert_clean([text], name)


def test_empty_report_sentence_matches_the_server():
    """D-109: the app refuses an empty report with the server's own sentence."""
    from insidelabel.api.main import EMPTY_REPORT
    src = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
    assert f'"{EMPTY_REPORT}"' in src
    assert '"empty_report"' in src


def test_how_we_check_page_has_a_section_for_every_word():          # D-127
    from insidelabel.lenses import screen
    r = c.get("/how")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    for key in list(screen.GLOSSARY) + ["avoid", "glance"]:
        assert f'id="{key}"' in r.text, key


def test_the_table_offer_comes_last_and_uses_the_servers_words():      # D-168
    app = JS["app.js"]
    assert "tablephoto" in app and 'store.get("tableSent", {})' in app
    # Placed after "More about this pack", the last block of the result (never above D-060's lines).
    assert app.index('s.more_title || "More about this pack"') < app.index("const offer = s.table_offer;")
    # Every word is the server's (lenses/screen.py TABLE_OFFER, TABLE_ANSWER).
    for words in ("Add the nutrition table?", "Send the table", "nothing was added"):
        assert words not in app
    assert 'fd.append("table_only", "true")' in JS["lib.js"]


def test_the_light_hint_is_for_pouches_and_shiny_packs():             # D-167
    # A tester's glossy, curved ketchup pouch with tiny text (Sushil, 2026-10-07, "yes pls").
    app = JS["app.js"]
    assert ("Hold the phone close and steady. On a pouch or a shiny pack, lay it on a table, smooth it "
            "flat and tilt it away from the light.") in app
    assert "Hold the pack flat and close, without glare." not in app


def test_how_we_check_says_there_is_no_score():                         # D-165, D-064
    # Testers (and a help bot) ask for a pack's score: the page says there is none, and
    # "score" appears nowhere else on it, so "doesn't change the score" can't come back.
    r = c.get("/how")
    start = r.text.index('<h2 id="score">No score</h2>')
    end = r.text.index("<h2", start + 1)
    section, rest = r.text[start:end], r.text[:start] + r.text[end:]
    assert "doesn't give a pack a score, a grade or stars" in section
    assert not re.search(r"\bscore\b", rest, re.I)
    assert "doesn't change the score" not in r.text
    assert start < r.text.index('<h2 id="avoid">')                    # right after the intro
    # The headlines are quoted in the app's own words (lenses/screen.py BAND_LABEL).
    from insidelabel.lenses import screen
    assert f'"{screen.BAND_LABEL["clean"]}"' in r.text and f'"{screen.BAND_LABEL["mixed"]}"' in r.text
    assert '"No concerns found"' not in r.text


def test_label_photos_come_in_steps():                                   # D-171 (was D-153's one page)
    """A tester liked the barcode step and was lost on the one long label page (2026-10-07)."""
    app = JS["app.js"]
    assert "Step ${n} of ${steps()}" in app
    assert "const steps = () => frontNeeded() ? 4 : 3;" in app          # D-181: the front is step 4
    assert 'stepLine(1, "Barcode")' in app
    # Step 2: one line under the camera; step 3 only when the table isn't in that photo.
    assert 'title: n === 1 ? "Photograph the ingredient list"' in app
    assert '"Fit the list, from \\"Ingredients\\" to the last word"' in app
    assert 'el("h1", { class: "dock-q" }, "Is the nutrition table in this photo too?")' in app   # D-185: by its answers
    assert '"Yes, it\'s in this photo"' in app and '"No, photograph the table"' in app          # D-199
    assert '"The list goes on: add the next part"' in app and '"This pack has no table"' in app   # D-194
    assert 'title: "Photograph the nutrition table"' in app
    # The table rides as the next part, so /scan's roles are unchanged (back, back2, back3).
    assert "const MAX_PHOTOS = 3;" in app and 'role: "back" + n, table: true' in app
    # D-163 and D-167's hints and the drawing move to Tips.
    tips = app[app.index("function tipsSheet("):app.index("function leadWith(")]
    assert "keep it in the photo too. We check the number against it." in tips
    assert 'pending.barcode ? el("div", {}, el("dt", {}, "Barcode"),' in tips
    assert "packBack()" in tips and '"Photograph these"' in app and '"NUTRITION"' in app
    assert app.count('"Not needed"') == 1                           # only the licence
    # D-181 (Sushil, 2026-10-08, "make the front photo mandatory"): while the catalogue wants the
    # front (D-100), it is step 4 and the check waits for it and for D-035's pairing box. It still
    # rides the one /scan.
    review = app[app.index("function shotReview("):app.index("function frontShot(")]
    assert "front of the pack too (optional)" not in app
    assert "const frontNeeded = () => !!pending.frontWanted;" in app
    assert "const yes = frontNeeded() && !pending.front ? () => show(frontShot()) : () => sendPhotos();" in review
    assert ': frontNeeded() && !pending.front ? button("Next: the front of the pack", yes, "primary")' in review
    assert "&& !frontIn;   // the table question" in review                  # answered before the front
    assert "if (frontIn && !pending.pairing) check.disabled = true;" in review
    assert "if (frontIn) check.disabled = !pending.pairing;" in review
    assert review.index('id: "pairing"') < review.index("    check,\n")       # the box above the check
    assert '" Both photos are of the same pack"' in review                    # D-035's pairing
    assert '" All these photos are of the same pack"' in review
    front = app[app.index("function frontShot("):app.index("// One photo of the label.")]
    assert 'role: "front", checkAs: "front"' in front and "show(shotReview(undefined, res))" in front
    assert 'stepLine(4, "Front")' in front and '"Not now"' not in front and '"Optional"' not in front
    assert "back: () => show(shotReview())," in front and '"Back"' not in front
    # Sushil, 2026-10-08: no loose "Tips" and "Back" links on the camera pages. Tips is a pill beside
    # the title; the header's arrow goes back to the photos in hand (a screen's backTo).
    shot = app[app.index("function labelShot("):app.index("function tipsSheet(")]
    assert 'el("div", { class: "cam-title" }, el("h1", {}, o.title), tips)' in shot
    assert 'class: "tips-btn"' in shot and 'button("Tips"' not in app
    assert "if (o.back) view.backTo = o.back;" in shot
    assert 'if (backTo) back = el("button", { type: "button", class: "top-back", "aria-label": "Back", onclick: backTo }' in app
    # An answer, as a button; with the front still to take (D-181) it leads there, not to the read.
    assert 'button("This pack has no table", () => frontNeeded() && !pending.front ? show(frontShot()) : sendPhotos())' in app
    assert '"Not now"' not in app[app.index("function front("):app.index("function recheckPhoto(")]
    # Off where the front is on file, and for D-175's list-only re-check.
    recheck = app[app.index("function recheckPhoto("):app.index("// ------------------------------------------------------------------ a table photo")]
    assert "pending.frontWanted = !!h.catalogue?.front_wanted;" in recheck
    assert "if (listOnly) pending.frontWanted = false;" in recheck
    assert '"Add the front of the pack?"' in app                              # the result's offer stays
    # D-168 and D-133's table photos use the same step 3 camera.
    assert "return labelShot(o);" in app[app.index("function tablephoto("):]
    assert "return tableShot(" in app[app.index("function table() {"):]


def test_the_live_shutter_is_switched_on_by_the_server_and_falls_back():   # D-171
    app, cam = JS["app.js"], JS["camera.js"]
    # Off by default (Sushil, 2026-10-07): today's camera app until he has compared the two.
    assert "liveShutter = !!body.live_shutter;" in app
    assert "const liveOn = () => liveShutter && TOUCH && labelCameraSupported();" in app
    # Full-resolution still where the phone has it; otherwise the camera app's input.
    assert '"ImageCapture" in window' in cam and "capture.takePhoto(settings)" in cam
    assert 'capture: "environment"' in app
    assert "appCamera(\"We couldn't open the camera here, so your phone's camera app takes the photo.\")" in app
    # Hints on the phone only: no request before the shutter.
    label = cam[cam.index("export async function startLabelCamera("):]
    assert "fetch(" not in label and "Request(" not in label
    assert '"Too dark"' in app and '"Hold still"' in app
    # The shot goes up as "live", so the stored scans tell the two apart.
    assert 'checkShot(o, blob, "live", again)' in app


def test_access_says_whether_the_live_shutter_is_on(monkeypatch):     # D-171
    from insidelabel.api import main
    monkeypatch.delenv("INSIDELABEL_LIVE_SHUTTER", raising=False)
    assert c.get("/access").json()["live_shutter"] is False
    monkeypatch.setenv("INSIDELABEL_LIVE_SHUTTER", "on")
    assert c.get("/access").json()["live_shutter"] is True
    monkeypatch.setattr(main, "LIVE_SHUTTER", False)
    assert c.get("/access").json()["live_shutter"] is False


def test_result_puts_people_first_and_folds_the_rest():                # D-153
    app = JS["app.js"]
    body = app[app.index("function result(id, sub, tileId)"):app.index("function kindView(s)")]
    # The panel comes first: the pack's name as the h1, then the person lines (D-060).
    assert body.index('class: "deep opener result-top"') < body.index("headline")
    assert 'el("h1", { class: "product" }' in body
    # Red only for the avoid list and "may contain".
    tone = app[app.index("const PERSON_TONE"):app.index("function personCard")]
    assert re.findall(r'(\w+): "stop"', tone) == ["contains", "may_contain"]
    # Everything else waits under "Worth knowing (n)", except a not-permitted additive (D-111).
    assert "Worth knowing (${notes.length})" in body
    assert 't.kind === "not_permitted"' in body and 'class: "worth card"' in body          # D-185 Phase 2: a card of rows
    # The result ends on the next pack (D-057), and says what isn't built yet.
    assert "Holding another pack? Scan it to compare" in body
    assert body.count('class: "pending"') == 2


def test_report_faces_are_cached_on_use_not_at_install():              # D-153
    """Precached at install, the three report faces delayed the first screen's own fonts and its
    footer moved (Lighthouse CLS 0 to 0.16, measured 2026-10-02). The fetch handler caches them
    the first time a screen uses them."""
    sw = open(os.path.join(WEB_DIR, "sw.js"), encoding="utf-8").read()
    shell = sw[sw.index("const SHELL"):sw.index("];", sw.index("const SHELL"))]
    for f in ("source-serif-4", "ibm-plex-mono", "dm-sans"):
        assert f not in shell
    # D-185: the two faces left are both the first screen's, so both are precached.
    assert '"fonts/figtree.woff2", "fonts/bricolage-grotesque.woff2"' in shell
    # ...and not preloaded: measured, a preload cost the first screen's LCP (index.html says how much).
    assert 'rel="preload"' not in HTML
    assert "caches.open(VERSION).then(c => c.put(e.request, copy))" in sw


def test_the_footer_waits_for_a_loading_screen():                      # D-153 step 2, fixed 2026-10-03
    """On a first visit the footer showed under "Loading…" and jumped when "Before you start" arrived
    (Lighthouse CLS 0.16 in about half of fresh loads). A busy screen reveals it only once filled."""
    app = JS["app.js"]
    show = app[app.index("function show(node)"):app.index("function settled(")]
    assert 'getAttribute("aria-busy") === "true"' in show and "settled()" in show
    assert 'document.body.classList.add("ready")' not in show
    agree = app[app.index("function agree()"):app.index("function feedback(")]
    assert agree.count("settled(view)") == 2                        # the terms, or the error in their place


def test_every_script_parses_as_a_module(tmp_path):
    """The app's files are ES modules (D-090). `node --check` on a .js file parses it as a script, which let a
    stray ")" through on 2026-10-03; a .mjs copy is parsed as a module, like the browser does."""
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node isn't installed")
    for name, src in JS.items():
        copy = tmp_path / (name[:-3] + ".mjs")
        copy.write_text(src, encoding="utf-8")
        r = subprocess.run([node, "--check", str(copy)], capture_output=True, text=True)
        assert r.returncode == 0, (name, r.stderr[-400:])



# ---------------------------------------------------------------- D-169: message kinds
CSS = open(os.path.join(WEB_DIR, "app.css"), encoding="utf-8").read()
KIND_SYMBOL = {"problem": "retake", "avoid": "circlecross", "notpermitted": "triangle",
               "worth": "circlealert", "info": "info", "done": "check"}
KIND_TOKEN = {"problem": "--problem", "avoid": "--stop", "notpermitted": "--stop",
              "worth": "--unsure", "info": "--calm", "done": "--brand"}


def _rule(selector):
    """The declarations of every CSS rule whose selector list names `selector`."""
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", _COMMENT.sub("", CSS)):
        if selector in [s.strip() for s in sel.split(",")]:
            out.append(body)
    return " ".join(out)


def _tokens(dark):
    """The first :root block (light) or the first dark-mode :root block's custom properties."""
    src = _COMMENT.sub("", CSS)
    if dark:
        src = src[src.index("@media (prefers-color-scheme: dark)"):]
    body = re.search(r":root\s*\{([^{}]*)\}", src).group(1)
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body))


def test_every_kind_has_its_symbol_name_class_and_tokens():
    icons = JS["icons.js"]
    for kind, symbol in KIND_SYMBOL.items():
        assert re.search(rf"^\s*{symbol}: \[", icons, re.M) or symbol == "check", symbol
        assert re.search(rf'{kind}: \["{symbol}", "[A-Z][^"]+"\]', icons), kind      # its accessible name
        assert f"var({KIND_TOKEN[kind]})" in _rule(f".ki-{kind}"), kind               # the symbol's ink
        assert _rule(f".k-{kind}"), kind                                              # the block's colours
        for dark in (False, True):
            assert KIND_TOKEN[kind] in _tokens(dark), (kind, dark)
    for dark in (False, True):
        assert {"--problem", "--problem-bg"} <= set(_tokens(dark)), dark
    # kindIcon names the symbol unless the words beside it say the same.
    assert 'svg.setAttribute("aria-label", label)' in icons and 'svg.setAttribute("role", "img")' in icons


def _ratio(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_problem_colour_is_readable_in_light_and_dark():
    for dark in (False, True):
        t = _tokens(dark)
        for bg in ("--bg", "--surface", "--problem-bg"):
            assert _ratio(t["--problem"].strip(), t[bg].strip()) >= 4.5, (dark, bg)
        for kind, token in KIND_TOKEN.items():                         # each symbol on the page, 3:1
            for bg in ("--bg", "--surface"):
                assert _ratio(t[token].strip(), t[bg].strip()) >= 3, (dark, kind, bg)


def test_no_error_or_refusal_is_red():
    for sel in (".error", ".check.bad", ".check.unknown", ".k-problem", ".ki-problem", ".spot.k-problem"):
        assert "--stop" not in _rule(sel), sel
    app = JS["app.js"]
    assert 'class: "error"' not in app.replace('{ class: "error" }, apiMessage', "")   # only through errorLine/kinded
    assert 'el("p", { class: "error", role: "alert" })' not in app
    assert '"card warn"' not in app                                     # the retake card was amber
    for retake in re.findall(r"\(s\.retake\)[^\n]*|\n[^\n]*s\.retake\),", app):
        assert '"problem"' in retake or "partialRetake(" in retake, retake       # D-170: both draw a problem
    assert 'kinded("div", "problem", { class: "card" }, el("p", {}, s.retake)' in app
    assert 'icon(res.ok ? "check" : "cross")' not in app
    assert re.search(r'kinded\("p", res\.ok \? "done" : "problem"', app)
    assert 'problemSpot(e instanceof ApiError && e.status === 0 ? "wifi" : "retake")' in app
    assert 'kinded("p", t.kind || "problem"' in app                   # D-168's answer, by the server's kind


def test_the_avoid_list_and_not_permitted_stay_red():
    for sel in (".ki-avoid", ".ki-notpermitted", ".k-avoid", ".k-notpermitted", ".person-line.stop",
                ".chip.tone-alert", ".add-not_permitted .badge"):
        assert "--stop" in _rule(sel), sel
    app = JS["app.js"]
    assert 'const PERSON_KIND = { contains: "avoid", may_contain: "avoid",' in app
    assert 'const BADGE_KIND = { not_permitted: "notpermitted", worth_knowing: "worth" };' in app
    assert 'kindIcon(t.kind === "not_permitted" ? "notpermitted" : "worth")' in app
    # D-060's allergen tokens keep their meaning: the person lines' classes are unchanged.
    assert ('const PERSON_TONE = { contains: "stop", may_contain: "stop",\n'
            '                      cannot_confirm: "unsure", uncertain: "unsure", worth_knowing: "unsure" };') in app


def test_the_kind_comes_from_the_server_never_from_words_or_score():
    from insidelabel.lenses import screen
    assert set(screen.TABLE_ANSWER_KIND) == set(screen.TABLE_ANSWER)
    assert set(screen.TABLE_ANSWER_KIND.values()) <= set(KIND_SYMBOL)
    body = JS["app.js"]
    for call in re.findall(r"kinded\([^\n]*|kindIcon\([^\n]*", body):
        assert "score" not in call and ".text ===" not in call, call


# ---------------------------------------------------------------- D-170: the photo problem
def _retake_branch(app):
    start = app.index('if (s.state === "retake") {')
    return app[start:app.index("return view;", start)]


def test_the_refusal_shows_the_photo_and_its_problem_without_report_a_mistake():
    app = JS["app.js"]
    branch = _retake_branch(app)
    assert "photoProblem(s.problem, heldPhotos(h" in branch
    assert "reportLink(h)" not in branch and "problemLink()" in branch          # nothing was read to correct
    # The photo is the one still on this phone: no request, no upload.
    held = app[app.index("function heldPhotos("):app.index("function partialRetake(")]
    assert "pending.resultId !== h.id" in held and "Request(" not in held
    assert app.count("put(partialRetake(s, h,") + app.count("you(partialRetake(s, h,") == 2   # the partial read's card too
    assert 'class: "card k-problem photo-problem"' in app


def test_the_photo_check_names_its_problem_and_offers_retake():
    app = JS["app.js"]
    assert re.search(r'res\.label\s*\n\s*//[^\n]*\n\s*\? kinded\("div", "problem", \{ class: "check bad"', app)
    assert 'button("Retake", retake)' in app
    assert 'checkLine(res, () => document.getElementById("pick-" + role)?.click(), role)' in app


def test_problem_labels_come_from_the_server():
    from insidelabel.lenses import screen
    for label in set(screen.PROBLEM_LABEL.values()):
        assert all(label not in js for js in JS.values()), label
    assert "p.label" in JS["app.js"] and "e.body.label" in JS["app.js"] and "res.label" in JS["app.js"]


def test_a_blocked_read_offers_send_it_to_us_at_once():                    # D-172
    app = JS["app.js"]
    assert 's.send_now && pending.refused.length >= 1 && button("Send it to us", () => go("send"), "primary")' in app
    assert 's.send_now ? "" : "primary"),' in app                           # Retake steps back
    assert '!s.send_now && pending.refused.length >= 2 && button("Send it to us", () => go("send")),' in app
    assert "pending.sendNow = !!body.screen.send_now;" in app
    assert "if (ids.length < (pending.sendNow ? 1 : 2))" in app


def test_a_retake_keeps_the_table_photo_and_the_front():                     # D-173
    """Sushil, 2026-10-07: "it should reuse as it reads properly in previous photo"."""
    app = JS["app.js"]
    fn = app[app.index("function retakeList("):app.index("// After a shot: the photos in hand")]
    # The list's photos go; the table's stay, unless the photos aren't of a pack at all.
    assert 'const tables = mine && !NOT_A_PACK.includes(code) ? partRows().filter(r => r[2] === "table") : [];' in fn
    # D-191: a refusal that read the table cleanly keeps this photo as the table (once).
    assert ('setParts(mine && keepTable && !tables.length && pending.back ? [[pending.back, pending.backSource, "table"]]'
            ' : tables);') in fn
    assert 'const NOT_A_PACK = ["back_is_a_screen", "not_a_food_pack", "screen_unread"];' in app
    assert "pending.back = null;" in fn and "pending.acceptUnconfirmed = false;" in fn
    # The front stays, except after two packs (D-108) or for another scan's photos.
    assert 'if (!mine || code === "product_mismatch") { pending.front = null; pending.pairing = false; }' in fn
    # Every retake of the list uses it: the refusal (and D-118's clearer photo), both partial reads
    # and D-188's amber allergen card.
    assert app.count("() => retakeList(h, ") == 4
    assert 'retakeList(h, s.problem?.code || s.headline?.source?.ref, s.keep_table)' in app
    # D-194: a partial read's retake on a result and a kind's goes through listChoices(), whose
    # default code is "partial"; D-188's allergen card keeps its own for older results.
    assert app.count('retakeList(h, "partial")') == 1
    assert app.count("listChoices(s, h)") == 2 and 'function listChoices(s, h, code = "partial", keepTable = false)' in app
    assert "pending.parts = []; pending.partSources = []; pending.partKinds = [];" not in app
    # A new first photo keeps a kept table, and a list part goes before it: the table is the last part.
    add = app[app.index("function addShot("):app.index("// D-173 (Sushil")]
    assert "setParts(tables);" in add and 'setParts([...list.slice(0, n - 2), [b, source, "list"], ...tables]);' in add
    # With a kept table: no table question, "Check this pack", and the table can still be retaken.
    review = app[app.index("function shotReview("):app.index("function frontShot(")]
    assert 'const kept = tableIn && pending.lastKind === "list";' in review
    assert 'kept && button("Retake the table too", dropTable, "link")' in review
    assert '(ask || (kept && n < MAX_PHOTOS) || (listOnly && n < MAX_PHOTOS))\n        && button("The list goes on: add the next part"' in review


# ---------------------------------------------------------------- D-177: the result screen
def _fn(app, name):
    f = app[app.index(f"function {name}("):]
    return f[:f.index("\n}\n")]


def test_a_food_result_has_three_tabs_under_the_people():
    app = JS["app.js"]
    body = _fn(app, "result")
    assert body.index('class: "deep opener result-top"') < body.index("put(tabBar(h, tabs, panels))")
    assert '[["you", "For you"], ["inside", "What\'s inside"], ["pack", "On the pack"]]' in body
    assert "moreAbout(h, !askTable, false)" in body and "onThePack(h)" in body
    bar = _fn(app, "tabBar")
    assert 'role: "tablist"' in bar and '"aria-selected"' in bar and "ArrowRight" in bar
    assert "p.hidden = k !== key" in bar


def test_the_pack_photo_stays_on_the_phone():
    lib = JS["lib.js"]
    keep = lib[lib.index("const PHOTO_KEEP"):]
    keep = keep[:keep.index("\n}\n", keep.index("export function savePackPhoto(")) + 3]
    assert "PHOTO_KEEP" in keep and "fetch(" not in keep and "Request(" not in keep
    head = _fn(JS["app.js"], "packHead")
    assert 'el("h1", { class: "product" }' in head and "shareResult(h)" in head


def test_share_sends_the_servers_words_without_a_nickname():
    share = _fn(JS["app.js"], "shareResult")
    assert "fill(p.share || p.line))" in share          # no ref: "your child", never the nickname (D-074)
    assert "cardPeople(s)" in share                     # D-188: nothing for a person with no match
    assert "s.headline?.text" in share and "score" not in share


def test_nutrition_bars_come_from_the_servers_numbers():
    from insidelabel.lenses import screen
    panel = {"basis": "per 100 g", "form": "solid", "values": {
        "added_sugars": {"value": 24.0, "unit": "g", "printed": "24 g", "bound": None},
        "sodium": {"value": 310.0, "unit": "mg", "printed": "310 mg", "bound": "lt"}}}
    rows = {r["key"]: r for r in screen._nutrition_rows(panel)[0]}
    assert rows["added_sugars"]["bar"]["value"] == 24.0 and rows["added_sugars"]["bar"]["unit"] == "g"
    assert rows["salt"]["bar"] is None                  # a printed "less than": no bar
    nb = _fn(JS["app.js"], "nutBar")
    assert '"aria-hidden": "true"' in nb and "nb-${r.tone}" in nb and "score" not in nb
    css = open(os.path.join(WEB_DIR, "app.css"), encoding="utf-8").read()
    assert "scaleX(var(--to, 0))" in css                # transform only


# D-178: home, Your scans, Household and Compare as cards.
def test_scan_cards_show_the_phones_photo_and_the_servers_words():
    app_js = JS["app.js"]
    cards = _fn(app_js, "scanList")
    assert "packThumb(h)" in cards and "cardChips(h.screen.summary).map(toneChip)" in cards
    assert "peopleSummary(h.screen)" in cards and "score" not in cards
    # D-185: at most two chips on a card, those worth a look first, in the server's order (D-123).
    chips = _fn(app_js, "cardChips")
    assert ".slice(0, 2)" in chips and 'r.tone === "worth"' in chips and "sort(" not in chips
    thumb = _fn(app_js, "packThumb")
    assert "h?.photo" in thumb and "fetch(" not in thumb      # the photo never leaves the phone (D-074)


def test_checking_for_and_household_keep_nicknames_on_the_phone():
    app_js = JS["app.js"]
    for name in ("checkingFor", "household", "avatar", "avoidNames"):
        fn = _fn(app_js, name)
        assert "Request(" not in fn and "fetch(" not in fn
    assert 'store.get("allergens"' in _fn(app_js, "avoidNames")
    assert "checkingFor()," in _fn(app_js, "home")


def test_checking_for_shows_a_count_and_opens_the_list_on_a_tap():
    """D-178 follow-up (Sushil, 2026-10-08): "Don't show directly all avoid list, keep one click option
    to see". One line per person with a count; the list sits inside a closed <details>."""
    fn = _fn(JS["app.js"], "checkingFor")
    assert "to avoid" in fn and "no avoid list" in fn and "p.avoid.length" in fn
    summary = fn[fn.index('el("summary"'):fn.index('el("p", { class: "who-avoid')]
    assert "avoidNames(" not in summary                                   # the line shows a count only
    assert 'el("details", { class: "who" }' in fn and "open:" not in fn   # closed by default
    assert "avoidNames(p.avoid)" in fn[fn.index('class: "who-avoid'):]    # the list, once opened
    css = open(os.path.join(WEB_DIR, "app.css"), encoding="utf-8").read()
    rule = css[css.index(".who-name {"):].split("}", 1)[0]
    assert "white-space: nowrap" in rule and "flex-shrink: 0" in rule     # the name never wraps a letter a line
    assert "overflow-wrap: anywhere" not in css[css.index(".checking .who-chips"):css.index(".who-avoid")]


def test_compare_lays_the_packs_side_by_side_with_compare_py_words():
    fn = _fn(JS["app.js"], "compareResult")
    assert 'class: "compare-grid"' in fn and "p.facts" in fn and "score" not in fn


def test_the_pack_picture_and_the_example_photos():                  # D-183
    app, css = JS["app.js"], open(os.path.join(WEB_DIR, "app.css"), encoding="utf-8").read()
    # The pack picture only stands in for the shopper's own photo; its words are the server's.
    assert "return h?.photo ? null : h?.screen?.pack_picture || null;" in app
    assert "const src = h.photo || packPicture(h)?.url || null;" in app
    assert 'el("img", { src: pic.url, alt: pic.alt })' in app and "pic.caption &&" in app
    assert "const src = h?.photo || packPicture(h)?.url;" in app             # Your scans' thumbnail
    # Example photos (Sushil, 2026-10-08): on "Before you start" in the server's words, and on
    # each camera step. A suggestion: nothing checks a photo against them.
    assert "t.examples && el(\"section\", { class: \"examples\" }," in app
    assert 'exampleShot(o.front ? "front" : o.table ? "table" : "list", "Like this: flat, sharp, the whole panel")' in app
    assert ".example-row { display: grid; grid-template-columns: repeat(3, 1fr);" in css



# ---------------------------------------------------------------- D-188: allergen lines when they matter
def test_the_top_shows_only_a_match_or_a_line_we_cant_confirm():
    app = JS["app.js"]
    body = _fn(app, "result")
    assert "cardPeople(s).map(p => personCard(p, h))" in body and "s.people.map" not in body
    pick = _fn(app, "cardPeople")
    # A result kept on the phone from before web-66 still lists everyone; its "not listed" lines stay hidden.
    assert "CARD.includes(p.status)" in pick
    assert re.search(r'const LISTED = \["contains", "may_contain", "uncertain"\]', app)
    assert 'const CARD = [...LISTED, "cannot_confirm", "worth_knowing"];' in app      # an age line is a card
    card = _fn(app, "personCard")
    # Retake on an amber card from a photo scan only; a barcode-only hit took no photo (D-170, D-173).
    assert 'p.status === "cannot_confirm" && h.screen?.state === "result" && !h.looked_up' in card
    assert 'retakeList(h, "partial")' in card
    # A second match stays in view, not under "More".
    assert 'class: "plain also"' in card and "LISTED.includes(a.state)" in card


def test_for_you_has_the_servers_reminder_and_age_lines_only():
    app = JS["app.js"]
    lines = _fn(app, "forYouLines")
    assert "s.for_you" in lines and "s.for_you_note" in lines and "fill(t, r.ref)" in lines
    assert "Not listed" not in app and "not listed" not in lines            # D-188: worded on the server only
    body = _fn(app, "result")
    assert "you(forYouLines(s))" in body and "put(kindView(s), forYouLines(s))" in body


def test_a_scan_card_names_a_match_and_never_a_no_match():
    app = JS["app.js"]
    cards = _fn(app, "scanList")
    assert "scanPerson(h.screen)" in cards
    person = _fn(app, "scanPerson")
    assert 'cardPeople(screen).find(x => x.status !== "worth_knowing")' in person
    assert "PERSON_TONE[p.status]" in person
    assert "cardPeople(screen)[0]" in _fn(app, "peopleSummary")


def test_the_table_question_has_two_equal_answers():                       # D-199
    """Sushil, 2026-10-11: "sometimes during scan of ingredients it skips step3 nutrition table".
    The big green Yes was tapped without reading; now neither answer is the highlighted default."""
    app = JS["app.js"]
    review = app[app.index("function shotReview("):app.index("function frontShot(")]
    # The question: both answers, same class, Yes first, both in the dock, neither primary.
    assert 'const check = ask ? button("Yes, it\'s in this photo", yes, "table-answer")' in review
    assert 'ask && button("No, photograph the table", () => show(tableShot()), "table-answer")' in review
    dock = review[review.rindex('el("div", { class: "dock" }'):]
    assert dock.index("    check,\n") < dock.index('"No, photograph the table"')
    assert review.count('"table-answer"') == 2
    assert '"Yes, now the front of the pack"' not in app and '"Yes, check this pack"' not in app
    # Yes does what the big button did: the front step while it is needed, else send.
    assert "const yes = frontNeeded() && !pending.front ? () => show(frontShot()) : () => sendPhotos();" in review
    # No question (listOnly, frontIn, every photo taken): the one primary check, words unchanged.
    assert "const ask = !tableIn && n < MAX_PHOTOS && !listOnly && !frontIn;" in review
    assert ': frontNeeded() && !pending.front ? button("Next: the front of the pack", yes, "primary")' in review
    assert ': button("Check this pack", yes, "primary");' in review


def test_the_table_card_is_first_in_for_you():                              # D-199
    """D-133's card was last in For you, below the first screen; it now follows the per-person lines."""
    body = JS["app.js"][JS["app.js"].index("function result("):JS["app.js"].index("function packHead(")]
    you = body.index("you(forYouLines(s));")
    card = body.index("if (askTable) you(")
    assert you < card < body.index("if (serious.length) you(")
    assert card < body.index("if (s.retake) you(partialRetake(")
    assert body.count("if (askTable) you(") == 1


def test_the_scanner_takes_a_read_with_a_right_check_digit_at_once(tmp_path):    # 2026-10-14
    # Sushil, comparing another app's scanner: "its really fast". One read is enough when its GS1 check
    # digit is right (the same rule as barcode.check_digit_ok); a failing read still needs a second one.
    import shutil
    import subprocess
    import pytest
    from insidelabel.barcode import check_digit_ok
    cam = JS["camera.js"]
    assert "if (checkDigitOk(code) || seen.has(raw)) return found(code);" in cam
    assert "video.requestVideoFrameCallback(tick)" in cam and "setTimeout(tick, TICK_MS)" in cam
    node = shutil.which("node")
    if not node:
        pytest.skip("node isn't installed")
    codes = ["8901262080033", "8901030980046", "8904335601951", "036000291452", "96385074",
             "8901262080034", "890126208003", "036000291453", "96385075", "123", ""]
    (tmp_path / "camera.mjs").write_text(cam, encoding="utf-8")
    run = (f"import('{(tmp_path / 'camera.mjs').as_uri()}').then(m => "
           f"console.log(JSON.stringify({codes!r}.map(m.checkDigitOk))))")
    r = subprocess.run([node, "-e", run], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    assert json.loads(r.stdout) == [len(c) in (8, 12, 13) and check_digit_ok(c) for c in codes]


def test_result_compare_button_counts_saved_packs_of_its_own_kind():      # 2026-10-14, D-201 follow-up
    # Sushil, 2026-10-14: "Compare (3)" beside the bar's 2, on an infant pack with foods saved.
    body = _fn(JS["app.js"], "resultNext")
    assert "Compare (${" not in body and "others + 1" not in body
    assert "kindOf(x) === kindOf(h.id)" in body
    assert 'button(`Compare with ${same.length} saved pack${same.length > 1 ? "s" : ""}`' in body
    assert 'store.set("compare", [...same, h.id].slice(-4));' in body


def test_the_scanner_reads_the_box_inside_the_corners_at_full_resolution():    # 2026-10-14
    # Sushil, on an Amulspray tin it didn't read: "check how poor our scan is". The barcode was about one
    # pixel per bar in a 1280 px frame of the whole room.
    cam, app = JS["camera.js"], JS["app.js"]
    assert "const SCAN_WIDTH = 1920;" in cam and "openCamera(video, SCAN_WIDTH, true)" in cam
    assert "const crop = looks++ % 2 ? guideCrop(video, canvas) : null;" in cam
    assert "await detector.detect(crop || video)" in cam
    assert ".frame { position: absolute; inset: 30% 12%;" in CSS      # GUIDE is a little wider than this
    assert "the camera zooms in by itself" in app and "hand's width" not in app
    assert "`App version: ${APP_VERSION}`" in app


def test_the_scanner_zooms_by_itself_until_a_read():                          # 2026-10-14
    # Sushil, on the other app: "then it auto zooms". 2x, 3x, 4x and round, as far as the camera offers.
    cam, app = JS["camera.js"], JS["app.js"]
    assert "const ZOOM_STEPS = [2, 3, 4];" in cam and "const ZOOM_EVERY_MS = 1200;" in cam
    assert "[...new Set(ZOOM_STEPS.map(z => Math.min(z, max)))].filter(z => z >= 1.5)" in cam
    assert "clearInterval(zoomer);" in cam                     # stops with the camera
    assert 'el("span", { class: "cam-zoom", "aria-hidden": "true" }, `${stop.zoom}x`)' in app
    assert ".cam-zoom {" in CSS


def test_the_scanner_falls_back_to_full_resolution_stills():                   # 2026-10-14
    # Sushil: Chrome on his phone offers no zoom and a soft live picture, while "both upload and photo works".
    cam, app = JS["camera.js"], JS["app.js"]
    assert "const STILL_AFTER_MS = 3000;" in cam and "const STILL_EVERY_MS = 2000;" in cam
    assert 'if (pc?.fillLightMode?.includes("off")) settings.fillLightMode = "off";' in cam   # never the flash
    assert "await detector.detect(await createImageBitmap(blob))" in cam
    assert "sent < STILL_SERVER_MAX" in cam and "const STILL_SERVER_MAX = 8;" in cam      # the /check-photo limit
    assert "clearTimeout(stills);" in cam                                             # stops with the camera
    assert 'checkPhotoRequest("barcode", blob)' in app
    assert 'startScanner(video, code => lookUp(code, "camera"), onStill)' in app
