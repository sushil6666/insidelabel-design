"""
D-174 (Sushil, 2026-10-07; review items #71 and #72): a pack sent to us whose photos
include the nutrition table publishes with its checked table in one review, so nobody
is asked for the table again.

Item #71: Britannia 50 50 Maska Chaska's list and table were photographed (D-171),
Gemini blocked the read (RECITATION, D-172), the pack was sent to us and published
without its table, and the next scan asked for the table (D-168, item #72).

The table is read once per item: an earlier answer that copied it is checked again for
free; otherwise one table-only read (its own prompt; the label prompt stays frozen,
D-081). nutrition.check() keeps a number only where Cloud Vision's text has it and the
table adds up (D-133). The reviewer's tick publishes it, through approve() only. A
blocked or failed read is stored with its error (D-092, D-172) and the item still works.
Model answers and Cloud Vision's text are replayed.
"""
import base64
import io
import json
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from PIL import Image  # noqa: E402
from test_nutrition import GOLD, printed  # noqa: E402
from test_web import JS  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision, gemini  # noqa: E402
from insidelabel.extraction.providers.prompt import VISION_PROMPT, VISION_RESPONSE_SCHEMA  # noqa: E402
from insidelabel.extraction.providers.table_prompt import (TABLE_PROMPT, TABLE_PROMPT_VERSION,  # noqa: E402
                                                           TABLE_SCHEMA)
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes, table_read  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

TOKEN = "sent-table-token"
TABLE = GOLD["maliban-wafer-cheese"]["nutrition"]
TEXT = "Ingredients: Refined wheat flour, Sugar, Palm oil. " + printed(TABLE)
c = TestClient(main.app)


class AnyPhoto(dict):
    """Cloud Vision's recorded text for whatever photo is read (the joined parts' bytes aren't known here)."""
    def get(self, _key, _default=None):
        return TEXT


def png(seed):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (seed * 37 % 255, 90, 160)).save(buf, "PNG")
    return buf.getvalue()


def answer(table=TABLE):
    return json.dumps({"nutrition": table, "net_quantity": None})


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    with psycopg.connect(uri) as conn:
        if conn.execute("SELECT count(*) FROM reviewers").fetchone()[0]:
            pytest.skip("reviewer accounts exist in this database; the shared token is refused")
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA, main.SENT_TABLE_CALL)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    mp.setattr(cloud_vision, "_REPLAY", AnyPhoto({"any": TEXT}))
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA, main.SENT_TABLE_CALL = saved


@pytest.fixture
def calls():
    """The table-only reads made, each answered with `calls.answer` (text, or an exception to raise)."""
    made = []

    def call(prompt, images):
        made.append((prompt, images))
        if isinstance(call.answer, Exception):
            raise call.answer
        return call.answer
    call.answer = answer()
    call.made = made
    main.SENT_TABLE_CALL = call
    yield call
    main.SENT_TABLE_CALL = None


def rows(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchall()


def reviewer():
    cred = base64.b64encode(f"asha:{TOKEN}".encode()).decode()
    return TestClient(main.app, headers={"Authorization": f"Basic {cred}"})


def csrf(html):
    return re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)


def blocked_pack(bc, kinds="list,table", dev=None):
    """A list and its table photographed (D-171), the read blocked (D-172), sent to us. Returns the item id."""
    dev = dev or str(uuid.uuid4())
    files = {"back": ("b.png", png(1), "image/png")}
    data = {"replay": gemini.blocked_marker("recitation"), "barcode": bc, "device_id": dev}
    if kinds:
        files["back2"] = ("t.png", png(2), "image/png")
        data["back_kinds"] = kinds
    r = c.post("/scan", files=files, data=data)
    assert r.status_code == 422 and r.json()["reliability"]["error"] == "vision_blocked", r.text
    sent = c.post("/send-to-us", json={"device_id": dev, "scan_ids": [r.json()["scan_id"]]})
    assert sent.status_code == 200, sent.text
    return sent.json()["review_id"]


def reads(uri, item):
    return rows(uri, "SELECT * FROM review_table_reads WHERE review_item_id = %s ORDER BY id", item)


