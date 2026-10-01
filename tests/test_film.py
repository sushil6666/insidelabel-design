"""
The explainer film on the two homes (Sushil, 2026-10-01: "website home page and android
apps home page"). The film itself is built in videos/insidelabel-how-it-reads/.

What must hold, checked statically and through the API:
- Nothing loads until someone looks: preload="none" everywhere, never in the service
  worker's precache, and the worker leaves the mp4 alone (it is fetched in ranges).
- The app never plays it on its own; the Scan button stays the first thing on home.
- The website plays it muted only once it is in view, and never with reduced motion.
- The files are the size the brief set (2 to 4 MB) and are served in ranges, which
  phones need to play a video.
"""
import json
import os
import re

from fastapi.testclient import TestClient

from insidelabel.api.main import WEB_DIR, app

c = TestClient(app)
MEDIA = os.path.join(WEB_DIR, "film")
CUTS = ("insidelabel-16x9", "insidelabel-9x16")
SW = open(os.path.join(WEB_DIR, "sw.js"), encoding="utf-8").read()
APP = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
SITE = open(os.path.join(WEB_DIR, "site", "index.html"), encoding="utf-8").read()


def test_each_cut_has_a_film_of_2_to_4_mb_and_a_poster():
    for cut in CUTS:
        size = os.path.getsize(os.path.join(MEDIA, cut + ".mp4"))
        assert 2_000_000 <= size <= 4_000_000, (cut, size)
        poster = os.path.getsize(os.path.join(MEDIA, cut + ".webp"))
        assert poster < 120_000, (cut, poster)


def test_the_film_is_served_in_ranges_as_mp4():
    for cut in CUTS:
        r = c.get(f"/app/film/{cut}.mp4", headers={"Range": "bytes=0-1023"})
        assert r.status_code == 206 and len(r.content) == 1024, cut
        assert r.headers["content-type"] == "video/mp4"
        assert r.headers["accept-ranges"] == "bytes"
        assert "image/webp" in c.get(f"/app/film/{cut}.webp").headers["content-type"]


def test_the_service_worker_never_precaches_or_caches_the_film():
    shell = json.loads("[" + re.search(r"SHELL = \[(.*?)\];", SW, re.S).group(1) + "]")
    assert not any("film/" in f for f in shell)
    skip = SW.index('if (url.pathname.endsWith(".mp4")) return;')
    assert skip < SW.index("e.respondWith(")


def test_the_app_plays_the_film_only_on_a_tap():
    assert "autoplay" not in APP
    assert 'preload: "none"' in APP
    home = APP[APP.index("async function home()"):APP.index("// D-130: packs planned")]
    assert home.index('class: "scan-cta"') < home.index("filmCard()")    # Scan stays first
    play = APP[APP.index("function playFilm("):]
    play = play[:play.index("\n}\n")]
    assert "prefers-reduced-motion: reduce" in play and "if (!still) video.play()" in play
    assert '"aria-label": "Close the film"' in play and "popstate" in play
    # this file's own history() is the scan list: the browser's must be named in full
    assert "window.history.pushState" in play and "window.history.back()" in play
    assert not re.search(r"(?<![.\w])history\.(pushState|back)", play)


def test_the_website_film_loads_only_in_view_muted_and_not_with_reduced_motion():
    video = re.search(r"<video\b[^>]*>", SITE).group(0)
    for attr in ('preload="none"', "muted", "playsinline", "controls", 'poster="/app/film/insidelabel-16x9.webp"'):
        assert attr in video, attr
    assert "autoplay" not in SITE
    assert '<source src="/app/film/insidelabel-16x9.mp4" type="video/mp4">' in SITE
    script = SITE[SITE.index("<script>"):]
    assert "prefers-reduced-motion: reduce" in script and "saveData" in script
    assert "IntersectionObserver" in script
    # near the top: before the first section heading
    assert SITE.index("<video") < SITE.index("<h2>How it works</h2>")
