"""
The review agents (D-117): Gemini drafts, the checker confirms or sends the
item to a person, and every published version records who drafted it.

The checker cases are the mistakes seen on the first supermarket run
(2026-09-27): compound ingredients split at a bracket, a garbled line that
dropped words, an Ayurvedic-medicine pack, a "Sugar Free" claim, a category
that is a judgement call. Gemini is never called: drafts are recorded answers.
"""
import base64
import json
import uuid

import pytest

from insidelabel.review import agent, checker

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from gtins import gtin  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewError, ReviewService  # noqa: E402

CATS = {"4.2.2.5", "5.2.1", "6.3", "7.1.2", "7.2.1", "7.2.2", "14.1.4.1", "15.1"}

MALIBAN_OCR = ("INGREDIENTS: REFINED WHEAT FLOUR (MAIDA), SUGAR, REFINED PALM OIL, MILK SOLIDS, WHEY, "
               "MALTODEXTRIN, IODIZED SALT, EMULSIFIER (322 (i)), RAISING AGENT (500 (ii)), ACIDITY "
               "REGULATOR (270), NATURAL & NATURE IDENTICAL FLAVOURING SUBSTANCES. CONTAINS WHEAT, SOY, "
               "MILK. NUTRITIONAL FACTS: APPROX. SERVING SIZE: 12g")
MALIBAN = {"brand": "Maliban", "name": "Wafer", "variant": "Cheese Flavour", "barcode": "8904132912625",
           "ingredients": ["REFINED WHEAT FLOUR (MAIDA)", "SUGAR", "REFINED PALM OIL", "MILK SOLIDS", "WHEY",
                           "MALTODEXTRIN", "IODIZED SALT", "EMULSIFIER (322 (i))", "RAISING AGENT (500 (ii))",
                           "ACIDITY REGULATOR (270)", "NATURAL & NATURE IDENTICAL FLAVOURING SUBSTANCES"],
           "allergen_statement": "CONTAINS WHEAT, SOY, MILK.", "front_claims": [], "category": "7.2.1",
           "category_source": "codex_descriptor", "category_reason": "Sweet biscuit.",
           "ayush_licence_seen": False, "note": "Category 7.2.1.", "changes": [], "doubts": []}
READ = {"confidence": {"ingredients": 0.98}, "ingredients_status": "read",
        "product_match": {"status": "single_image"}}


def ctx(ocr=MALIBAN_OCR, **kw):
    c = {"kind": "new_product", "ocr_text": ocr, "raw": READ, "request": {"photo_sources": {"back": "camera"}},
         "categories": CATS, "has_front": False}
    c.update(kw)
    return c


def failed(draft, context):
    return {c["check"] for c in checker.check(draft, context) if not c["ok"]}


def with_(**kw):
    d = json.loads(json.dumps(MALIBAN))
    d.update(kw)
    return d


# ---------------------------------------------------------------- the checker

def test_a_clean_biscuit_is_confirmed():
    checks = checker.check(MALIBAN, ctx())
    assert [c for c in checks if not c["ok"]] == []
    assert checker.outcome(checks) == "confirmed"


def test_a_compound_split_at_its_bracket_goes_to_a_person():
    d = with_(ingredients=MALIBAN["ingredients"][:7] + ["EMULSIFIER (322 (i)", "RAISING AGENT (500 (ii))"])
    assert "brackets_balance" in failed(d, ctx())


