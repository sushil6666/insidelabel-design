"""
site-desktop (Sushil, 2026-10-02): the centred italic wordmark on every page and screen, the
profile menu in the app, the "Scan here" bar, and the website's desktop layout.

Static checks on web/, like tests/test_web.py:
- One wordmark, made by tools/make_wordmark.py and carried, identical, by every page.
- The app header: the wordmark, a back button only where a screen had one, and the profile icon
  (a drawing, never a name: D-074) that opens a menu holding every header and footer link.
- The home: "Scan here" first, nothing above it but the header.
- The website: the desktop layout is scoped to desktops (phones unchanged).
- D-161: the reviewer screen's header (review/templates/base.html) carries the same wordmark,
  then "review", left-aligned in its work-tool header; GET /review shows it.
"""
import os
import re

from insidelabel.api.main import WEB_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
read = lambda *p: open(os.path.join(*p), encoding="utf-8").read()
APP_HTML = read(WEB_DIR, "index.html")
APP_JS = read(WEB_DIR, "app.js")
APP_CSS = read(WEB_DIR, "app.css")
SITE = {n: read(WEB_DIR, "site", f"{n}.html") for n in ("index", "privacy", "about", "how")}
SITE_CSS = read(WEB_DIR, "site", "site.css")
REVIEW_BASE = read(ROOT, "src", "insidelabel", "review", "templates", "base.html")
WORDMARK = re.compile(r"<!--wordmark-->(.*?)<!--/wordmark-->", re.S)


def test_every_page_and_the_app_carry_the_same_wordmark():
    copies = ([WORDMARK.findall(APP_HTML)] + [WORDMARK.findall(h) for h in SITE.values()]
              + [WORDMARK.findall(REVIEW_BASE)])                 # D-161
    assert all(len(c) == 1 for c in copies), [len(c) for c in copies]
    assert len({c[0] for c in copies}) == 1                  # one definition, the same everywhere
    svg = copies[0][0]
    assert 'role="img"' in svg and 'aria-label="InsideLabel"' in svg
    assert "prefers-color-scheme:dark" in svg                 # light and dark ink
    for html in [APP_HTML, *SITE.values()]:
        header = re.search(r"<header.*?</header>", html, re.S).group(0)
        assert 'class="wordmark"' in header and "<!--wordmark-->" in header
        assert 'class="brand"' not in html


def test_the_wordmark_font_is_the_open_licence_italic_it_was_drawn_from():
    tool = read(ROOT, "tools", "make_wordmark.py")
    assert "dm-sans-latin-800-italic.woff2" in tool
    assert os.path.exists(os.path.join(ROOT, "tools", "wordmark", "dm-sans-latin-800-italic.woff2"))
    assert "Open Font License" in read(ROOT, "tools", "wordmark", "OFL-dm-sans.txt")


def test_the_app_header_has_a_profile_icon_that_opens_the_menu():
    header = re.search(r'<header class="top">.*?</header>', APP_HTML, re.S).group(0)
    btn = re.search(r'<button[^>]*id="menu-btn"[^>]*>(.*?)</button>', header, re.S)
    assert 'aria-label="Menu"' in btn.group(0) and 'aria-controls="menu"' in btn.group(0)
    assert re.sub(r"<[^>]+>", "", btn.group(1)).strip() == ""           # a drawing: no name, no initials
    assert "width: var(--tap); height: var(--tap)" in APP_CSS              # 48 x 48
    assert '<nav>' not in header and "Compare" not in header               # the pills moved to the menu


