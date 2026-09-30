"""
D-142 (RECOMMENDED): a product's barcode changes only through a recorded
correction. Found by the D-141 measurement: product 42 was published under the
camera scanner's 4901196008343 while its own back photo reads 8901499008343.

The old code, the new one, who, when and why are kept (barcode_changes); the
database refuses a change without that record (migration 020), so a direct
UPDATE fails; the review form can't change a published product's barcode.
"""
import os
import sys

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import accounts, routes  # noqa: E402
from insidelabel.review.service import ReviewError, ReviewService  # noqa: E402
from test_review import approve, client, q, scan, take_next  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import barcodes  # noqa: E402

WRONG, RIGHT = "4901196008343", "8901499008343"      # the camera's read, the photo's read (product 42)
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    accounts.add(uri, "sushil", PASSWORD)
    yield uri
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def published(uri, code, name="Corn Flakes"):
    """A product scanned under `code` and published by a reviewer; its id."""
    scan(["Corn grits", "Sugar", "Salt"], barcode=code)
    c = client("sushil", PASSWORD)
    approve(c, take_next(c), name=name, ingredients="Corn grits\nSugar\nSalt", barcode=code)
    return q(uri, "SELECT id FROM products WHERE barcode = %s", code)[0][0]


def test_a_published_barcode_is_corrected_and_the_old_one_kept(env):
    uri = env
    pid = published(uri, WRONG)
    svc = ReviewService(uri, main.ENGINE_VERSION)
    row = svc.correct_barcode(pid, RIGHT, "sushil", "printed under the bars: 8 901499 008343",
                              evidence="03f8277a.jpg")
    assert (row["old_barcode"], row["new_barcode"], row["changed_by"], row["via"]) == (WRONG, RIGHT, "sushil",
                                                                                         "correction")
    assert q(uri, "SELECT barcode FROM products WHERE id = %s", pid)[0][0] == RIGHT
    # the catalogue answers the right code, not the wrong one
    assert main.STORE.find_current(RIGHT)["product_id"] == pid
    assert main.STORE.find_current(WRONG) is None
    # the old code is findable in the record, with who, when, why
    h = svc.barcode_history(code=WRONG)
    assert len(h) == 1 and h[0]["product_id"] == pid and h[0]["reason"].startswith("printed under")
    assert h[0]["evidence"] == "03f8277a.jpg" and h[0]["created_at"] is not None
    assert [r["new_barcode"] for r in svc.barcode_history(product_id=pid)] == [RIGHT]


@pytest.mark.parametrize("new, by, why, says", [
    ("8901499008344", "sushil", "photo", "doesn't look right"),                 # check digit
    ("12222333333333", "sushil", "photo", "carton"),                            # a case code
    ("8901499008343", "sushil", "  ", "Say why"),                              # no reason
    ("8901499008343", "nobody", "photo", "not an active reviewer"),            # not a reviewer
])
def test_a_correction_is_refused(env, new, by, why, says):
    uri = env
    pid = q(uri, "SELECT id FROM products WHERE name = 'Corn Flakes'")[0][0]
    before = q(uri, "SELECT barcode FROM products WHERE id = %s", pid)[0][0]
    with pytest.raises(ReviewError, match=says):
        ReviewService(uri, None).correct_barcode(pid, new, by, why)
    assert q(uri, "SELECT barcode FROM products WHERE id = %s", pid)[0][0] == before


def test_a_code_another_product_has_is_refused(env):
    uri = env
    other = published(uri, "8901063093089", name="Oats")
    svc = ReviewService(uri, None)
    with pytest.raises(ReviewError, match="already belongs to product"):
        svc.correct_barcode(other, RIGHT, "sushil", "photo")
    with pytest.raises(ReviewError, match="already has barcode"):
        svc.correct_barcode(other, "8901063093089", "sushil", "photo")


def test_a_direct_update_is_refused_by_the_database(env):
    uri = env
    pid = q(uri, "SELECT id FROM products WHERE barcode = %s", RIGHT)[0][0]
    with pytest.raises(psycopg.errors.RaiseException, match="D-142"):
        q(uri, "UPDATE products SET barcode = %s WHERE id = %s", "8906002430017", pid)
    assert q(uri, "SELECT barcode FROM products WHERE id = %s", pid)[0][0] == RIGHT


def test_the_review_form_cant_change_a_published_barcode(env):
    uri = env
    pid = q(uri, "SELECT id FROM products WHERE barcode = %s", RIGHT)[0][0]
    TestClient(main.app).post("/report", json={"scan_id": q(uri, """SELECT s.id::text FROM scans s
        JOIN product_versions v ON v.id = s.product_version_id WHERE v.product_id = %s LIMIT 1""", pid)[0][0],
                                               "field": "ingredients", "note": "salt is iodised"})
    c = client("sushil", PASSWORD)
    r = approve(c, take_next(c), name="Corn Flakes", ingredients="Corn grits\nSugar\nIodised salt",
                barcode="8906002430017")
    assert "barcode+correction" in r.headers["location"] or "barcode%20correction" in r.headers["location"]
    assert q(uri, "SELECT barcode FROM products WHERE id = %s", pid)[0][0] == RIGHT


def test_a_never_published_product_gets_its_barcode_set_at_review_and_recorded(env):
    uri = env
    scan(["Rice", "Salt"], barcode="8906002430024")            # the scan's read, wrong
    c = client("sushil", PASSWORD)
    item = take_next(c)
    approve(c, item, name="Poha", ingredients="Rice\nSalt", barcode="8906002430017", note="digits on the photo")
    pid = q(uri, "SELECT id FROM products WHERE barcode = %s", "8906002430017")[0][0]
    (row,) = ReviewService(uri, None).barcode_history(product_id=pid)
    assert (row["old_barcode"], row["via"], row["changed_by"]) == ("8906002430024", "review", "sushil")
    assert row["reason"] == f"Set at review of item {item}: digits on the photo"


def test_the_tool_is_a_dry_run_until_yes(env):
    uri = env
    pid = q(uri, "SELECT id FROM products WHERE barcode = %s", "8906002430017")[0][0]
    svc, lines = ReviewService(uri, None), []
    assert barcodes.fix(svc, pid, "8906002430031", "sushil", "photo", out=lines.append) is None
    assert "dry run" in lines[-1]
    assert q(uri, "SELECT barcode FROM products WHERE id = %s", pid)[0][0] == "8906002430017"
    row = barcodes.fix(svc, pid, "8906002430031", "sushil", "photo", yes=True, out=lines.append)
    assert row["new_barcode"] == "8906002430031"
    lines = []
    barcodes.history(svc, "8906002430017", out=lines.append)
    assert any("8906002430017 -> 8906002430031" in x for x in lines)