def test_words_dropped_from_the_list_go_to_a_person():
    # Bisk Farm TOP GOLD: the reader wrote "CONTAARTIFICIAL FOOD COLOUR (102)", losing
    # "AND ADDED ARTIFICIAL FLAVOURS (CHEESE, BUTTER)".
    ocr = ("INGREDIENTS: SUGAR, CHEESE (3%), CONTAINS ARTIFICIAL FOOD COLOUR (102) AND ADDED ARTIFICIAL "
           "FLAVOURS (CHEESE, BUTTER) NUTRITION")
    d = with_(ingredients=["SUGAR", "CHEESE (3%)", "CONTAARTIFICIAL FOOD COLOUR (102)"], allergen_statement=None)
    bad = failed(d, ctx(ocr=ocr))
    assert "nothing_lost" in bad
    detail = next(c["detail"] for c in checker.check(d, ctx(ocr=ocr)) if c["check"] == "nothing_lost")
    assert "flavours" in detail and "butter" in detail          # "added" is a panel word (item 13)


def test_a_word_cloud_vision_never_saw_goes_to_a_person():
    d = with_(ingredients=MALIBAN["ingredients"] + ["TARTRAZINE"])
    assert "ingredients_in_ocr" in failed(d, ctx())


def test_no_independent_text_means_a_person():
    assert {"independent_text", "nothing_lost"} <= failed(MALIBAN, ctx(ocr=""))


def test_an_ayurvedic_medicine_licence_goes_to_a_person():
    ocr = MALIBAN_OCR + " Ayurvedic Medicine Mfg. Lic. No. A-2755"
    assert "no_ayush_licence" in failed(MALIBAN, ctx(ocr=ocr))
    assert "no_ayush_licence" in failed(with_(ayush_licence_seen=True), ctx())


def test_a_missing_fssai_number_is_not_evidence_of_anything():
    # The Maliban pack hides it behind a QR code; nothing in the checker looks for it.
    assert "no_ayush_licence" not in failed(MALIBAN, ctx(ocr=MALIBAN_OCR.replace("FSSAI", "")))


def test_a_claim_a_rule_covers_goes_to_a_person():
    d = with_(front_claims=["Sugar Free"])
    assert "no_rule_claims" in failed(d, ctx())
    assert "no_rule_claims" not in failed(with_(front_claims=["No Maida"]), ctx())


def test_uploaded_photos_and_the_drafters_doubts_go_to_a_person():
    assert "camera_photos" in failed(MALIBAN, ctx(request={"photo_sources": {"back": "upload"}}))
    assert "no_doubts" in failed(with_(doubts=["7.2.1 or 7.2.2"]), ctx())


def test_a_weak_reading_or_a_mismatched_front_goes_to_a_person():
    assert "reading_gate" in failed(MALIBAN, ctx(raw={**READ, "confidence": {"ingredients": 0.9}}))
    assert "reading_gate" in failed(MALIBAN, ctx(raw={**READ, "ingredients_status": "partial"}))
    assert "same_pack" in failed(MALIBAN, ctx(raw={**READ, "product_match": {"status": "mismatch"}}))
    unconfirmed = ctx(raw={**READ, "product_match": {"status": "indeterminate"}}, has_front=True)
    assert "same_pack" in failed(with_(front_claims=["No Maida"]), unconfirmed)
    assert "same_pack" not in failed(MALIBAN, unconfirmed)       # no claims rest on the front


def test_other_kinds_stay_with_people():
    assert "in_scope" in failed(MALIBAN, ctx(kind="correction"))
    assert "in_scope" in failed(MALIBAN, ctx(kind="send_to_us"))


# ---------------------------------------------------------------- category

def test_the_packs_declared_category_decides():
    ocr = MALIBAN_OCR + " PEANUT BASED SPREAD (Proprietary Food - 4.2.2.5 Spread)"
    assert checker.declared_category(ocr) == "4.2.2.5"
    assert "category" not in failed(with_(category="4.2.2.5", name="Peanut Butter"), ctx(ocr=ocr))
    assert "category" in failed(with_(category="15.1", name="Peanut Butter"), ctx(ocr=ocr))


