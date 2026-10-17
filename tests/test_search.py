"""
D-204 (Sushil, 2026-10-17): search the packs we've checked, by name. One test or more for each
of his five changes:

1. Infant packs are left out of search: no row, and no way to open one from a search.
2. The brand matches as well as the name and variant; best match first, then name, never
   products.scan_count.
3. The no-match words are his: "We haven't checked this one yet. Scan the pack in the shop to check it."
4. "Reviewed" means a published version, whoever published it; "Checked on" is its published date.
5. Rate limited like the other free endpoints (D-095); an empty or one-letter query returns
   nothing; the search words are never stored or logged.

Plus what was kept: rows carry no finding, colour or allergen mark; a pack opened from a search
says where it came from and offers the shop list.
"""
import json
import logging
import re

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_pack_kind import reading, st  # noqa: E402
from test_pack_kind_db import env, item_page, post, q  # noqa: E402, F401

from insidelabel import ratelimit  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.lenses import screen  # noqa: E402

c = TestClient(main.app)
DEVICE = "6f1c2c1e-6d0b-4c55-9a51-1a1a1a1a1a1a"
KID_MILK = json.dumps([{"ref": "p1", "age": "kid", "avoid": ["milk"]}])


def publish(env, name, brand="Testco", variant="", ingredients=("Wheat flour", "Sugar", "Milk solids"),
            statements=(), category="7.2.1"):
    """A pack scanned, then approved by a person on /review: a published, current version."""
    bc = gtin()
    j = post(bc, reading(list(ingredients), list(statements), name=name))
    item_id, rc, page = item_page(env, j["catalogue"]["product_version_id"])
    token = re.search(r'name="csrf" value="([0-9a-f]+)"', page).group(1)
    rc.post(f"/review/item/{item_id}/claim", data={"csrf": token})
    r = rc.post(f"/review/item/{item_id}/approve", follow_redirects=False, data={
        "csrf": token, "name": name, "brand": brand, "variant": variant, "barcode": "",
        "ingredients": "\n".join(ingredients), "allergen_statement": "", "front_claims": "", "note": "",
        "category": category})
    assert r.status_code == 303 and "error=" not in r.headers["location"], r.headers["location"]
    return bc


def search(text, device=DEVICE):
    r = c.post("/search", json={"q": text, "device_id": device})
    assert r.status_code == 200, r.text
    return r.json()


def names(j):
    return [x["name"] for x in j["results"]]


def open_from_search(bc, profiles=None):
    return c.post("/scan", data={"barcode": bc, "barcode_source": "search", "device_id": DEVICE,
                                 **({"profiles": profiles} if profiles else {})})


# ---------------------------------------------------------------- 1. no infant packs

