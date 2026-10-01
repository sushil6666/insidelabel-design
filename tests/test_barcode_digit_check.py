"""
D-146 (RECOMMENDED): a code the scanner or a barcode photo reads for a pack not in the
catalogue is shown back before the ingredients photo, its first 3 and last 4 digits
large ("Check these match the numbers under the barcode": "Yes, they match" or "Scan
again"). A catalogue hit names the product with "Not this pack? Scan again". Nothing is
stored for a dropped code; the answer (confirmed, rescanned) is kept with the scan and
shown on /review as supporting evidence only. No typing (D-104); the words are
lenses/screen.py's (D-091).
"""
import json
import os
import re

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_review import TOKEN, approve, client, q, take_next, vision  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.lenses import screen  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"digit-check" + os.urandom(8)
WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def test_the_digits_are_split_as_the_pack_prints_them():
    c = screen.barcode_check("8901499008343")
    assert (c["first"], c["middle"], c["last"], c["code"]) == ("890", "149900", "8343", "8901499008343")
    assert c["text"] == "Check these match the numbers under the barcode"
    assert (c["yes"], c["again"]) == ("Yes, they match", "Scan again")
    # a UPC-A is kept as 13 digits with a leading 0 (D-104) but printed as its 12
    assert screen.barcode_check("0012345678905")["code"] == "012345678905"


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def lookup(code, **extra):
    return TestClient(main.app).post("/scan", data={"barcode": code, "barcode_source": "camera", **extra})


def test_a_code_not_in_the_catalogue_comes_back_to_be_checked_and_nothing_is_stored(env):
    uri, code = env, gtin()
    before = q(uri, "SELECT count(*) FROM scans")[0][0]
    r = lookup(code)
    assert r.status_code == 404 and r.json()["error"] == "not_in_catalogue"
    c = r.json()["barcode_check"]
    assert c["first"] + c["middle"] + c["last"] == code and c["yes"] == "Yes, they match"
    assert q(uri, "SELECT count(*) FROM scans")[0][0] == before
    assert q(uri, "SELECT count(*) FROM products WHERE barcode = %s", code)[0][0] == 0


def test_the_answer_is_kept_with_the_scan_and_shown_to_the_reviewer(env):
    uri, code = env, gtin()
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", JPEG, "image/jpeg")}, data={
        "replay": vision(["Wheat flour", "Sugar"]), "barcode": code, "barcode_source": "camera",
        "barcode_answer": "rescanned"})
    assert r.status_code == 200, r.text
    assert q(uri, "SELECT request->>'barcode_answer' FROM scans WHERE id = %s", r.json()["scan_id"])[0][0] == \
        "rescanned"
    c = client()
    page = c.get(f"/review/item/{take_next(c)}").text
    assert 'id="barcode-answer"' in page and "scanned again before this code" in page
    assert "Supporting evidence" in page and "only (D-146)" in page


def test_a_bad_answer_is_refused():
    r = TestClient(main.app).post("/scan", data={"barcode": gtin(), "barcode_answer": "typed"})
    assert r.status_code == 422 and r.json()["error"] == "bad_barcode_answer"


def test_a_catalogue_hit_offers_the_way_back_to_the_scanner(env):
    uri, code = env, gtin()
    TestClient(main.app).post("/scan", files={"back": ("b.jpg", JPEG + b"2", "image/jpeg")}, data={
        "replay": vision(["Oats"]), "barcode": code, "barcode_source": "camera", "barcode_answer": "confirmed"})
    c = client()
    # D-143 still holds: the photos don't show this camera code, so the reviewer ticks that they checked it
    approve(c, take_next(c), name="Oats", ingredients="Oats", barcode=code, barcode_checked="1")
    hit = lookup(code, barcode_answer="rescanned").json()
    assert hit["catalogue"]["source"] == "catalogue" and hit["product"]["name"] == "Oats"
    assert hit["screen"]["rescan"] == {"text": "Not this pack?", "button": "Scan again"}
    assert "barcode_check" not in json.dumps(hit)                        # no digit check for a hit
    assert q(uri, "SELECT request->>'barcode_answer' FROM scans WHERE id = %s", hit["scan_id"])[0][0] == "rescanned"


def test_the_app_takes_every_word_from_the_server_and_never_types_a_barcode():
    app = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    fn = app[app.index("function digitCheck(c)"):app.index("\n}\n", app.index("function digitCheck(c)"))]
    assert not re.search(r'"[A-Z][a-z]+ [a-z]', fn), "digitCheck composes its own words"      # D-091
    assert "c.title" in fn and "c.text" in fn and "c.yes" in fn and "c.again" in fn
    assert 's.rescan.text' in app and 's.rescan.button' in app
    assert 'type: "number"' not in app and "inputmode" not in fn                          # D-104


def test_app_and_service_worker_versions_move_together():
    lib = open(os.path.join(WEB, "lib.js"), encoding="utf-8").read()
    sw = open(os.path.join(WEB, "sw.js"), encoding="utf-8").read()
    n_app = re.search(r'APP_VERSION = "web-(\d+)"', lib).group(1)
    n_sw = re.search(r'VERSION = "il-shell-(\d+)"', sw).group(1)
    assert n_app == n_sw and int(n_app) >= 30             # web-30 shipped D-146; later parts bump both
