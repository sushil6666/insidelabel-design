"""
D-191 (Sushil, 2026-10-10, "yes D-191"): fewer retakes.

"many complain i am getting like performance issue while checking the photo as it asks
multiple time to take a new pic". Over 2026-10-03 to 10-10, 39 of 86 photo scans were
refused, and every retake costs another read of about 9 s. Four rules:

1. A "no ingredient list" refusal whose photo showed the nutrition table says so, and a
   cleanly read table is kept as the table photo, so only the list is left to take.
2. A free table hint on /check-photo (INSIDELABEL_TABLE_HINT, off until its numbers are in).
3. The same photos and choices as a refused scan of this phone in the last day get the
   same answer from the stored read: no model call, not counted, recorded for replay.
4. The cross-check (D-118) asks only when the result would change, and once per pack per phone.
"""
import io
import json
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from PIL import Image  # noqa: E402

from insidelabel import ratelimit, repro, table_hint  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision, gemini  # noqa: E402
from insidelabel.lenses import screen as result_screen  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import checker  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")

TABLE = {"status": "read", "per_100_basis": "100 g", "rda_column": False, "serving_size": None,
         "servings_per_pack": None,
         "rows": [{"nutrient": "Energy", "unit": "kcal", "per_100": 512, "per_serving": None, "rda_percent": None},
                  {"nutrient": "Protein", "unit": "g", "per_100": 7.2, "per_serving": None, "rda_percent": None}]}


def vision(ingredients, statement=None, status="read", nutrition=None):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": status,
         "product": {"brand": "Test", "name": "Masala Crunch", "variant": None, "net_quantity": None,
                     "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ingredients)] if ingredients else [],
         "ingredient_count": len(ingredients), "ingredients": ingredients, "allergen_statement": statement,
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98 if ingredients else 0.0, "front_claims": 0.0,
                        "product_identity": 0.8}}
    if nutrition is not None:
        v["nutrition"] = nutrition
    return json.dumps(v)


def photo():
    """A real, readable JPEG (photo_check passes it), different every time."""
    im = Image.frombytes("L", (900, 1200), os.urandom(900 * 1200))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=60)
    return out.getvalue()


@pytest.fixture(autouse=True)
def _no_second_reader(monkeypatch):
    """A live scan here has no Cloud Vision key: Tesseract on a noise photo would only burn CPU."""
    from insidelabel.extraction.providers import ocr_check
    real = ocr_check.start_back_read
    monkeypatch.setattr(ocr_check, "start_back_read",
                        lambda b: real(b) if cloud_vision._REPLAY is not None or cloud_vision.cached(b) else None)


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield uri
    main.STORE, main.MEDIA = saved


def row(uri, scan_id):
    with psycopg.connect(uri) as c:
        cur = c.execute("SELECT * FROM scans WHERE id = %s", (scan_id,))
        return dict(zip([d.name for d in cur.description], cur.fetchone()))


def post(back, device, replay=None, ocr=None, **form):
    data = {"device_id": device, **form}
    if replay is not None:
        data["replay"] = replay
    files = {"back": ("b.jpg", back, "image/jpeg")}
    if ocr is not None:
        with cloud_vision.replaying({cloud_vision.digest(back): ocr}):
            return TestClient(main.app).post("/scan", files=files, data=data)
    return TestClient(main.app).post("/scan", files=files, data=data)


# ---------------------------------------------------------------- 1. say what we did see

def test_a_table_only_read_says_what_was_read(env):
    r = post(photo(), str(uuid.uuid4()), replay=vision([], status="not_found", nutrition=TABLE))
    assert r.status_code == 422, r.text
    s = r.json()["screen"]
    assert s["headline"]["text"] == "We read the nutrition table, but not the ingredient list."
    assert s["problem"] == {"code": "table_only", "label": "Nutrition table, no ingredient list",
                            "fix": s["retake"]}
    assert s["retake"].startswith('The ingredient list is a separate block that starts with "Ingredients"')
    # The table wasn't confirmed by a second reading here, so it isn't kept.
    assert s["keep_table"] is False and s["retake"].endswith("Photograph that one.")
    assert s["retake_button"] == "Photograph the ingredient list"


