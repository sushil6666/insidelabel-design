"""
D-144 at /scan: a scan sent without a barcode, whose own photo shows one. The code
counts when two zxing-cpp reads agree, or when its digits are printed in the back
photo's OCR text (D-093's second reading, the text /scan already has: no extra
call). Otherwise the scan goes on without one (D-107: its result, an unlisted row).

Cloud Vision's text is served by its replay mode (no call leaves the machine).
"""
import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision, ocr_check  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from test_barcode_two_reads import CORN_FLAKES, CORN_FLAKES_OCR, OTHER_MISREAD, reads  # noqa: E402
from test_check_photo import barcode_photo  # noqa: E402
from test_review import q, vision  # noqa: E402

INGREDIENTS = ["Corn grits", "Sugar", "Salt"]


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    mp = pytest.MonkeyPatch()
    mp.setattr(ocr_check, "AVAILABLE", False)          # no Tesseract: Cloud Vision's text is replayed
    yield uri
    mp.undo()
    main.STORE, main.MEDIA = saved


def scan(photo, text=CORN_FLAKES_OCR):
    with cloud_vision.replaying({cloud_vision.digest(photo): text}):
        r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                      data={"replay": vision(INGREDIENTS)})
    assert r.status_code == 200, r.text
    return r.json()


def row(uri, scan_id):
    return q(uri, """SELECT s.outcome, s.barcode_check, p.barcode FROM scans s
                       LEFT JOIN product_versions v ON v.id = s.product_version_id
                       LEFT JOIN products p ON p.id = v.product_id WHERE s.id = %s""", scan_id)[0]


def test_two_reads_that_agree_file_the_pack_under_its_code(env):
    uri = env
    j = scan(barcode_photo(CORN_FLAKES), text="INGREDIENTS: Corn grits, Sugar, Salt.")   # no digits in the text
    outcome, check, code = row(uri, j["scan_id"])
    assert (outcome, code) == ("verdict", CORN_FLAKES)
    assert check["source"] == "scan_photo" and check["status"] == "found"


def test_a_correct_code_in_the_ocr_text_counts_when_the_second_read_is_empty(env, monkeypatch):
    uri = env
    reads(monkeypatch, "8901499008350", None)          # another pack's photo, same reading pattern
    j = scan(barcode_photo(CORN_FLAKES), text=CORN_FLAKES_OCR.replace("8 901499 008343", "8 901499 008350"))
    assert row(uri, j["scan_id"])[2] == "8901499008350"


def test_0921129008343_is_refused_and_the_scan_goes_on_unlisted(env, monkeypatch):
    uri = env
    reads(monkeypatch, OTHER_MISREAD, None)
    j = scan(barcode_photo(CORN_FLAKES))
    outcome, check, code = row(uri, j["scan_id"])
    assert (outcome, code) == ("unlisted", None)
    assert check["status"] == "unsure" and check["code"] is None
    assert j["verdict"] is not None                     # the user still gets the result (D-107)
    assert q(uri, "SELECT count(*) FROM products WHERE barcode = %s", OTHER_MISREAD)[0][0] == 0


def test_a_code_sent_by_the_app_is_not_replaced(env, monkeypatch):
    uri = env
    photo = barcode_photo(CORN_FLAKES)
    with cloud_vision.replaying({cloud_vision.digest(photo): CORN_FLAKES_OCR}):
        j = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                      data={"replay": vision(INGREDIENTS), "barcode": "8906002430017",
                                            "barcode_source": "camera"}).json()
    outcome, check, code = row(uri, j["scan_id"])
    assert code == "8906002430017" and check["source"] == "camera" and check["status"] == "mismatch"
