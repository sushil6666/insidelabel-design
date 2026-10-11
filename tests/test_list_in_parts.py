"""
D-194 (Sushil, 2026-10-11, "Ask only when cut off"): a long ingredient list in parts, asked
for only when the read finds it cut off. A partial result and a partial refusal offer the
rest of the list as its own photo ("Photograph the rest of the list", keeping every photo in
hand) and "Retake the whole list"; the words and which choices show are the server's
(`screen.list_choices`, lenses/screen.py, D-091). At three back photos only the retake shows.
"""
import json
import os
import uuid

from fastapi.testclient import TestClient
from gtins import gtin
from test_fewer_retakes import L, _no_second_reader, env, photo, post, row, vision  # noqa: F401
from test_wording import assert_clean

from insidelabel.api import main
from insidelabel.extraction.providers import cloud_vision, gemini
from insidelabel.lenses import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
BOTH = {"add": "Photograph the rest of the list", "retake": "Retake the whole list"}
ME = json.dumps([{"ref": "me", "age": "adult", "avoid": ["peanut"]}])


def scan(raw, parts=1, **data):
    files = {"back": ("b.jpg", photo(), "image/jpeg")}
    for n in range(2, parts + 1):
        files[f"back{n}"] = (f"b{n}.jpg", photo(), "image/jpeg")
    r = TestClient(main.app).post("/scan", files=files, data={"replay": raw, **data})
    return r, r.json().get("screen") or {}


# ---------------------------------------------------------------- the server's choices

def test_a_partial_result_offers_both_choices():
    r, s = scan(vision(L, status="partial"), profiles=ME)
    assert r.status_code == 200 and s["state"] == "result", r.text
    assert s["list_choices"] == BOTH
    # Sushil, accepting: the card line is short; the buttons say the rest.
    assert s["problem"] == {"code": "partial", "label": "Part of the list is cut off",
                            "fix": "Part of the ingredient list was cut off or hard to read."}
    assert s["retake"] == screen.RETAKE_PARTIAL
    # The allergen line keeps its own words (D-188, D-072: a partial read can't confirm).
    me = next(p for p in s["people"] if p["ref"] == "me")
    assert me["status"] == "cannot_confirm"


def test_a_partial_result_with_no_profiles_still_offers_both():
    """Sushil: a shopper with no avoid list gets the same two choices."""
    r, s = scan(vision(L, status="partial"))
    assert r.status_code == 200 and s["list_choices"] == BOTH, r.text
    assert not [p for p in s["people"] if p["status"] == "cannot_confirm"]


def test_parts_already_sent_count_against_the_three():
    r, s = scan(vision(L, status="partial"), parts=2)
    assert r.status_code == 200 and s["list_choices"] == BOTH, r.text
    # Three back photos (list parts and table share them, D-119): only the retake.
    r, s = scan(vision(L, status="partial"), parts=3)
    assert r.status_code == 200 and s["list_choices"] == {"add": None, "retake": "Retake the whole list"}, r.text


def test_a_full_read_offers_neither():
    r, s = scan(vision(L))
    assert r.status_code == 200 and "list_choices" not in s and s["retake"] is None and "problem" not in s


def test_a_kind_result_read_in_part_offers_them_too():
    out = screen._kind_screen({"code": "supplement", "evidence": []}, people=[], ingredients=L,
                              reliability={"ingredients_complete": False}, parts_sent=1)
    assert out["list_choices"] == BOTH


def test_a_partial_refusal_offers_both_choices(env):
    """D-118's clearer-photo ask on a list read only in part: the rest may be past the photo's edge."""
    r = post(photo(), str(uuid.uuid4()), replay=vision(L + ["Milk solids"], status="partial"), barcode=gtin(),
             ocr="Ingredients: Wheat flour, Sugar, Palm oil, Salt, solids.")
    assert r.status_code == 422 and r.json()["reliability"]["error"] == "independent_read_failed", r.text
    s = r.json()["screen"]
    assert s["headline"]["text"] == "We couldn't read all of the ingredient list."
    assert s["problem"]["code"] == "partial" and s["problem"]["fix"] == screen.RETAKE_PARTIAL
    assert s["list_choices"] == BOTH and s["can_use_anyway"] is True


def test_a_full_read_refusal_keeps_its_words(env):
    r = post(photo(), str(uuid.uuid4()), replay=vision(L + ["Milk solids"]), barcode=gtin(),
             ocr="Ingredients: Wheat flour, Sugar, Palm oil, Salt, solids.")
    assert r.status_code == 422, r.text
    s = r.json()["screen"]
    assert s["headline"]["text"] == "One clearer photo, please." and "list_choices" not in s
    assert s["problem"]["code"] == "independent_read_failed"


