"""
The explainer film is on the website home only, as the hero (D-151, Sushil 2026-10-01: "not liked
it, keep only web page website on desktop and mobile version video"). The app has no film.
The film itself is built in videos/insidelabel-how-it-reads/.

What must hold, checked statically and through the API:
- The app serves no film: no card, no player, nothing in its shell.
- The website picks ONE cut per screen (9:16 on phones and portrait screens, 16:9 otherwise),
  by the same rule for the still (<picture>), the CSS and the script, and sets the film's src
  only after the page has loaded; never by itself with reduced motion, Save-Data or without
  IntersectionObserver; a visible, labelled play/pause button (WCAG 2.2.2).
- Each hero file is under 1.6 MB with no audio track (the words are on screen), and the
  posters exist. They are served in ranges, which phones need to play a video.
- The service worker never caches an .mp4.
"""
import json
import os
import re
import struct

from fastapi.testclient import TestClient

from insidelabel.api.main import WEB_DIR, app

c = TestClient(app)
FILM = os.path.join(WEB_DIR, "film")
CUTS = ("hero-16x9", "hero-9x16")
RULE = "(max-width: 767px), (orientation: portrait)"
SW = open(os.path.join(WEB_DIR, "sw.js"), encoding="utf-8").read()
APP = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(WEB_DIR, "app.css"), encoding="utf-8").read()
SITE = open(os.path.join(WEB_DIR, "site", "index.html"), encoding="utf-8").read()
SITE_CSS = open(os.path.join(WEB_DIR, "site", "site.css"), encoding="utf-8").read()


def track_handlers(path):
    """The handler type of every track in an MP4 ('vide', 'soun', ...), read from its boxes."""
    data = open(path, "rb").read()
    found, i = [], 0
    while True:
        i = data.find(b"hdlr", i)
        if i < 0:
            return found
        found.append(data[i + 12:i + 16].decode("latin-1"))      # size, 'hdlr', version+flags, pre_defined
        i += 4


def test_the_app_serves_no_film():
    for word in ("filmCard", "playFilm", "film/", ".mp4", "How it works"):
        assert word not in APP, word
    assert "film" not in CSS
    shell = json.loads("[" + re.search(r"SHELL = \[(.*?)\];", SW, re.S).group(1) + "]")
    assert not any("film" in f or f.endswith(".mp4") for f in shell)


def test_each_hero_film_is_under_1_6_mb_with_no_audio_and_has_a_poster():
    for cut in CUTS:
        path = os.path.join(FILM, cut + ".mp4")
        assert os.path.getsize(path) < 1_600_000, (cut, os.path.getsize(path))
        assert track_handlers(path).count("vide") == 1 and "soun" not in track_handlers(path), cut
        assert os.path.getsize(os.path.join(FILM, cut + ".webp")) < 120_000, cut
    # nothing else lingers in web/film: what isn't served is deleted
    assert sorted(os.listdir(FILM)) == sorted(f"{c}.{e}" for c in CUTS for e in ("mp4", "webp"))


def test_the_hero_film_is_served_in_ranges():
    for cut in CUTS:
        r = c.get(f"/app/film/{cut}.mp4", headers={"Range": "bytes=0-1023"})
        assert r.status_code == 206 and len(r.content) == 1024, cut
        assert r.headers["content-type"] == "video/mp4" and r.headers["accept-ranges"] == "bytes"
        assert "image/webp" in c.get(f"/app/film/{cut}.webp").headers["content-type"]


def test_the_service_worker_never_caches_an_mp4():
    assert SW.index('if (url.pathname.endsWith(".mp4")) return;') < SW.index("e.respondWith(")


def test_the_website_chooses_one_cut_per_screen_by_one_rule():
    video = re.search(r"<video\b[^>]*>", SITE).group(0)
    for attr in ("muted", "autoplay", "loop", "playsinline", 'preload="none"'):
        assert attr in video, attr
    assert "src=" not in video and "<source" not in SITE[SITE.index("<video"):SITE.index("</video>")]
    # the still: <picture> with the same rule, sized so nothing shifts
    assert f'<source media="{RULE}" srcset="/app/film/hero-9x16.webp" width="720" height="1280">' in SITE
    assert '<img src="/app/film/hero-16x9.webp" width="1280" height="720"' in SITE
    # the CSS: the same rule turns the box 9:16
    assert f"@media {RULE} {{" in SITE_CSS and "aspect-ratio: 9 / 16" in SITE_CSS
    script = SITE[SITE.index("<script>"):]
    assert f'matchMedia("{RULE}")' in script
    assert '"/app/film/hero-" + (tall ? "9x16" : "16x9") + ".mp4"' in script
    assert script.count("film.src =") == 1                       # one file, set in one place


def test_the_website_film_starts_only_after_load_in_view_and_never_with_reduced_motion():
    script = SITE[SITE.index("<script>"):]
    assert 'addEventListener("load", start)' in script and "IntersectionObserver" in script
    assert "prefers-reduced-motion: reduce" in script and "saveData" in script
    assert 'film.removeAttribute("autoplay")' in script
    assert "film.pause()" in script and "held = 1" in script      # out of view, and the visitor's pause


def test_the_hero_has_a_labelled_pause_button_and_keeps_its_words_first():
    button = re.search(r'<button class="film-toggle"[^>]*>', SITE).group(0)
    assert 'type="button"' in button and 'aria-label="Play the film"' in button
    assert '"Pause the film"' in SITE[SITE.index("<script>"):]
    hero = SITE[SITE.index('<section class="hero'):SITE.index("</section>")]
    assert hero.index("<h1>") < hero.index('class="cta"') < hero.index("<video")   # words, then the film