def test_the_word_table_on_the_first_runs_packs():
    rc = checker.rule_category
    assert rc("Wafer", "Cheese Flavour", ["REFINED WHEAT FLOUR (MAIDA)", "SUGAR"], "") == "7.2.1"
    assert rc("Biscoff", "CARAMELIZED COOKIE", ["Refined Wheat Flour (Maida)", "Sugar"], "") == "7.2.1"
    assert rc("Eat Fit Sugar Free", "Masala Cracker", ["REFINED WHEAT FLOUR (MAIDA) (68.3%)", "YEAST", "SALT"],
              "") == "7.1.2"
    assert rc("Mint Drops", "", ["Sugar", "Liquid Glucose"], "HARD BOILED SWEETS INGREDIENTS") == "5.2.1"
    # FSSAI 2.7.1: "sugar boiled confectionery" covers toffees too, so it says nothing
    # about hard or soft (shadow run item 16, a butter toffee).
    assert rc("Tangy Twist", "", ["Sugar", "Liquid Glucose"], "SUGAR BOILED CONFECTIONARY INGREDIENTS") is None
    assert rc("Butter Toffee", "", ["Sugar", "Liquid Glucose", "Milk Solids (4.7%)"],
              "SUGAR BOILED CONFECTIONERY") is None
    assert rc("Peanut Butter", "Chocolate Crunchy", ["Roasted Peanut (83%)"], "") == "4.2.2.5"
    assert rc("Limca", "", ["CARBONATED WATER", "SUGAR"], "") == "14.1.4.1"
    # Judgement calls get no answer, so a person decides.
    assert rc("POPZ", "CHOCOLATEY CRUNCH Multigrain MUNCHIE", ["Multigrain Flour Mix {Rice Meal (41.5%)}"], "") is None
    assert rc("dream LITE", "", ["Refined Wheat flour (Maida)", "Sugar"], "") is None
    assert rc("Cream Cracker", "", ["Wheat flour", "Sugar"], "") is None        # a sweet cracker


def test_a_category_no_rule_gives_goes_to_a_person():
    popz = with_(name="POPZ", variant="CHOCOLATEY CRUNCH Multigrain MUNCHIE", category="6.3")
    assert "category" in failed(popz, ctx())
    assert "category" in failed(with_(category="99.9"), ctx())


# ---------------------------------------------------------------- the drafter's answer

def test_parse_accepts_a_complete_answer_and_refuses_the_rest():
    assert agent.parse(json.dumps(MALIBAN))["category"] == "7.2.1"
    assert agent.parse("```json\n" + json.dumps(MALIBAN) + "\n```")["name"] == "Wafer"
    with pytest.raises(agent.DraftError):
        agent.parse("not json")
    with pytest.raises(agent.DraftError):
        agent.parse(json.dumps({k: v for k, v in MALIBAN.items() if k != "category"}))
    with pytest.raises(agent.DraftError):
        agent.parse(json.dumps(with_(ingredients="SUGAR")))


# ---------------------------------------------------------------- with the database

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes" + uuid.uuid4().bytes


def vision(ingredients):
    return json.dumps({
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Maliban", "name": "Wafer", "variant": "Cheese Flavour", "net_quantity": None,
                    "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": "CONTAINS WHEAT, SOY, MILK.",
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}})


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", "test-token-123")
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def new_item(uri, barcode=None):
    """A barcoded scan, as from the phone, whose scan row carries Cloud Vision's text."""
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", JPEG, "image/jpeg")},
                                  data={"replay": vision(MALIBAN["ingredients"]), "barcode": barcode or gtin()})
    assert r.status_code == 200, r.text
    item_id, scan_id = q(uri, "SELECT id, scan_id FROM review_queue ORDER BY id DESC LIMIT 1")[0]
    with psycopg.connect(uri) as c:
        c.execute("""UPDATE scans SET ocr = %s, request = request || '{"photo_sources": {"back": "camera"}}'
                      WHERE id = %s""", (json.dumps({"back": {"reader": "cloud_vision", "text": MALIBAN_OCR}}),
                                         scan_id))
    return item_id