def test_the_words_pass_the_wording_lint():
    for text in (screen.RETAKE_PARTIAL, screen.PARTIAL_HEADLINE, *screen.LIST_CHOICES.values()):
        assert_clean(text, "D-194")


# ---------------------------------------------------------------- D-191: an added part is a new scan

def test_an_added_part_is_not_the_same_photo(env, monkeypatch):
    back, device = photo(), str(uuid.uuid4())
    answer = vision([], status="not_found")
    first = post(back, device, replay=answer)
    assert first.status_code == 422
    calls, real = [], gemini.analyze_images

    def counted(images, raw_response=None, **kw):
        if raw_response is None:
            calls.append(len(images))
            raw_response = vision(L)
        return real(images, raw_response=raw_response, **kw)
    monkeypatch.setattr(main.gemini, "analyze_images", counted)
    files = {"back": ("b.jpg", back, "image/jpeg"), "back2": ("b2.jpg", photo(), "image/jpeg")}
    two = TestClient(main.app).post("/scan", files=files, data={"device_id": device})
    assert two.status_code == 200, two.text
    assert calls == [1]                                    # read again: the joined back is a new photo
    assert "repeat" not in two.json()["screen"]
    assert "repeat_of" not in row(env, two.json()["scan_id"])["request"]
    # The first photo alone again is still the same photo (D-191 unchanged).
    again = post(back, device)
    assert again.status_code == 422 and calls == [1] and again.json()["screen"]["repeat"]


# ---------------------------------------------------------------- the app

def _fn(name):
    f = APP[APP.index(f"function {name}("):]
    return f[:f.index("\n}\n")]


def test_the_camera_line_mentions_parts_on_the_first_photo_only():
    fn = _fn("listShot")
    assert 'more: n === 1 ? "Too long for one photo? Take it in parts, one photo each." : null,' in fn
    assert '"Fit the list, from \\"Ingredients\\" to the last word"' in fn          # the line stays
    shot = _fn("labelShot")
    # Both camera paths show it: the phone's camera app (shutter off) and the live shutter.
    assert shot.count('o.more && el("p", { class: "cam-line cam-more" }, o.more)') == 2


def test_the_rest_of_the_list_keeps_every_photo_and_sends_one_scan():
    fn = _fn("listpart")
    # Nothing in hand is dropped: no setParts, no clearing of the back, the front or the tick.
    assert "setParts" not in fn and "pending.back = null" not in fn and "pending.front = null" not in fn
    assert "pending.pairing" not in fn
    assert "if (!canAddPart()) return errorView(" in fn
    assert 'return listShot(() => go("result/" + encodeURIComponent(id)));' in fn
    assert "listpart," in APP and 'listpart: "Photo"' in APP
    # The next part joins the list before a kept table (D-173), and goes up as back2/back3 in one /scan.
    assert 'return setParts([...list.slice(0, n - 2), [b, source, "list"], ...tables]);' in APP
    assert "pending.parts.length < MAX_PHOTOS - 1" in APP
    assert 'keptList: back && n > 1 ? (n === 2 ? "We kept your first photo of the list." : "We kept your photos of the list.") : null,' in APP


def test_the_choices_come_from_the_server_once_on_the_result():
    fn = _fn("listChoices")
    assert "const c = s.list_choices;" in fn and "const add = !!c.add && canAddPart(h);" in fn
    assert 'button(c.add, () => go("listpart"), "primary")' in fn
    assert "button(c.retake, () => retakeList(h, code, keepTable)" in fn
    assert 'button("Photograph the rest' not in APP and '"Retake the whole list"' not in APP   # the server's words
    # Sushil, accepting: once, on the partial card, whatever the allergen cards show.
    assert "const cardRetake = !s.list_choices && cardPeople(s).some(" in APP
    card = _fn("personCard")
    assert "&& !h.screen.list_choices;" in card and "listChoices" not in card
    # The refusal's dock: the choices in place of its one retake button.
    assert "s.list_choices ? listChoices(s, h, s.problem?.code, s.keep_table) :" in APP


def test_the_review_screen_button_is_visible():
    review = _fn("shotReview")
    assert 'button("The list goes on: add the next part", () => show(listShot()), "secondary more-part")' in review
    assert '"The list continues"' not in APP
    # A part added after the front names the part, not the front.
    assert 'frontIn && pending.lastKind === "front" ? stepLine(4, "Front")' in review