def test_the_table_is_kept_only_when_it_was_read_cleanly():
    kw = dict(verdict=None, display=None, claim_check=None, extracted=None, profiles=[],
              allergen_confidence=0.0, allergen_reliable=False,
              reliability={"error": "no_ingredient_list_found"})
    kept = result_screen.build(**kw, table_only={"keep": True})
    assert kept["keep_table"] is True
    assert kept["retake"].endswith("Photograph that one; we'll keep this photo for the table.")
    # No table read: the D-036 words as before, nothing kept.
    plain = result_screen.build(**kw)
    assert "keep_table" not in plain and plain["retake"] == result_screen.RETAKE["no_ingredient_list_found"]
    # A recipe (D-166) keeps its own words.
    recipe = result_screen.build(**{**kw, "reliability": {"error": "no_ingredient_list_found", "reason": "recipe"}},
                                 table_only={"keep": True})
    assert recipe["retake"] == result_screen.RETAKE_RECIPE and "keep_table" not in recipe


def test_no_table_read_keeps_the_old_words(env):
    r = post(photo(), str(uuid.uuid4()), replay=vision([], status="not_found"))
    s = r.json()["screen"]
    assert s["headline"]["text"] != result_screen.TABLE_ONLY_HEADLINE and "keep_table" not in s


# ---------------------------------------------------------------- 2. the free table hint

TABLE_TEXT = "NUTRITION INFORMATION per 100 g\nEnergy 512 kcal\nProtein 7.2 g\nCarbohydrate 62 g\nTotal Fat 25 g"
LIST_TEXT = "INGREDIENTS: Wheat flour, Sugar, Palm oil, Salt, Raising agent (500(ii))"


@pytest.mark.parametrize("text, fires", [
    (TABLE_TEXT, True),                                   # the table only
    (LIST_TEXT, False),                                   # the list only
    (LIST_TEXT + "\n" + TABLE_TEXT, False),               # both: the list is in it
    ("lngredients: " + TABLE_TEXT, False),                # a misread heading still counts as the list
    ("Energy 512 kcal Protein 7 g", False),               # too few table words
    ("", False),
])
def test_the_table_hint_rule(text, fires):
    assert table_hint.looks_like_table(text)["fires"] is fires


def test_the_table_hint_is_off_by_default(monkeypatch):
    monkeypatch.delenv("INSIDELABEL_TABLE_HINT", raising=False)
    assert table_hint.enabled() is False
    monkeypatch.setenv("INSIDELABEL_TABLE_HINT", "on")
    assert table_hint.enabled() is True


def test_a_read_past_the_cap_gives_no_hint():
    got = table_hint.check(b"x", reader=lambda _b: None)
    assert got["fires"] is False and got["read"] is False


def check_photo(**form):
    return TestClient(main.app).post("/check-photo", files={"photo": ("b.jpg", photo(), "image/jpeg")},
                                     data={"role": "back", **form}).json()


def test_check_photo_asks_once_only_when_switched_on(monkeypatch):
    monkeypatch.setattr(table_hint, "read", lambda _b: TABLE_TEXT)
    monkeypatch.delenv("INSIDELABEL_TABLE_HINT", raising=False)
    assert "hint" not in check_photo(first_list="true")                      # off: nothing
    monkeypatch.setenv("INSIDELABEL_TABLE_HINT", "on")
    got = check_photo(first_list="true")
    assert got["ok"] is True and got["hint"] == {
        "text": "This looks like the nutrition table. Is the ingredient list in it?",
        "retake": "Retake", "use": "Use this photo"}
    assert "hint" not in check_photo()                                       # not the first list photo
    monkeypatch.setattr(table_hint, "read", lambda _b: LIST_TEXT)
    assert "hint" not in check_photo(first_list="true")


# ---------------------------------------------------------------- 3. same photo, same answer