def form(**kw):
    f = {"name": "Wafer", "brand": "Maliban", "variant": "Cheese Flavour", "barcode": "",
         "ingredients": "\n".join(MALIBAN["ingredients"]), "allergen_statement": "CONTAINS WHEAT, SOY, MILK.",
         "front_claims": "", "category": "7.2.1", "note": ""}
    f.update(kw)
    return f


def publish(svc, item_id, reviewer="sushil", **kw):
    assert svc.claim(item_id, reviewer)
    return svc.approve(item_id, reviewer, form(**kw))


def test_a_publish_records_who_drafted_it(env):
    svc = ReviewService(env, main.ENGINE_VERSION)
    a = publish(svc, new_item(env))
    b = publish(svc, new_item(env), drafted_by="claude", category_source="codex_descriptor")
    rows = dict((r[0], r[1:]) for r in q(env, """SELECT id, drafted_by, category_source, verified_by
                                                   FROM product_versions WHERE id = ANY(%s)""",
                                          [a["product_version_id"], b["product_version_id"]]))
    assert rows[a["product_version_id"]] == ("sushil", "reviewer", "sushil")
    assert rows[b["product_version_id"]] == ("claude", "codex_descriptor", "sushil")
    item = new_item(env)
    svc.claim(item, "sushil")
    with pytest.raises(ReviewError):
        svc.approve(item, "sushil", form(drafted_by="asha"))        # only yourself, Claude or Gemini
    with pytest.raises(ReviewError):
        svc.approve(item, "sushil", form(category_source="guess"))


def test_items_published_before_the_column_can_be_marked_once(env):
    svc = ReviewService(env, main.ENGINE_VERSION)
    item = new_item(env)
    vid = publish(svc, item)["product_version_id"]
    with psycopg.connect(env) as c:                                  # as if published before migration 015
        c.execute("UPDATE product_versions SET drafted_by = NULL WHERE id = %s", (vid,))
    open_item = new_item(env)
    assert svc.mark_drafted([item, open_item], "claude") == [item]
    assert q(env, "SELECT drafted_by FROM product_versions WHERE id = %s", vid) == [("claude",)]
    assert svc.mark_drafted([item], "claude") == []                  # never overwrites
    with pytest.raises(ReviewError):
        svc.mark_drafted([item], "sushil")


def test_a_shadow_draft_is_stored_and_publishes_nothing(env):
    svc = ReviewService(env, main.ENGINE_VERSION)
    item = new_item(env)
    seen = {}

    def call(prompt, images):
        seen["prompt"], seen["images"] = prompt, images
        return json.dumps(with_(barcode=""))

    row = agent.draft_item(svc, main.MEDIA, item, call=call)
    # Cloud Vision's text from the scan row, the reading's confidence from the version:
    # a clean draft passes every check, and in shadow that still publishes nothing.
    assert row["outcome"] == "confirmed" and row["mode"] == "shadow", row["checks"]
    assert row["model_raw"] and row["prompt_version"] and row["drafter"] == "gemini"
    assert "CLOUD VISION TEXT OF THE BACK PHOTO" in seen["prompt"] and "7.2.1 Cakes, cookies and pies" in seen["prompt"]
    assert [role for _b, _m, role in seen["images"]] == ["back"]
    assert q(env, "SELECT status FROM review_queue WHERE id = %s", item) == [("open",)]
    assert q(env, """SELECT v.status FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      WHERE q.id = %s""", item) == [("pending_review",)]
    from insidelabel.review.draft_prompt import PROMPT_VERSION
    assert item not in svc.items_to_draft(PROMPT_VERSION, limit=100)   # drafted once per prompt version
    with pytest.raises(ValueError):
        agent.draft_item(svc, main.MEDIA, item, mode="publish", call=call)


def test_an_unusable_answer_is_stored_as_an_error(env):
    svc = ReviewService(env, main.ENGINE_VERSION)
    item = new_item(env)
    row = agent.draft_item(svc, main.MEDIA, item, call=lambda p, i: "Sorry, I can't help with that.")
    assert row["outcome"] == "error" and "DraftError" in row["error"]
    assert row["model_raw"] == "Sorry, I can't help with that."