def test_the_menu_and_the_bottom_bar_hold_every_link():                 # D-176
    menu = re.search(r'<dialog id="menu".*?</dialog>', APP_HTML, re.S).group(0)
    footer = re.search(r"<footer.*?</footer>", APP_HTML, re.S).group(0)
    bar = re.search(r'<nav class="tabbar".*?</nav>', APP_HTML, re.S).group(0)
    links = dict(re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', menu))
    for href in re.findall(r'href="([^"]+)"', footer):
        assert href in links, href
    for href in ("#/", "#/scans", "#/compare", "#/household"):
        assert f'href="{href}"' in bar, href
    assert "#/household" not in menu and "#/compare" not in menu          # moved to the bar
    assert 'id="nav-compare"' in bar and 'id="tab-scan"' in bar             # the count, the Scan button


def test_the_menu_closes_every_way_and_gives_focus_back():
    fn = APP_JS[APP_JS.index("function setupMenu("):]
    fn = fn[:fn.index("\n}\n")]
    assert "menu.showModal()" in fn and "btn.focus()" in fn
    assert '"cancel"' in fn                                                 # Escape
    assert "e.target === menu" in fn                                        # a tap outside
    assert '"popstate"' in fn and "window.history.pushState" in fn         # the phone's Back
    assert not re.search(r"(?<![.\w])history\.(pushState|back)", fn)       # this file's history() is the scans


def test_a_tile_page_still_goes_back_to_its_result():
    assert APP_JS.count('"data-back"') == 1                                 # a result's own page (D-134)
    look = APP_JS[APP_JS.index("function lookView("):]
    assert '"data-back-label": "Back to the result"' in look[:look.index("\n}\n")]
    assert 'class: "back"' not in APP_JS


def test_home_starts_with_scan_here_and_nothing_above_it():
    home = APP_JS[APP_JS.index("async function home()"):]
    home = home[:home.index("\n}\n")]
    body = home[home.index('return el("section"'):]
    first = body.index('class: "scan-cta"')
    assert first < body.index("updates,")
    assert body.index('"Scan here"') < body.index("updates,")
    assert 'go("scan")' in body[first:first + 200]                          # opens what "Scan a pack" opened


def test_the_website_desktop_layout_touches_desktops_only():
    style = re.search(r'<style media="\(min-width: 1024px\)">(.*?)</style>', SITE["index"], re.S)
    assert style and ".home .wrap { max-width: 1200px;" in style.group(1)
    assert "max-width: 1280px" in style.group(1)                            # the step at 1440 px
    assert ".home " not in SITE_CSS                                         # nothing in the phones' stylesheet
    assert 'class="home"' in SITE["index"]


# ---------------------------------------------------------------- D-161: the reviewer screen

def test_the_reviewer_header_takes_the_wordmark_then_review():
    header = re.search(r"<header>.*?</header>", REVIEW_BASE, re.S).group(0)
    # Jinja never reads the SVG: the block sits inside {% raw %}, outside the markers.
    assert "{% raw %}<!--wordmark-->" in header and "<!--/wordmark-->{% endraw %}" in header
    assert 'href="/review" aria-label="InsideLabel review"' in header
    assert '<span class="sub">review</span>' in header
    assert 'class="who"' in header                                   # "Signed in as" stays right


def test_get_review_shows_the_wordmark(fresh_db):
    import base64

    import pytest
    from fastapi.testclient import TestClient

    from insidelabel.api import main
    from insidelabel.review import routes
    from insidelabel.review.service import ReviewService

    saved, mp = routes.SERVICE, pytest.MonkeyPatch()
    routes.SERVICE = ReviewService(fresh_db[0], main.ENGINE_VERSION)
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", "wordmark-token")             # signed in, as test_reviewer_logins does
    try:
        cred = base64.b64encode(b"asha:wordmark-token").decode()
        r = TestClient(main.app, headers={"Authorization": f"Basic {cred}"}).get("/review")
    finally:
        mp.undo()
        routes.SERVICE = saved
    assert r.status_code == 200, r.text
    assert WORDMARK.findall(r.text) == WORDMARK.findall(APP_HTML)        # the same copy, rendered
    assert 'aria-label="InsideLabel review"' in r.text and "{% raw %}" not in r.text



# ---------------------------------------------------------------- D-176: the app's frame

def _fn(name):
    f = APP_JS[APP_JS.index(f"function {name}("):]
    return f[:f.index("\n}\n")]


def test_inner_screens_show_their_name_and_a_back_arrow():
    header = re.search(r'<header class="top">.*?</header>', APP_HTML, re.S).group(0)
    assert 'id="top-title"' in header and 'class="wordmark"' in header
    assert ".top.titled .wordmark { display: none; }" in APP_CSS
    frame = _fn("frame")
    assert "FIRST_RUN.includes(name)" in frame                               # the wordmark on first-run screens
    assert 'name === "result"' in frame and 'href: "#/"' in frame           # a result goes home
    assert "window.history.back()" in frame and 'go("")' in frame           # else the phone's Back, or home
    titles = APP_JS[APP_JS.index("const TITLES = {"):APP_JS.index("};", APP_JS.index("const TITLES = {"))]
    assert "home" not in re.findall(r"(\w+):", titles)                       # home keeps the wordmark (D-152)


def test_the_bottom_bar_stays_off_the_camera_and_first_run_screens():
    nobar = APP_JS[APP_JS.index("const NO_TABBAR"):].split("\n")[0]
    for name in ("scan", "photo", "front", "table", "tablephoto"):
        assert f'"{name}"' in nobar, name
    assert "...FIRST_RUN" in nobar
    assert "bar.hidden = NO_TABBAR.includes(name)" in _fn("frame")
    assert 'id="tabbar" aria-label="Main" hidden' in APP_HTML               # hidden until a screen shows it
    assert re.search(r"\.tabbar \{\s*position: fixed;", APP_CSS)             # fixed: no layout shift
    assert "scroll-padding-bottom" in APP_CSS                               # focus never hides under it


def test_the_bottom_bar_scan_button_opens_what_scan_here_opens():
    fn = _fn("setupTabbar")
    assert 'resetPending(); go("scan")' in fn
    assert "setupTabbar();" in APP_JS


def test_your_scans_lists_this_phones_results():
    fn = _fn("scans")
    assert "history()" in fn and "yourScans()" in fn and "scanList(all)" in fn
    assert "scans," in APP_JS[APP_JS.index("const routes = {"):APP_JS.index("};", APP_JS.index("const routes = {"))]


def test_every_site_page_has_the_same_nav_and_footer():                 # D-179
    navs, foots = set(), set()
    for name, html in SITE.items():
        header = re.search(r"<header.*?</header>", html, re.S).group(0)
        assert 'class="site-nav"' in header and 'class="site-menu"' in header and 'href="/app/"' in header
        nav = re.sub(r' aria-current="page"', "", re.search(r'<nav class="site-nav".*?</nav>', header, re.S).group(0))
        navs.add(nav)
        cur = re.findall(r'href="([^"]+)" aria-current="page"', header)
        assert cur == ([] if name == "index" else [f"/{name}"] * 2)      # the page in view, in the bar and the menu
        foot = re.search(r'<footer class="site-foot">.*?</footer>', html, re.S).group(0)
        foots.add(foot)
        assert "none can change what we show" in foot                   # D-138
        assert 'href="/privacy"' in foot and 'href="/about"' in foot and "mailto:connect@insidelabel.ai" in foot
    assert len(navs) == 1 and len(foots) == 1
    assert 'id="how-title"' in SITE["index"]                             # "How it works" lands on its section
    assert "<script" not in re.search(r"<header.*?</header>", SITE["about"], re.S).group(0)   # no JS for the menu