def test_the_same_photo_again_gets_the_stored_answer(env, monkeypatch):
    back, device = photo(), str(uuid.uuid4())
    answer = vision([], status="not_found", nutrition=TABLE)
    first = post(back, device, replay=answer)
    assert first.status_code == 422
    calls = []
    real = gemini.analyze_images

    def counted(images, raw_response=None, **kw):
        if raw_response is None:
            calls.append(1)
            raw_response = answer
        return real(images, raw_response=raw_response, **kw)
    monkeypatch.setattr(main.gemini, "analyze_images", counted)

    again = post(back, device)
    assert again.status_code == 422 and calls == []                       # no model call
    s = again.json()["screen"]
    assert s["repeat"] == ("This is the same photo as last time, so the answer is the same. "
                           "Take a new photo of the ingredient list.")
    assert s["headline"] == first.json()["screen"]["headline"]
    # Not counted against the day's photo scans: only the first one is.
    assert len(ratelimit.LIMITER._hits[("scan", "device", device)]) == 1
    # Recorded, pointing at the original, and replayable on its own (D-092).
    rec = row(env, again.json()["scan_id"])
    assert rec["request"]["repeat_of"] == first.json()["scan_id"]
    assert rec["model_raw"] == answer and rec["error_code"] == "no_ingredient_list_found"
    out = repro.replay_scan(rec, media=main.MEDIA)
    assert out["screen"]["headline"] == s["headline"]

    # A changed choice is not the same request: it is read again.
    post(back, device, avoid="milk")
    assert calls == [1]
    # Nor is another phone's.
    post(back, str(uuid.uuid4()))
    assert calls == [1, 1]


def test_a_scan_that_gave_a_result_is_never_reused(env, monkeypatch):
    back, device = photo(), str(uuid.uuid4())
    ok = vision(["Wheat flour", "Sugar", "Salt"])
    assert post(back, device, replay=ok).status_code == 200
    calls, real = [], gemini.analyze_images

    def counted(images, raw_response=None, **kw):
        calls.append(raw_response)
        return real(images, raw_response=raw_response or ok, **kw)
    monkeypatch.setattr(main.gemini, "analyze_images", counted)
    post(back, device)
    assert calls == [None]                              # read again: only a refusal is answered from store


def test_the_app_back_button_opens_the_result_instead_of_resending():
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    fn = app[app.index("function photo() {"):app.index("// The ingredient list, or its next part")]
    assert "samePhotos(pending.answered)" in fn and 'location.replace("#/result/"' in fn
    assert "pending.answered = photosInHand();" in app
    assert 's.repeat && el("p", { class: "muted" }, s.repeat)' in app


# ---------------------------------------------------------------- 4. the cross-check asks when it matters

L = ["Wheat flour", "Sugar", "Palm oil", "Salt"]
MAGGI = ["Noodles: Wheat flour (Atta) (65%)", "Palm oil", "Iodised salt", "Wheat gluten",
         "Mixed spices (24%) (Onion powder, Coriander, Chilli powder, Turmeric, Garlic powder, Cumin, "
         "Fenugreek, Ginger, Clove, Nutmeg)", "Sugar", "Hydrolysed groundnut protein"]
MAGGI_TEXT = ("INGREDIENTS: Noodles: Wheat flour (Atta) (65%), Palm oil, Iodised salt, Wheat gluten, Mixed "
              "spices (24%) (Onion powder, Coriander, Chilli powder, Turmeric, Garlic powder, Cumin, Fenugreek, "
              "Clove, Nutmeg), Sugar, Hydrolysed groundnut protein.")