@pytest.mark.parametrize("switch", ["infant_on", "infant_off"])
def test_an_infant_pack_never_shows_in_search_and_cannot_be_opened_from_one(env, switch, request):
    request.getfixturevalue(switch)
    word = {"infant_on": "Kwelto", "infant_off": "Drumbex"}[switch]    # far apart, so fuzzy matching can't mix them
    infant = publish(env, f"{word} Rice Cereal", ingredients=("Rice flour", "Milk solids"),
                     statements=[st("Processed Cereal Based Complementary Food", "front")], category="13.2")
    food = publish(env, f"{word} Biscuits")
    supplement = publish(env, f"{word} Multivitamin", ingredients=("Calcium carbonate", "Vitamin D3"),
                         statements=[st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE")])
    got = search(word.lower())
    assert {x["barcode"] for x in got["results"]} == {food, supplement}          # supplements are in
    r = open_from_search(infant)
    assert r.status_code == 404 and r.json()["error"] == "not_in_catalogue"
    assert "shop_list" not in json.dumps(r.json())
    # A barcode scan of the same pack in the shop is unchanged (D-200, D-202).
    assert c.post("/scan", data={"barcode": infant}).json()["pack_kind"]["code"] == "infant"


# ---------------------------------------------------------------- 2. brand, order, never scan_count

def test_the_brand_alone_finds_its_packs(env):
    a = publish(env, "Cashew Cookies", brand="Brivanta")
    b = publish(env, "Salted Crackers", brand="Brivanta", variant="Family pack")
    assert {x["barcode"] for x in search("brivanta")["results"]} == {a, b}
    # With pg_trgm the brand's other packs may follow; the best match is first either way.
    assert names(search("brivanta salted"))[0] == "Salted Crackers"
    assert names(search("family pack brivanta"))[0] == "Salted Crackers"         # the variant counts too


def test_a_misspelt_name_still_finds_its_pack_with_pg_trgm(env):
    with psycopg.connect(env) as conn:
        if conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'").fetchone() is None:
            pytest.skip("the embedded test server has no pg_trgm (migration 002 is skipped there)")
    publish(env, "Good Dax Cookies", brand="Britonnia")
    assert names(search("britonia good dax"))[0] == "Good Dax Cookies"


def test_the_best_match_comes_first_then_the_name_and_never_the_scan_count(env):
    long_one = publish(env, "Zuvaro Day Choco Chip Cookies", brand="Quelt")
    publish(env, "Zuvaro Day", brand="Quelt")
    publish(env, "Zuvaro Day Almond", brand="Quelt")
    # The longer pack has been opened far more often; that must change nothing.
    with psycopg.connect(env) as conn:
        conn.execute("UPDATE products SET scan_count = 10000 WHERE barcode = %s", (long_one,))
    assert names(search("zuvaro day")) == ["Zuvaro Day", "Zuvaro Day Almond", "Zuvaro Day Choco Chip Cookies"]


def test_the_order_rule_has_no_findings_or_scan_count_in_it():
    src = open(main.__file__.replace("api/main.py", "db/store.py")).read()
    body = src[src.index("    def search(self, q"):src.index("    # -- writes")]
    body = body.split('"""', 2)[2]                       # the code, not the docstring that names them
    assert "scan_count" not in body and "findings" not in body and "concern" not in body


# ---------------------------------------------------------------- 3. the no-match words

def test_the_no_match_words_are_sushils(env):
    assert screen.SEARCH_NONE == "We haven't checked this one yet. Scan the pack in the shop to check it."
    got = search("nothing called this exists xq")
    assert got == {"results": [], "none": screen.SEARCH_NONE}
    r = open_from_search(gtin())
    assert r.status_code == 404 and r.json()["detail"] == screen.SEARCH_NONE


# ---------------------------------------------------------------- 4. published only; the published date

def test_only_a_published_version_shows_whoever_published_it(env):
    waiting = gtin()
    post(waiting, reading(["Sugar", "Cocoa"], name="Plombir Waiting Bar"))       # in review, never published
    assert search("plombir waiting")["results"] == []
    assert open_from_search(waiting).status_code == 404
    bc = publish(env, "Plombir Bar")
    # D-117: the review agents publish too; who published doesn't matter, only that it is published.
    with psycopg.connect(env) as conn:
        conn.execute("""UPDATE product_versions v SET verified_by = 'agent:review'
                          FROM products p WHERE p.id = v.product_id AND p.barcode = %s AND v.is_current""", (bc,))
    assert [x["barcode"] for x in search("plombir")["results"]] == [bc]


def test_checked_on_is_the_published_date_not_a_later_photo_match(env):
    bc = publish(env, "Torvik Rusk", variant="Elaichi")
    with psycopg.connect(env) as conn:
        conn.execute("""UPDATE product_versions v SET verified_at = '2026-09-03 10:00+00',
                               last_verified_at = '2026-10-15 10:00+00'
                          FROM products p WHERE p.id = v.product_id AND p.barcode = %s AND v.is_current""", (bc,))
    [row] = search("torvik")["results"]
    assert row["checked_on"] == "2026-09-03" and row["checked"] == "Checked on 3 Sep 2026"
    s = open_from_search(bc).json()["screen"]
    assert s["from_search"]["title"] == "From our catalogue: the pack we checked on 3 Sep 2026."


# ---------------------------------------------------------------- 5. limits, short queries, nothing kept

@pytest.mark.parametrize("text", ["", " ", "a", "7", " b ", "!!", "a-"])
def test_an_empty_or_one_letter_query_returns_nothing(env, text):
    publish_once(env)
    assert search(text) == {"results": [], "none": None}


_once = []


def publish_once(env):
    if not _once:
        _once.append(publish(env, "Abacus Atta"))


def test_search_words_need_two_letters_or_digits():
    assert Store.search_words("a") is None and Store.search_words("  ") is None and Store.search_words("a!") is None
    assert Store.search_words("Good-Day!!") == "good day"
    assert Store.search_words("x" * 500) == "x" * Store.SEARCH_MAX_CHARS


def test_search_is_rate_limited_per_install_and_address(monkeypatch):
    monkeypatch.setattr(ratelimit.LIMITER, "rules", {"search": {"device": [(3, 600)], "ip": [(5, 600)]}})
    ratelimit.LIMITER.reset()
    try:
        for _ in range(3):
            assert c.post("/search", json={"q": "atta", "device_id": DEVICE}).status_code == 200
        r = c.post("/search", json={"q": "atta", "device_id": DEVICE})
        assert r.status_code == 429 and r.json()["error"] == "rate_limited"
        assert r.json()["detail"].startswith("That's a lot of searches in a short time.")
        other = "0b1c2c1e-6d0b-4c55-9a51-1a1a1a1a1a1a"
        assert c.post("/search", json={"q": "atta", "device_id": other}).status_code == 200
        assert c.post("/search", json={"q": "atta", "device_id": other}).status_code == 200
        assert c.post("/search", json={"q": "atta", "device_id": other}).status_code == 429   # the address's 5
    finally:
        ratelimit.LIMITER.reset()
    assert "search" in ratelimit.RULES


def test_search_words_are_never_stored_or_logged(env, caplog):
    bc = publish(env, "Wynfield Muesli")
    word = "wynfield muesli secretword"
    before = q(env, "SELECT count(*) FROM scans")[0][0]
    with caplog.at_level(logging.DEBUG):
        search(word)
        search("wynfield")
    assert q(env, "SELECT count(*) FROM scans")[0][0] == before                    # a search writes nothing
    assert "secretword" not in caplog.text
    # Opening a result is a scan like a barcode hit, marked as from a search, with no words in it.
    open_from_search(bc)
    [(via, trace)] = q(env, """SELECT s.resolved_via, row_to_json(s)::text FROM scans s
                                 JOIN product_versions v ON v.id = s.product_version_id
                                 JOIN products p ON p.id = v.product_id
                                WHERE p.barcode = %s ORDER BY s.created_at DESC LIMIT 1""", bc)
    assert via == "search" and "wynfield" not in (trace or "").lower()
    # Nowhere in the database holds the words.
    dump = json.dumps(q(env, "SELECT row_to_json(s)::text FROM scans s"), default=str)
    assert "secretword" not in dump


def test_the_query_goes_in_the_body_never_the_url():
    lib = open(main.WEB_DIR + "/lib.js").read()
    call = lib[lib.index("export const searchRequest"):lib.index("export const reportRequest")]
    assert 'call("/search", { method: "POST"' in call and "?q=" not in call
    assert c.get("/search?q=atta").status_code == 405


# ---------------------------------------------------------------- what was kept

def test_rows_carry_no_finding_colour_or_allergen_mark(env):
    publish(env, "Nimbro Milk Rusk", ingredients=("Wheat flour", "Milk solids", "Sugar"))
    [row] = c.post("/search", json={"q": "nimbro", "device_id": DEVICE}).json()["results"]
    assert set(row) <= {"barcode", "brand", "name", "variant", "quantity", "checked_on", "checked", "pack_picture"}


def test_a_pack_opened_from_a_search_says_where_it_came_from_and_offers_the_shop_list(env):
    bc = publish(env, "Ostrel Milk Biscuits", ingredients=("Wheat flour", "Milk solids", "Sugar"))
    r = open_from_search(bc, profiles=KID_MILK)
    assert r.status_code == 200, r.text
    j = r.json()
    s = j["screen"]
    assert s["from_search"]["text"] == "Recipes and sizes change, so check the pack in the shop."
    assert s["shop_list"] is True
    assert list(j)[0] == "allergens"                                                # D-060: still first
    assert [p["status"] for p in s["people"]] == ["contains"]                       # the person's card, as a hit
    # A barcode hit from the scanner says none of this.
    plain = c.post("/scan", data={"barcode": bc}).json()["screen"]
    assert "from_search" not in plain and "shop_list" not in plain


def test_a_search_open_takes_its_barcode_only(env):
    bc = publish(env, "Pravex Toast")
    r = c.post("/scan", files={"back": ("b.jpg", b"\xff\xd8\xff\xe0x", "image/jpeg")},
               data={"barcode": bc, "barcode_source": "search"})
    assert r.status_code == 422 and r.json()["error"] == "bad_search_open"


def test_the_new_words_pass_the_wording_rules():
    from test_wording import FORBIDDEN, FORBIDDEN_SAFETY
    for text in (screen.SEARCH_NONE, screen.SEARCH_RESULT_TITLE, screen.SEARCH_RESULT_TEXT,
                 screen.SEARCH_CHECKED, ratelimit.SEARCH_TEXT):
        low = text.lower()
        assert not any(re.search(rf"\b{re.escape(w)}\b", low) for w in FORBIDDEN + FORBIDDEN_SAFETY), text
