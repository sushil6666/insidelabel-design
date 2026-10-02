"""D-153 step 3: the website home as the redesign "Merged".

Static checks on web/site/index.html, like tests/test_site_desktop.py. The film's own rules
(D-151) stay in tests/test_film.py and the desktop container (D-152) in test_site_desktop.py;
these cover what the redesign adds, and tie the page's claims to where they come from, so a
number or a note on the home can't drift from the data or from /about.
"""
import html
import json
import os
import re

from insidelabel.api.main import WEB_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = open(os.path.join(WEB_DIR, "site", "index.html"), encoding="utf-8").read()
ABOUT = open(os.path.join(WEB_DIR, "site", "about.html"), encoding="utf-8").read()


def text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def sections():
    main = HOME[HOME.index("<main>"):HOME.index("</main>")]
    return re.findall(r"<section([^>]*)>(.*?)</section>", main, re.S)


def test_the_sections_come_in_the_accepted_order():
    heads = [text(re.search(r"<h[12][^>]*>(.*?)</h[12]>", body, re.S).group(1)) for _attrs, body in sections()]
    assert heads == ["Read the label for your kids.", "How it works", "One real pack, every line sourced",
                     "How we check", "In preparation", "Why I built InsideLabel", "Try it on your next shop."]
    assert 'class="hero deep band"' in sections()[0][0] and "deep band" in sections()[-1][0]


def test_the_hero_cards_quote_the_example_with_its_source_numbers():
    cards = re.search(r'<ul class="hero-cards".*?</ul>', HOME, re.S).group(0)
    table = re.search(r'<table class="sourced">.*?</table>', HOME, re.S).group(0)
    for n in re.findall(r"\[(\d)\]", cards):
        assert f"[{n}]" in table, n
    assert "brand hidden" in text(HOME) and "not a review of a company" in text(HOME)   # D-042: never the brand


def test_the_additive_count_on_the_page_is_the_data():
    rows = json.load(open(os.path.join(ROOT, "data", "additives.json"), encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("additives", rows)
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    n = sum(1 for r in rows if r.get("fssai_basis"))
    assert f"{n} additives, each with its FSSAI Appendix A entry" in HOME, n


def test_the_founder_note_is_the_same_on_the_home_and_about():
    note = lambda page: [text(p) for p in re.findall(r"<p>(.*?)</p>",
                         re.search(r'<div class="founder-text[^"]*">(.*?)</div>', page, re.S).group(1), re.S)]
    assert note(HOME) == note(ABOUT) and len(note(HOME)) == 3


def test_what_is_promised_says_it_is_not_built_yet():
    pending = re.findall(r'<div class="pending">(.*?)</div>', HOME, re.S)
    assert len(pending) == 2
    assert "not yet available" in pending[0] and "Ask about this pack" in pending[0]          # D-113, Pro
    assert "Free" in pending[1]                                                               # D-059


def test_below_the_first_screen_waits_until_it_is_near():
    """Measured 2026-10-02: laying out the whole page before the first paint cost a slow phone's CPU."""
    assert ".home main > section:not(.hero):not(.band-end) { content-visibility: auto;" in HOME
    assert "contain-intrinsic-size: auto" in HOME