def test_the_review_page_shows_the_draft_and_fills_the_form(env):
    svc = ReviewService(env, main.ENGINE_VERSION)
    item = new_item(env)
    agent.draft_item(svc, main.MEDIA, item, call=lambda p, i: json.dumps(with_(
        note="Category from the Codex descriptor.", doubts=["Line 3 is creased."])))
    cred = base64.b64encode(b"sushil:test-token-123").decode()
    page = TestClient(main.app, headers={"Authorization": f"Basic {cred}"}).get(f"/review/item/{item}").text
    assert 'id="agent-draft"' in page and "needs a person" in page and "Line 3 is creased." in page
    assert '<option value="gemini" selected>' in page
    assert 'value="Category from the Codex descriptor."' in page


def test_the_measurement_compares_drafts_with_decisions(env):
    svc = ReviewService(env, main.ENGINE_VERSION)
    before = agent.measure(svc)
    same = new_item(env)
    agent.draft_item(svc, main.MEDIA, same, call=lambda p, i: json.dumps(MALIBAN))
    publish(svc, same)
    other = new_item(env)
    agent.draft_item(svc, main.MEDIA, other, call=lambda p, i: json.dumps(with_(category="7.2.2")))
    publish(svc, other)
    r = agent.measure(svc)
    assert r["items"] == before["items"] + 2
    ids = {d["id"] for d in r["disagreements"]}
    assert other in ids and same not in ids
    assert r["gate_passes"] is False                                  # far fewer than 30 items


# ---------------------------------------------------------------- the first shadow run (items 12 to 16)

BISCUIT = ["REFINED WHEAT FLOUR (MAIDA)", "SUGAR", "FRACTIONATED FAT", "PALMOLEIN", "INVERT SUGAR",
           "COCOA SOLIDS (2%*)", "LEAVENING AGENTS (500(ii), 503(ii))", "STARCH", "IODISED SALT",
           "EMULSIFIER (322)", "NATURE IDENTICAL FLAVOURING SUBSTANCES"]
BISCUIT_OCR = ("INGREDIENTS: REFINED WHEAT FLOUR (MAIDA), SUGAR, FRACTIONATED FAT, PALMOLEIN, INVERT SUGAR, "
               "COCOA SOLIDS (2%*), LEAVENING AGENTS (500(ii), 503(ii)), STARCH, IODISED SALT, "
               "EMULSIFIER (322), NATURE IDENTICAL FLAVOURING SUBSTANCES.")


def biscuit(**kw):
    fields = {"name": "Cream Biscuit", "variant": "", "ingredients": BISCUIT, "allergen_statement": None}
    fields.update(kw)
    return with_(**fields)


def test_a_recipe_on_the_pack_is_not_the_ingredient_list():
    # Item 12: the pack's recipe also says "ingredients", and it came first.
    ocr = ("Try Biscuit Balls! Ingredients: 10 biscuits, cream cheese. Crush the biscuits fine, "
           "make balls between your palms, dip in chocolate. " + BISCUIT_OCR)
    assert "nothing_lost" not in failed(biscuit(), ctx(ocr=ocr))
    after = BISCUIT_OCR + " Cheesecake cookies: crush a brick of biscuits fine, dip in chocolate."
    assert "nothing_lost" not in failed(biscuit(), ctx(ocr=after))


def test_a_nutrition_panel_read_into_the_list_is_not_lost_ingredients():
    # Item 13: Cloud Vision read the curved panel in among the list, words cut short.
    ocr = BISCUIT_OCR.replace("STARCH,", "STARCH, Energ 480 Satur 9 Servin 25 Total Trans 0 Recomme,")
    assert "nothing_lost" not in failed(biscuit(), ctx(ocr=ocr))


