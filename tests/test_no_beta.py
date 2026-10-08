"""
D-184 (Sushil, 2026-10-08: "remove all beta options anywhere in app and web, we are no
more beta now"): no text a user can see says "beta" or "tester". The invite-only beta
(D-102) is gone with its join screen. "Invite code" and "invite link" stay only where the
privacy page and "Your data" say what is deleted (codes made before D-162, until they expire).

Shown text: the app's own strings (web/*.js, web/index.html), screen.py's word tables, the
website pages and their meta descriptions, the "Before you start" rules, the messages the
server sends (rate limits, photo checks, errors), and the Play listing's copy. "beta-carotene"
is a pigment, not a beta, so the word match leaves it alone.
"""
import glob
import html
import json
import os
import re

from fastapi.testclient import TestClient

from insidelabel import ratelimit
from insidelabel.api import main
from insidelabel.lenses import screen
from test_no_score_words import NOT_SHOWN
from test_web import HTML, JS, js_strings
from test_wording import ROOT, strings

c = TestClient(main.app)
WORD = re.compile(r"\b(beta(?!-)|testers?)\b", re.I)


def assert_no_beta(texts, where):
    bad = [t for t in texts if isinstance(t, str) and WORD.search(t)]
    assert not bad, f"{where}: says beta or tester\n" + "\n".join(f"  {t!r}" for t in bad)


def _page_text(src):
    """The words a reader sees, and the meta description a search result shows."""
    metas = re.findall(r'<meta[^>]+content="([^"]*)"', src)
    body = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", " ", src, flags=re.S)
    return [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split()), *metas]


def test_the_lint_catches_the_word():
    assert WORD.search("InsideLabel, in beta") and WORD.search("testers get it") and WORD.search("Join the Beta")
    assert not WORD.search("Carotenes (beta-carotene)") and not WORD.search("alphabetical")


def test_the_apps_own_strings():
    for name, src in JS.items():
        assert_no_beta(js_strings(src), f"web/{name}")
    assert_no_beta(_page_text(HTML), "web/index.html")
    with open(os.path.join(ROOT, "web", "manifest.webmanifest"), encoding="utf-8") as f:
        assert_no_beta(list(strings(json.load(f))), "web/manifest.webmanifest")


def test_the_screens_word_tables():
    texts = []
    for name, value in vars(screen).items():
        if name.isupper():
            texts += list(strings(value, skip_keys=NOT_SHOWN))
    assert_no_beta(texts, "lenses/screen.py")
    assert screen.PHOTO_LIMIT_TEXT == "Each phone can photograph {limit} packs in any 24 hours."   # D-148 stays


def test_the_website_pages_and_meta_descriptions():
    pages = sorted(glob.glob(os.path.join(ROOT, "web", "site", "*.html")))
    assert len(pages) >= 4
    for p in pages:
        with open(p, encoding="utf-8") as f:
            texts = _page_text(f.read())
        assert_no_beta(texts, os.path.relpath(p, ROOT))
    for path in ("/", "/about", "/how", "/privacy"):
        assert_no_beta([" ".join(c.get(path).text.split())], f"served {path}")


def test_the_before_you_start_rules():
    t = main.TERMS
    shown = [t["title"], t["intro"], t["agree_label"], t["button"], *t["points"],
             *strings(t.get("examples") or {})]
    assert_no_beta(shown, "data/terms.json")


def test_the_servers_messages():
    texts = [v for k, v in vars(ratelimit).items() if k.endswith("_TEXT") and isinstance(v, str)]
    texts += list(main.CHECK_MESSAGES.values())
    src = open(main.__file__, encoding="utf-8").read()
    texts += re.findall(r'"detail":\s*"([^"]*)"', src)
    assert_no_beta(texts, "server messages")


def test_the_invite_gate_is_gone():
    assert not hasattr(main, "INVITE_ONLY") and not hasattr(main, "_require_invite")
    assert c.post("/join", json={"code": "K7PM4QXT", "device_id": "x"}).status_code in (404, 405)
    assert "function join(" not in JS["app.js"] and "joinRequest" not in JS["lib.js"]
    assert not any("Invite code" in t or "Join the" in t for t in js_strings(JS["app.js"]))


# D-184 (Sushil, 2026-10-08, "yes"): everyone has the full plan free until billing ships, so no plan name,
# price or upgrade shows. The future names ("Label", "Label Master") wait for billing too. "Free ·
# shelf by shelf" describes a feature, not a plan, and "Label" alone is everywhere, so neither is matched.
PLAN = re.compile(r"\bPro\b|\bLabel (Master|Plus)\b|\bupgrad(e|es|ed|ing)\b|(\bRs\.?|\u20b9)\s?\d|\bper month\b|\ba month\b",
                  re.I)


def assert_no_plan(texts, where):
    bad = [t for t in texts if isinstance(t, str) and PLAN.search(t)]
    assert not bad, f"{where}: names a plan, a price or an upgrade\n" + "\n".join(f"  {t!r}" for t in bad)


def test_the_plan_lint_catches_it():
    for t in ("Pro \u00b7 in preparation", "Label Master", "Label Plus", "Upgrade now", "Rs 51", "\u20b951",
              "Rs. 51 a month"):
        assert PLAN.search(t), t
    for t in ("In preparation", "Free \u00b7 shelf by shelf", "InsideLabel", "Protein", "process", "provenance"):
        assert not PLAN.search(t), t


def test_no_plan_names_prices_or_upgrades():
    for name, src in JS.items():
        assert_no_plan(js_strings(src), f"web/{name}")
    assert_no_plan(_page_text(HTML), "web/index.html")
    texts = []
    for name, value in vars(screen).items():
        if name.isupper():
            texts += list(strings(value, skip_keys=NOT_SHOWN))
    assert_no_plan(texts, "lenses/screen.py")
    pages = sorted(glob.glob(os.path.join(ROOT, "web", "site", "*.html"))) + [os.path.join(ROOT, "web", "design.html")]
    for p in pages:
        with open(p, encoding="utf-8") as f:
            assert_no_plan(_page_text(f.read()), os.path.relpath(p, ROOT))
