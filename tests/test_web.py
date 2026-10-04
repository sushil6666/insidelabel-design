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


def test_invite_and_feedback_errors_pass_the_wording_lint():
    from insidelabel.api import main
    assert_clean([t for _s, t in main._JOIN_ERRORS.values()], "join errors")


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


def test_photo_ask_names_the_panel_the_count_and_why():                # D-153
    """A tester didn't know which panel "the back" was, how many photos, or why."""
    app = JS["app.js"]
    assert "Photograph the back" not in app
    # Sushil, 2026-10-03: for food, the ingredients and the nutrition table everywhere (D-133).
    assert 'el("h1", {}, "Photograph the ingredients and the nutrition table")' in app
    assert '"New pack · 1 or 2 photos"' in app and "We haven't checked this barcode yet" in app
    assert '"Photograph these"' in app and '"NUTRITION"' in app     # the drawing marks both blocks
    assert app.count('"Not needed"') == 1                           # only the licence
    assert "Optional: the front of the pack" in app                 # D-100's front stays optional


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
    assert 't.kind === "not_permitted"' in body and 'class: "worth"' in body
    # The result ends on the next pack (D-057), and says what isn't built yet.
    assert "Holding another pack? Scan it to compare" in body
    assert body.count('class: "pending"') == 2


def test_report_faces_are_cached_on_use_not_at_install():              # D-153
    """Precached at install, the three report faces delayed the first screen's own fonts and its
    footer moved (Lighthouse CLS 0 to 0.16, measured 2026-10-02). The fetch handler caches them
    the first time a screen uses them."""
    sw = open(os.path.join(WEB_DIR, "sw.js"), encoding="utf-8").read()
    shell = sw[sw.index("const SHELL"):sw.index("];", sw.index("const SHELL"))]
    for f in ("source-serif-4", "ibm-plex-mono"):
        assert f not in shell
    assert "caches.open(VERSION).then(c => c.put(e.request, copy))" in sw


def test_the_footer_waits_for_a_loading_screen():                      # D-153 step 2, fixed 2026-10-03
    """On a first visit the footer showed under "Loading…" and jumped when "Before you start" arrived
    (Lighthouse CLS 0.16 in about half of fresh loads). A busy screen reveals it only once filled."""
    app = JS["app.js"]
    show = app[app.index("function show(node)"):app.index("function settled(")]
    assert 'getAttribute("aria-busy") === "true"' in show and "settled()" in show
    assert 'document.body.classList.add("ready")' not in show
    agree = app[app.index("function agree()"):app.index("function join(")]
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