def test_item_13_as_cloud_vision_read_it():
    # The server's text for item 13 (2026-09-27): "added" and "sodium" are panel rows.
    ing = ["Refined Wheat Flour (Maida)", "Sugar", "Fractionated Vegetable Fat", "Refined Palmolein Oil",
           "Starch", "Invert Sugar Syrup", "Iodized Salt",
           "Flavours (Nature-Identical, Artificial (Vanilla) Flavouring Substances)",
           "Leavening Agents (500(ii),503(ii))", "Emulsifier (322)"]
    ocr = ("ingredients: refined wheat flour\nservin\n(maida), sugar, fractionated vegetable\n"
           "fat, refined palmolein oil, starch, invert\nsugar syrup, lodized salt, flavours\nenerg\nadded\n"
           "(nature-identical, artificial (vanilla)\nflavouring substances), leavening\ntotal\nsatur\n"
           "trans\nsodium\nrecomme\nagents (500(ii),503(ii)), emulsifier (322)")
    assert checker.independent_read(ing, ocr) == (True, [], [])


def test_a_dropped_sodium_salt_is_still_caught():
    ocr = BISCUIT_OCR[:-1] + ", SODIUM BICARBONATE."
    detail = next(c["detail"] for c in checker.check(biscuit(), ctx(ocr=ocr)) if c["check"] == "nothing_lost")
    assert "bicarbonate" in detail


def test_accents_and_net_weight():
    # Item 15: CRÈME on the draft, CREME in Cloud Vision's text; "Net Weight" after the list.
    d = biscuit(ingredients=["CHOCO CRÈME (38.0%) {SUGAR, COCOA SOLIDS}"] + BISCUIT)
    ocr = "INGREDIENTS: CHOCO CREME (38.0%) {SUGAR, COCOA SOLIDS}, " + BISCUIT_OCR[13:] + " Net Weight 120 g"
    assert "nothing_lost" not in failed(d, ctx(ocr=ocr))
    assert "ingredients_in_ocr" not in failed(d, ctx(ocr=ocr))


def test_words_dropped_at_the_end_are_still_caught():
    # The Bisk Farm garble again, with the list ending mid-sentence.
    ocr = BISCUIT_OCR[:-1] + ", CONTAINS ARTIFICIAL FOOD COLOUR (102) AND ADDED ARTIFICIAL FLAVOURS (CHEESE)."
    d = biscuit(ingredients=BISCUIT + ["CONTAARTIFICIAL FOOD COLOUR (102)"])
    detail = next(c["detail"] for c in checker.check(d, ctx(ocr=ocr)) if c["check"] == "nothing_lost")
    assert "flavours" in detail and "cheese" in detail          # "added" is a panel word (item 13)


def test_a_list_cloud_vision_did_not_read_goes_to_a_person():
    # Item 14: Gemini read words Cloud Vision never saw, and there was no list to compare.
    assert {"ingredients_in_ocr", "nothing_lost"} <= failed(biscuit(), ctx(ocr="Net Weight 100 g. Best before 6 months."))


def test_recheck_replays_the_stored_answer_for_free(env, capsys):
    import sys as _sys
    _sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[1] / "tools"))
    import review_agent
    svc = ReviewService(env, main.ENGINE_VERSION)
    item = new_item(env)
    agent.draft_item(svc, main.MEDIA, item, call=lambda p, i: json.dumps(MALIBAN))

    def no_gemini(*a, **k):
        raise AssertionError("recheck must not call Gemini")
    mp = pytest.MonkeyPatch()
    mp.setattr(agent.gemini, "call_gemini_json", no_gemini)
    try:
        review_agent.main(["--db", env, "--media", main.MEDIA.root, "recheck", str(item)])
    finally:
        mp.undo()
    assert f"item {item}: confirmed -> confirmed" in capsys.readouterr().out
    assert len(q(env, "SELECT id FROM review_drafts WHERE review_item_id = %s", item)) == 2