# The facts of 2026-10-03 to 10-10 (the stored rows stay on the server; tools/cross_check_replay.py
# gives the exact count there): (case, Gemini's list, statement, Cloud Vision's text, asked then, asks now).
CASES = [
    ("Maggi 8901058022216: ginger only", MAGGI, "Contains wheat, groundnut.", MAGGI_TEXT, True, False),
    ("8901058022223: 'nut' read glued as 'groundnut'", ["Edible vegetable oil (Ground Nut Oil)", "Gram flour", "Salt"],
     None, "Ingredients: Edible vegetable oil (Groundnut Oil), Gram flour, Salt.", True, False),
    ("8901928222401: a glued reader word", L + ["Contaadded flavour"], None,
     "Ingredients: Wheat flour, Sugar, Palm oil, Salt, flavour.", True, False),
    ("peas only", L + ["Green peas"], None, "Ingredients: Wheat flour, Sugar, Palm oil, Salt, green.", True, False),
    ("curved pouch, no list found, every word in the text", L, None,
     "Wheat flour, Sugar, Palm oil, Salt  Net wt 70 g", True, False),
    ("curved pouch, no list found, an allergen word not in the text", L + ["Milk solids"], None,
     "Wheat flour, Sugar, Palm oil, Salt  Net wt 70 g", True, True),
    ("8901725121228: may-contain oats and soy that Gemini dropped", L, None,
     "Ingredients: Wheat flour, Sugar, Palm oil, Salt (Made in a facility which handle wheat, oats, soy).",
     True, True),
    ("a dropped preservative number", L, None, "Ingredients: Wheat flour, Sugar, Palm oil, Salt, Preservative (211).",
     True, True),
]


@pytest.mark.parametrize("case, ingredients, statement, text, before, after", CASES, ids=[c[0] for c in CASES])
def test_the_cross_check_cases(case, ingredients, statement, text, before, after):
    matters, check = main.cross_check(ingredients, statement, text)
    assert check is not None                 # each was asked before (not confirmed word for word)
    assert matters is after, (case, check)


def test_before_and_after_count():
    after = sum(1 for c in CASES if main.cross_check(c[1], c[2], c[3])[0])
    assert (len(CASES), after) == (8, 3)


def test_a_glued_word_counts_as_seen():
    assert checker.glued_seen(["nut"], ["Ground Nut Oil"], "groundnut oil") == ["nut"]
    assert checker.glued_seen(["nut"], ["Nut paste"], "paste") == []
    # The D-117 checker stays strict: it still reports the word.
    assert checker.independent_read(["Ground Nut Oil"], "Ingredients: groundnut oil.")[1] == ["nut"]


def ask_scan(device, barcode):
    """A new pack whose Cloud Vision text lacks Gemini's "Milk solids": that matters, so it asks."""
    back = photo()
    return post(back, device, replay=vision(L + ["Milk solids"]), barcode=barcode,
                ocr="Ingredients: Wheat flour, Sugar, Palm oil, Salt, solids.")


def test_one_ask_per_pack_per_phone(env):
    device, bc = str(uuid.uuid4()), gtin()
    first = ask_scan(device, bc)
    assert first.status_code == 422 and first.json()["reliability"]["error"] == "independent_read_failed"
    # Another phone gets its own one ask.
    assert ask_scan(str(uuid.uuid4()), bc).status_code == 422
    second = ask_scan(device, bc)                       # another photo, still not confirmed
    assert second.status_code == 200, second.text
    check = row(env, second.json()["scan_id"])["ocr"]["back"]["independent_read"]
    assert check["already_asked"] == first.json()["scan_id"] and check["asked"] is False


def test_cross_check_replay_counts_once_per_pack():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cross_check_replay", os.path.join(TOOLS, "cross_check_replay.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    import datetime as dt
    t0 = dt.datetime(2026, 10, 8, 13, 0, tzinfo=dt.timezone.utc)
    rows = [{"id": i, "created_at": t0 + dt.timedelta(minutes=i), "user_id": "u1",
             "request": {"barcode": "8901058022216"}, "model_raw": '{"ingredients": ["ginger"]}',
             "ocr": {"back": {"reader": "cloud_vision", "text": "x", "independent_read": {"missing": ["milk"]}}}}
            for i in range(4)]
    out = tool.redecide(rows, lambda _i, _s, _t: (True, {"missing": ["milk"]}), lambda _r: ([], None))
    assert [r["after"] for r in out] == [True, False, False, False]
    assert out[1]["why"].startswith("already asked for this pack on this phone")
    assert out[0]["origin"] == {"milk": "not in Gemini's answer (added by D-093's recovery)"}
