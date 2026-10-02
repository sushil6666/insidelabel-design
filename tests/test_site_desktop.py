"""
site-desktop (Sushil, 2026-10-02): the centred italic wordmark on every page and screen, the
profile menu in the app, the "Scan here" bar, and the website's desktop layout.

Static checks on web/, like tests/test_web.py:
- One wordmark, made by tools/make_wordmark.py and carried, identical, by every page.
- The app header: the wordmark, a back button only where a screen had one, and the profile icon
  (a drawing, never a name: D-074) that opens a menu holding every header and footer link.
- The home: "Scan here" first, nothing above it but the header.
- The website: the desktop layout is scoped to desktops (phones unchanged).
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
WORDMARK = re.compile(r"<!--wordmark-->(.*?)<!--/wordmark-->", re.S)


def test_every_page_and_the_app_carry_the_same_wordmark():
    copies = [WORDMARK.findall(APP_HTML)] + [WORDMARK.findall(h) for h in SITE.values()]
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


def test_the_menu_holds_every_header_and_footer_link():
    menu = re.search(r'<dialog id="menu".*?</dialog>', APP_HTML, re.S).group(0)
    footer = re.search(r"<footer.*?</footer>", APP_HTML, re.S).group(0)
    links = dict(re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', menu))
    assert links.get("#/household") == "Household" and links.get("#/compare") == "Compare"
    for href in re.findall(r'href="([^"]+)"', footer):
        assert href in links, href
    assert 'id="nav-compare"' in menu                                      # the count still updates


def test_the_menu_closes_every_way_and_gives_focus_back():
    fn = APP_JS[APP_JS.index("function setupMenu("):]
    fn = fn[:fn.index("\n}\n")]
    assert "menu.showModal()" in fn and "btn.focus()" in fn
    assert '"cancel"' in fn                                                 # Escape
    assert "e.target === menu" in fn                                        # a tap outside
    assert '"popstate"' in fn and "window.history.pushState" in fn         # the phone's Back
    assert not re.search(r"(?<![.\w])history\.(pushState|back)", fn)       # this file's history() is the scans


def test_the_back_button_moved_into_the_header_only_where_it_was():
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
