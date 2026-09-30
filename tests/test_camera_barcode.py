"""
D-143 (RECOMMENDED): a barcode from the camera scanner is set against the scan's
own photos and OCR text. The scanner takes a code seen in two frames of one
view, so one blur can give the same wrong code twice: product 42 was published
under the camera's 4901196008343 while its back photo reads 8901499008343.
A code nothing else shows goes to a reviewer to check before publishing; the
user's result doesn't change. Real zxing-cpp reads of generated barcodes.
"""
import json

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel import barcode  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import ocr_check  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import checker, routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402
from test_check_photo import barcode_photo, label_photo  # noqa: E402
from test_review import TOKEN, approve, client, q, take_next, vision  # noqa: E402

WRONG, RIGHT = "4901196008343", "8901499008343"


# ---------------------------------------------------------------- barcode.confirm()

def test_a_photo_that_reads_the_same_code_confirms_it():
    assert barcode.confirm(RIGHT, [("back", barcode_photo(RIGHT))])["status"] == "confirmed"


def test_product_42s_case_is_a_mismatch():
    got = barcode.confirm(WRONG, [("back", barcode_photo(RIGHT))])
    assert got["status"] == "mismatch" and got["photo_codes"] == {"back": [RIGHT]}


def test_the_digits_in_the_ocr_text_confirm_it():
    assert barcode.confirm(RIGHT, [("back", label_photo())], "Net wt 250 g\n8 901499 008343")["status"] == "confirmed"


def test_nothing_showing_it_is_not_shown_and_the_ocr_codes_are_listed_not_trusted():
    got = barcode.confirm(WRONG, [("back", label_photo())], "8 901499 008343")
    assert got["status"] == "not_shown" and got["ocr_codes"] == [RIGHT]


def test_what_needs_a_person():
    mismatch = {"code": WRONG, "status": "mismatch", "photo_codes": {"back": [RIGHT]}, "source": "camera"}
    assert barcode.unconfirmed(mismatch) is mismatch
    assert "photos read 8901499008343" in barcode.check_text(mismatch)
    assert barcode.unconfirmed({**mismatch, "status": "confirmed"}) is None
    assert barcode.unconfirmed({**mismatch, "source": "photo"}) is None     # a barcode photo's own rule (D-144)
    assert barcode.unconfirmed({**mismatch, "source": None}) is None        # not the app (D-104): recorded only
    assert barcode.unconfirmed(None) is None


def test_the_review_agents_send_it_to_a_person():
    bad = {"code": WRONG, "status": "not_shown", "photo_codes": {}, "ocr_codes": [], "source": "camera"}
    (row,) = [c for c in checker.check({"barcode": WRONG}, {"barcode_check": bad}) if c["check"] == "barcode_confirmed"]
    assert not row["ok"] and "camera scanner alone" in row["detail"]
    (row,) = [c for c in checker.check({"barcode": WRONG}, {"barcode_check": {**bad, "status": "confirmed"}})
              if c["check"] == "barcode_confirmed"]
    assert row["ok"]


# ---------------------------------------------------------------- /scan and /review

@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    mp.setattr(ocr_check, "AVAILABLE", False)          # no Tesseract on generated photos
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def send(code, photo, source="camera"):
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                  data={"replay": vision(["Corn grits", "Salt"]), "barcode": code,
                                        "barcode_source": source})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_scan_keeps_the_check_and_the_user_result_is_unchanged(env):
    uri = env
    j = send(WRONG, barcode_photo(RIGHT))
    assert "barcode_check" not in json.dumps(j["screen"]) and j["verdict"] is not None
    (bc, ms), = q(uri, "SELECT barcode_check, timings->'barcode_check_ms' FROM scans WHERE id = %s", j["scan_id"])
    assert bc["status"] == "mismatch" and bc["source"] == "camera" and bc["code"] == WRONG and ms is not None


def test_a_reviewer_must_check_a_barcode_the_photos_dont_confirm(env):
    uri = env
    c = client()
    item = take_next(c)
    page = c.get(f"/review/item/{item}").text
    assert 'id="barcode-unsure"' in page and "photos read 8901499008343" in page
    r = approve(c, item, name="Corn Flakes", ingredients="Corn grits\nSalt", barcode=WRONG)
    assert "I+checked" in r.headers["location"] or "I%20checked" in r.headers["location"]
    assert q(uri, "SELECT count(*) FROM product_versions WHERE status = 'published'")[0][0] == 0
    # the reviewer reads the printed digits and types them: published under them, the change recorded (D-142)
    approve(c, item, name="Corn Flakes", ingredients="Corn grits\nSalt", barcode=RIGHT, note="digits on the photo")
    assert q(uri, "SELECT barcode FROM products WHERE name = 'Corn Flakes'")[0][0] == RIGHT
    assert q(uri, "SELECT old_barcode, via FROM barcode_changes")[0] == (WRONG, "review")
    assert q(uri, "SELECT barcode_checked_by FROM review_queue WHERE id = %s", item)[0][0] is None


def test_a_ticked_check_publishes_and_names_the_reviewer(env):
    uri = env
    send("8906002430017", label_photo())                     # nothing shows it
    c = client()
    item = take_next(c)
    approve(c, item, name="Poha", ingredients="Corn grits\nSalt", barcode="8906002430017", barcode_checked="1")
    assert q(uri, "SELECT status, barcode_checked_by FROM review_queue WHERE id = %s", item)[0] == ("done", "asha")


def test_a_confirmed_or_photo_read_code_needs_no_tick(env):
    uri = env
    for code, photo, source in (("8901063093089", barcode_photo("8901063093089"), "camera"),
                                ("8906002430031", label_photo(), "photo")):
        send(code, photo, source)
        c = client()
        item = take_next(c)
        assert 'id="barcode-unsure"' not in c.get(f"/review/item/{item}").text
        approve(c, item, name="Oats", ingredients="Corn grits\nSalt", barcode=code)
        assert q(uri, "SELECT status FROM review_queue WHERE id = %s", item)[0][0] == "done"