def approve(item, bc, tick):
    client = reviewer()
    page = client.get(f"/review/item/{item}").text
    assert client.post(f"/review/item/{item}/claim", data={"csrf": csrf(page)}).status_code == 200
    form = {"csrf": csrf(page), "name": "50 50 Maska Chaska", "brand": "Britannia", "variant": "",
            "barcode": bc, "category": "7.2.1", "ingredients": "Refined wheat flour\nSugar\nPalm oil",
            "allergen_statement": "", "front_claims": "", "note": "", "drafted_by": "asha",
            "category_source": "reviewer"}
    if tick:
        form["nutrition_ok"] = "1"
    r = client.post(f"/review/item/{item}/approve", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/review", r.headers.get("location")


def published_table(uri, bc):
    return rows(uri, """SELECT v.nutrition FROM product_versions v JOIN products p ON p.id = v.product_id
                         WHERE p.barcode = %s AND v.is_current""", bc)[0]["nutrition"]


def lookup(bc):
    r = c.post("/scan", data={"barcode": bc})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- item #71's path

def test_a_sent_pack_has_its_table_read_and_published_with_the_tick(env, calls):
    bc = gtin()
    item = blocked_pack(bc)
    # The blocked scan kept Cloud Vision's text of its photo: the read uses it, not a second call.
    scan = rows(env, "SELECT s.* FROM scans s JOIN review_queue q ON q.scan_id = s.id WHERE q.id = %s", item)[0]
    assert scan["ocr"]["back"] == {"reader": "cloud_vision", "text": TEXT}
    assert scan["request"]["back_kinds"] == ["list", "table"]
    [(prompt, images)] = calls.made                                   # one paid read, after the reply
    assert prompt == TABLE_PROMPT and [r for _d, _m, r in images] == ["back"]
    [rd] = reads(env, item)
    assert rd["source"] == "table_read" and rd["prompt_version"] == TABLE_PROMPT_VERSION
    assert rd["model_raw"] == calls.answer and rd["model_error"] is None
    assert rd["ocr_reader"] == "cloud_vision" and rd["ocr_text"] == TEXT and rd["build"]
    assert rd["panel"]["status"] == "read" and rd["panel"]["values"]

    page = reviewer().get(f"/review/item/{item}").text
    assert "The nutrition table was read from these photos" in page
    assert "Every number shown to users matches the photo" in page
    assert "Read the nutrition table from these photos" not in page   # read once, not per view
    reviewer().get(f"/review/item/{item}")
    assert len(calls.made) == 1 and len(reads(env, item)) == 1

    approve(item, bc, tick=True)
    table = published_table(env, bc)
    assert table["status"] == "read" and table["confirmed_by"] == "asha"
    assert table["values"] == rd["panel"]["values"]
    # D-168: a pack with its table on file is never asked for it.
    hit = lookup(bc)
    assert hit["catalogue"]["table_wanted"] is False and hit["nutrition"]["status"] == "read"


def test_without_the_tick_the_pack_is_published_without_its_table(env, calls):
    bc = gtin()
    item = blocked_pack(bc)
    approve(item, bc, tick=False)
    assert published_table(env, bc) is None
    assert lookup(bc)["catalogue"]["table_wanted"] is True               # D-168's offer, as today


# ---------------------------------------------------------------- a blocked or failed table read

@pytest.mark.parametrize("failure, words", [
    (gemini.VisionBlocked("recitation"), "RECITATION"),
    ("not json {", "JSONDecodeError"),
])
def test_a_failed_table_read_keeps_its_error_and_the_item_still_works(env, calls, failure, words):
    calls.answer = failure
    bc = gtin()
    item = blocked_pack(bc)
    [rd] = reads(env, item)
    assert words in rd["model_error"] and rd["panel"] is None
    if isinstance(failure, gemini.VisionBlocked):
        assert rd["model_raw"] == gemini.blocked_marker("recitation")    # D-172's marker, never parsed
    page = reviewer().get(f"/review/item/{item}")
    assert page.status_code == 200
    assert "Table read failed" in page.text and "Read the nutrition table from these photos" in page.text
    assert "Every number shown to users matches the photo" not in page.text
    approve(item, bc, tick=True)                                          # a stray tick publishes no table
    assert published_table(env, bc) is None


def test_a_person_can_ask_for_the_read_again(env, calls, monkeypatch):
    calls.answer = gemini.VisionBlocked("recitation")
    bc = gtin()
    item = blocked_pack(bc)
    monkeypatch.setattr(table_read, "_paid_call", lambda prompt, images, usage=None: answer())
    client = reviewer()
    page = client.get(f"/review/item/{item}").text
    r = client.post(f"/review/item/{item}/read-table", data={"csrf": csrf(page)}, follow_redirects=False)
    assert r.status_code == 303
    last = reads(env, item)[-1]
    assert last["requested_by"] == "asha" and last["panel"]["status"] == "read"
    assert "The nutrition table was read from these photos" in client.get(f"/review/item/{item}").text
    # With a usable read on file, the button reads nothing more.
    client.post(f"/review/item/{item}/read-table", data={"csrf": csrf(page)}, follow_redirects=False)
    assert len(reads(env, item)) == 2


# ---------------------------------------------------------------- free first, and only when there's a table

def test_an_earlier_answer_that_copied_the_table_costs_no_read(env, calls):
    from test_send_to_us import vision
    dev, bc = str(uuid.uuid4()), gtin()
    ids = []
    for n in (3, 4):
        r = c.post("/scan", files={"back": ("b.png", png(n), "image/png")},
                   data={"replay": vision(back_status="unreadable", nutrition=TABLE), "barcode": bc,
                         "device_id": dev})
        assert r.status_code == 422
        ids.append(r.json()["scan_id"])
    item = c.post("/send-to-us", json={"device_id": dev, "scan_ids": ids}).json()["review_id"]
    assert calls.made == []
    [rd] = reads(env, item)
    assert rd["source"] == "stored_answer" and str(rd["scan_id"]) == ids[-1]
    assert rd["panel"]["status"] == "read" and rd["model_error"] is None


def test_no_table_photo_no_read(env, calls):
    item = blocked_pack(gtin(), kinds=None)                               # one photo, the list
    assert calls.made == [] and reads(env, item) == []
    item = blocked_pack(gtin(), kinds="list,list")                        # a long list in two parts (D-119)
    assert calls.made == [] and reads(env, item) == []


def test_an_older_two_part_scan_counts_as_list_and_table():
    assert table_read.has_table_photo({"back_parts": 2})
    assert not table_read.has_table_photo({"back_parts": 1})
    assert not table_read.has_table_photo({"back_parts": 2, "back_kinds": ["list", "list"]})
    assert table_read.has_table_photo({"back_parts": 2, "back_kinds": ["list", "table"]})


# ---------------------------------------------------------------- the request, the prompt and the app

def test_back_kinds_names_each_back_part(env):
    files = {"back": ("b.png", png(5), "image/png"), "back2": ("t.png", png(6), "image/png")}
    for bad in ("list", "list,table,table", "list,front"):
        r = c.post("/scan", files=files, data={"replay": gemini.blocked_marker("recitation"), "back_kinds": bad})
        assert r.status_code == 422 and r.json()["error"] == "bad_back_kinds", bad


def test_the_table_prompt_is_rule_10_and_the_label_prompt_is_unchanged():
    rule = VISION_PROMPT[VISION_PROMPT.index("10. THE NUTRITION TABLE"):VISION_PROMPT.index("\n11. ")].rstrip()
    assert rule in TABLE_PROMPT and "do not copy the" in TABLE_PROMPT
    assert TABLE_SCHEMA["properties"]["nutrition"] is VISION_RESPONSE_SCHEMA["properties"]["nutrition"]
    assert TABLE_PROMPT_VERSION.startswith("table-") and TABLE_PROMPT_VERSION[6:] != main.PROMPT_VERSION


def test_the_app_says_which_part_is_the_table():
    js = JS["lib.js"]
    assert 'fd.append("back_kinds", ["list", ...parts.slice(0, 2).map((_p, i) => partKinds[i] || "list")]' in js
    assert "partKinds = []" in js


def test_a_blocked_answer_is_never_read_as_a_table():                     # D-172's marker
    scan = {"model_raw": gemini.blocked_marker("recitation"), "ocr": {"back": {"reader": "cloud_vision", "text": TEXT}}}
    assert table_read.from_stored_answer(scan) is None
