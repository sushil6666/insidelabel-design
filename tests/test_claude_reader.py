"""
D-192 (Sushil, 2026-10-14, "Claude Haiku 5.5 i am planning can we try ?", then "accept"):
Claude as a second label reader behind INSIDELABEL_READER=claude, off by default.

Only the read changes: the same prompt and photos, an answer in the same shape (nullable
fields left out by Claude come back as Gemini's empty value), and everything after the
read (harden(), the cross-check, D-191, the rules) runs on it as on Gemini's. Errors map
onto Gemini's classes; a busy Claude falls back to one Gemini read, as does a HEIC photo.
No key and no network here: every Claude call is a fake client.
"""
import copy
import io
import json
import os
import random
import sys
import uuid

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from insidelabel import ratelimit, repro
from insidelabel.api import main
from insidelabel.core import engine
from insidelabel.extraction.providers import answer_shape, claude, cloud_vision, gemini
from insidelabel.extraction.providers.prompt import VISION_RESPONSE_SCHEMA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWITCHES = ("INSIDELABEL_READER", "INSIDELABEL_CLAUDE_MODEL", "INSIDELABEL_READ_SPLIT_FRONT",
            "INSIDELABEL_THINKING_LEVEL", "INSIDELABEL_MEDIA_RESOLUTION")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in SWITCHES:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    # Retries without the wait: the backoff itself is gemini.py's and tested there.
    monkeypatch.setattr(gemini.time, "sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _no_second_reader(monkeypatch):
    """A live scan here has no Cloud Vision key: Tesseract on a noise photo would only burn CPU."""
    from insidelabel.extraction.providers import ocr_check
    real = ocr_check.start_back_read
    monkeypatch.setattr(ocr_check, "start_back_read",
                        lambda b: real(b) if cloud_vision._REPLAY is not None or cloud_vision.cached(b) else None)


def gemini_answer(ingredients=("Wheat flour", "Sugar", "Salt"), statement=None):
    """A full Gemini answer: every field present, nulls where nothing is printed."""
    return {
        "image_content": {"back": "food_pack", "front": "not_provided"},
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product_match": {"status": "single_image", "evidence": []},
        "front_identity": {"brand": None, "name": None, "manufacturer": None},
        "back_identity": {"brand": "Test", "name": "Masala Crunch", "manufacturer": None, "fssai_licence": None},
        "product": {"brand": "Test", "name": "Masala Crunch", "variant": None, "net_quantity": "90 g",
                    "veg_mark": "veg"},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": list(ingredients), "allergen_statement": statement,
        "front_claims": [], "front_claim_footnotes": [],
        "nutrition": {"status": "read", "per_100_basis": "100 g", "rda_column": None, "serving_size": None,
                      "servings_per_pack": None,
                      "rows": [{"nutrient": "Energy", "unit": "kcal", "per_100": "512", "per_serving": None,
                                "rda_percent": None}]},
        "composition": {"status": "not_found", "basis": None, "rows": []},
        "pack_statements": [], "licences": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8},
    }


def left_out(answer, schema=VISION_RESPONSE_SCHEMA):
    """The same answer as Claude gives it: every nullable field with nothing in it left out."""
    if isinstance(answer, dict):
        props = schema.get("properties") or {}
        return {k: left_out(v, props.get(k) or {}) for k, v in answer.items()
                if not ((props.get(k) or {}).get("nullable") and v is None)}
    if isinstance(answer, list):
        return [left_out(x, schema.get("items") or {}) for x in answer]
    return answer


# ---------------------------------------------------------------- a fake Claude

class Msg:
    def __init__(self, text, stop="end_turn", usage=(9000, 1100), category=None):
        self.content = [type("Block", (), {"type": "text", "text": text})()] if text is not None else []
        self.stop_reason = stop
        self.stop_details = type("D", (), {"category": category})() if stop == "refusal" else None
        self.usage = type("U", (), {"input_tokens": usage[0], "output_tokens": usage[1]})()


class FakeClaude:
    """Stands in for anthropic.Anthropic(): returns (or raises) each queued item in turn."""

    def __init__(self, *items):
        self.items, self.requests = list(items), []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return item if isinstance(item, Msg) else Msg(item)


@pytest.fixture
def fake_claude(monkeypatch):
    def install(*items):
        fake = FakeClaude(*items)
        monkeypatch.setattr(claude, "_client", lambda _key: fake)
        return fake
    return install


class FakeGemini:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def __call__(self, images, api_key=None, usage=None, settings=None):
        self.calls += 1
        if usage is not None:
            usage.update({"input_tokens": 6000, "output_tokens": 1100, "thinking_tokens": 40, "total_tokens": 7140,
                          "model": gemini.MODEL, "thinking_level": "low", "media_resolution": None, "ms": 5})
        return self.text


@pytest.fixture
def fake_gemini(monkeypatch):
    def install(text):
        fake = FakeGemini(text)
        monkeypatch.setattr(gemini, "_HAVE_SDK", True)
        monkeypatch.setattr(gemini, "call_gemini_sdk", fake)
        return fake
    return install


def status_error(cls, status):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=req), body=None)


def timeout_error():
    return anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))


def photo(seed=1, size=(900, 1200)):
    im = Image.frombytes("L", size, random.Random(seed).randbytes(size[0] * size[1]))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=60)
    return out.getvalue()


BACK = photo(1)


# ---------------------------------------------------------------- 1. the switch

@pytest.mark.parametrize("value, want", [
    (None, "gemini"), ("gemini", "gemini"), ("claude", "claude"), (" Claude ", "claude"),
    ("CLAUDE", "claude"), ("haiku", "gemini"), ("", "gemini"), ("claude,gemini", "gemini"),
])
def test_reader_selection(monkeypatch, value, want):
    if value is not None:
        monkeypatch.setenv("INSIDELABEL_READER", value)
    assert gemini.reader() == want
    assert gemini.read_settings()["reader"] == want


def test_off_by_default_reads_as_today():
    assert gemini.read_settings() == {"reader": "gemini", "model": "gemini-3.6-flash", "thinking_level": "low",
                                      "media_resolution": None, "split_front": False}
    assert main.PROMPT_VERSION == "01696584efa3"                    # the prompt is unchanged


def test_claude_settings_name_only_what_applies(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    for k, v in (("INSIDELABEL_THINKING_LEVEL", "minimal"), ("INSIDELABEL_MEDIA_RESOLUTION", "low"),
                 ("INSIDELABEL_READ_SPLIT_FRONT", "on")):
        monkeypatch.setenv(k, v)
    # D-193's three switches are Gemini's: recorded as not applied, the split off.
    assert gemini.read_settings() == {"reader": "claude", "model": "claude-haiku-5-5", "thinking_level": None,
                                      "media_resolution": None, "split_front": False}
    monkeypatch.setenv("INSIDELABEL_CLAUDE_MODEL", "claude-haiku-6")
    assert gemini.read_settings()["model"] == "claude-haiku-6" == claude.model()


# ---------------------------------------------------------------- 2. the answer's shape

def _objects(schema, path="$"):
    """Every object schema in the tree, with its path."""
    if str(schema.get("type", "")).lower() == "object":
        yield path, schema
        for k, sub in (schema.get("properties") or {}).items():
            yield from _objects(sub, f"{path}.{k}")
    if "items" in schema:
        yield from _objects(schema["items"], f"{path}[]")


def test_the_converter_keeps_every_field_of_the_real_schema():
    converted = dict(_objects(answer_shape.to_claude_schema(VISION_RESPONSE_SCHEMA)))
    original = dict(_objects(VISION_RESPONSE_SCHEMA))
    assert converted.keys() == original.keys() and len(original) == 13
    for path, g in original.items():
        c = converted[path]
        assert c["properties"].keys() == g["properties"].keys(), path          # every field present
        assert c["additionalProperties"] is False, path
        nullable = {k for k, v in g["properties"].items() if v.get("nullable")}
        # Required kept; a nullable field becomes "leave it out", never dropped.
        assert set(c["required"]) == set(g.get("required", [])) - nullable, path
        for k, v in g["properties"].items():
            cv = c["properties"][k]
            assert "nullable" not in cv and "propertyOrdering" not in cv
            assert cv.get("type") == str(v.get("type")).lower()
            assert cv.get("enum") == v.get("enum") and cv.get("description") == v.get("description")
    assert "propertyOrdering" not in json.dumps(answer_shape.to_claude_schema())


def test_the_converted_schema_is_within_claudes_limits():
    # A new nullable field past these fails here, not as a 400 on a scan.
    optional, union = answer_shape.limits(claude.CLAUDE_SCHEMA)
    assert optional <= answer_shape.MAX_OPTIONAL == 24 and union <= answer_shape.MAX_UNION == 16
    assert optional == 23 and union == 0


def test_the_request_is_the_same_prompt_and_photos_with_thinking_off():
    front = photo(2)
    req = claude.build_request([(BACK, "image/jpeg", "back"), (front, "image/png", "front")])
    assert req["model"] == "claude-haiku-5-5" and req["thinking"] == {"type": "disabled"}
    assert req["output_config"]["format"] == {"type": "json_schema", "schema": claude.CLAUDE_SCHEMA}
    content = req["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": gemini.VISION_PROMPT}
    assert [b["source"]["media_type"] for b in content[1:]] == ["image/jpeg", "image/png"]
    import base64
    assert base64.b64decode(content[1]["source"]["data"]) == BACK                 # sent as it is
    assert "temperature" not in req and "system" not in req


def test_fill_back_makes_claudes_answer_gemini_s_field_by_field():
    full = gemini_answer()
    claude_text = json.dumps(left_out(full))
    assert "fssai_licence" not in claude_text and "allergen_statement" not in claude_text
    got = gemini.parse_vision_json(claude_text)
    # Each left-out field back with exactly Gemini's empty value for it.
    assert got == full
    assert got["back_identity"]["fssai_licence"] is None and got["nutrition"]["rows"][0]["rda_percent"] is None


def test_fill_back_gives_the_schemas_own_empty_value():
    schema = {"type": "object", "properties": {
        "a": {"type": "string", "nullable": True}, "b": {"type": "array", "nullable": True, "items": {"type": "string"}},
        "c": {"type": "array", "items": {"type": "string"}}},
        "required": ["a", "b", "c"]}
    assert answer_shape.fill_back({"c": []}, schema) == {"a": None, "b": None, "c": []}
    assert answer_shape._empty({"type": "array"}) == [] and answer_shape._empty({"type": "string"}) == ""


def test_fill_back_leaves_a_gemini_answer_unchanged():
    full = gemini_answer()
    assert answer_shape.fill_back(copy.deepcopy(full)) == full
    # An old recorded answer missing a required field stays as it was (D-092 replays).
    old = gemini_answer()
    del old["pack_statements"], old["nutrition"]
    assert answer_shape.fill_back(copy.deepcopy(old)) == old


def test_fill_back_puts_enum_values_in_the_schemas_spelling():
    full = gemini_answer()
    shouting = json.loads(json.dumps(left_out(full)))
    shouting["ingredients_status"], shouting["product"]["veg_mark"] = "READ", "Veg"
    shouting["image_content"]["front"] = "Not_Provided"
    assert gemini.parse_vision_json(json.dumps(shouting)) == full


def test_every_saved_answer_in_the_repo_parses_as_before():
    """Every model answer kept in the repo (fixtures, gold, predictions) is unchanged by the fill-back."""
    seen = 0
    for base in ("tests", "predictions_archive", "gold"):
        for dirpath, _d, files in os.walk(os.path.join(ROOT, base)):
            for name in files:
                if not name.endswith(".json"):
                    continue
                try:
                    data = json.load(open(os.path.join(dirpath, name), encoding="utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                for raw in _raw_answers(data):
                    try:
                        obj = json.loads(gemini._FENCE.sub("", raw).strip())
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and "ingredients" in obj:
                        seen += 1
                        assert answer_shape.fill_back(copy.deepcopy(obj)) == obj, name
    assert seen > 0


def _raw_answers(data):
    if isinstance(data, dict):
        if "ingredients_status" in data:
            yield json.dumps(data)                                  # an answer stored as JSON itself
        for k, v in data.items():
            if k in ("model_raw", "replay", "model_raw_front") and isinstance(v, str):
                yield v
            else:
                yield from _raw_answers(v)
    elif isinstance(data, list):
        for x in data:
            yield from _raw_answers(x)


# ---------------------------------------------------------------- 3. same answer, same result

@pytest.mark.parametrize("ingredients, avoid", [
    (("Wheat flour", "Sugar", "Salt", "Acidity regulator (INS 330)"), None),
    (("Wheat flour", "Milk solids", "Sugar"), ["milk"]),
])
def test_a_claude_answer_gives_the_same_result_as_gemini_s(monkeypatch, fake_claude, fake_gemini,
                                                         ingredients, avoid):
    full = gemini_answer(ingredients, statement="Contains milk." if avoid else None)
    images = [(BACK, "image/jpeg", "back")]
    fake_gemini(json.dumps(full))
    g, g_corr = gemini.analyze_images(images)
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake_claude(json.dumps(left_out(full)))
    c, c_corr = gemini.analyze_images(images)
    assert c["_read"] == {"reader": "claude"} and g["_read"] == {"reader": "gemini"}
    assert c["_model"] == "claude-haiku-5-5" and g["_model"] == gemini.MODEL
    private = ("_model", "_raw_text", "_usage", "_read")
    assert {k: v for k, v in c.items() if k not in private} == {k: v for k, v in g.items() if k not in private}
    assert c_corr == g_corr
    assert engine.analyze(", ".join(c["ingredients"])) == engine.analyze(", ".join(g["ingredients"]))


def scan(**form):
    return TestClient(main.app).post("/scan", files={"back": ("b.jpg", BACK, "image/jpeg")}, data=form)


def _same(r):
    j = r.json()
    j.pop("scan_id", None)
    return j


def test_scan_gives_the_same_screen_with_either_reader(monkeypatch, fake_claude, fake_gemini):
    full = gemini_answer(("Wheat flour", "Milk solids", "Sugar"), statement="Contains milk.")
    fake_gemini(json.dumps(full))
    g = scan(avoid="milk")
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake_claude(json.dumps(left_out(full)))
    c = scan(avoid="milk")
    assert g.status_code == c.status_code == 200
    assert _same(c) == _same(g)
    assert list(c.json())[0] == "allergens"                           # D-060: still the first key


# ---------------------------------------------------------------- 4. errors

@pytest.mark.parametrize("error, cls", [
    (status_error(anthropic.RateLimitError, 429), gemini.VisionUnavailable),
    (status_error(anthropic.OverloadedError, 529), gemini.VisionUnavailable),
    (status_error(anthropic.InternalServerError, 500), gemini.VisionUnavailable),
    (status_error(anthropic.ServiceUnavailableError, 503), gemini.VisionUnavailable),
    (timeout_error(), gemini.VisionUnavailable),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")),
     gemini.VisionUnavailable),
    (status_error(anthropic.AuthenticationError, 401), gemini.VisionConfigError),
    (status_error(anthropic.PermissionDeniedError, 403), gemini.VisionConfigError),
    (status_error(anthropic.BadRequestError, 400), gemini.VisionConfigError),
    (status_error(anthropic.NotFoundError, 404), gemini.VisionConfigError),
])
def test_error_mapping(fake_claude, error, cls):
    fake_claude(error)
    with pytest.raises(gemini.VisionError) as got:
        claude.call_claude([(BACK, "image/jpeg", "back")])
    assert type(got.value) is cls
    if cls is gemini.VisionConfigError:
        assert got.value.status == error.status_code


def test_a_refusal_is_a_blocked_answer(fake_claude):
    fake_claude(Msg(None, stop="refusal", category="general_harms"))
    with pytest.raises(gemini.VisionBlocked) as got:
        claude.call_claude([(BACK, "image/jpeg", "back")])
    assert got.value.reason == "refusal"
    assert gemini.blocked_reason(gemini.blocked_marker(got.value.reason)) == "refusal"


def test_a_cut_off_answer_fails_to_parse_and_keeps_its_text(monkeypatch, fake_claude):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    cut = json.dumps(gemini_answer())[:300]
    fake_claude(Msg(cut, stop="max_tokens"))
    with pytest.raises(gemini.VisionError) as got:
        gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert type(got.value) is gemini.VisionError and got.value.raw_text == cut


def test_usage_is_recorded_with_the_same_keys(fake_claude):
    fake_claude(Msg(json.dumps(gemini_answer()), usage=(9100, 1050)))
    usage = {}
    claude.call_claude([(BACK, "image/jpeg", "back")], usage=usage)
    assert set(gemini.USAGE_KEYS) <= set(usage)
    assert usage["input_tokens"] == 9100 and usage["output_tokens"] == 1050 and usage["total_tokens"] == 10150
    assert usage["thinking_tokens"] is None and usage["model"] == "claude-haiku-5-5" and usage["ms"] >= 0


def test_no_key_with_the_switch_on_is_a_setup_problem(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(gemini.VisionConfigError, match="ANTHROPIC_API_KEY"):
        claude.call_claude([(BACK, "image/jpeg", "back")])
    r = scan()                                       # no Gemini key either: nothing to fall back to
    assert r.status_code == 503 and r.json()["error"] == "vision_not_configured"


# ---------------------------------------------------------------- 5. the fallback

def test_busy_claude_falls_back_to_one_gemini_read(monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake = fake_claude(status_error(anthropic.OverloadedError, 529))
    g = fake_gemini(json.dumps(gemini_answer()))
    v, _c = gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert len(fake.requests) == gemini.MAX_ATTEMPTS and g.calls == 1         # Claude's retries, then one read
    assert v["_read"] == {"reader": "gemini", "fallback": "gemini", "fallback_why": "unavailable"}
    assert v["_usage"]["model"] == gemini.MODEL and v["_model"] == gemini.MODEL


def test_no_fallback_without_a_gemini_key(monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    monkeypatch.delenv("GEMINI_API_KEY")
    fake_claude(status_error(anthropic.OverloadedError, 529))
    g = fake_gemini(json.dumps(gemini_answer()))
    with pytest.raises(gemini.VisionUnavailable) as got:
        gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert g.calls == 0 and got.value.read == {"reader": "claude"}


def test_a_refusal_never_falls_back(monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake = fake_claude(Msg(None, stop="refusal"))
    g = fake_gemini(json.dumps(gemini_answer()))
    with pytest.raises(gemini.VisionBlocked):
        gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert g.calls == 0 and len(fake.requests) == 1                          # not retried either


@pytest.mark.parametrize("error", [
    status_error(anthropic.BadRequestError, 400),                            # credit balance too low
    status_error(anthropic.AuthenticationError, 401),
    status_error(anthropic.PermissionDeniedError, 403),
    status_error(anthropic.NotFoundError, 404),
])
def test_a_setup_problem_falls_back_to_one_gemini_read(monkeypatch, fake_claude, fake_gemini, error):
    # The Anthropic credit is prepaid: when it runs out, shoppers still get a result.
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake = fake_claude(error)
    g = fake_gemini(json.dumps(gemini_answer()))
    v, _c = gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert len(fake.requests) == 1 and g.calls == 1                          # never retried, read once
    assert v["_read"]["reader"] == "gemini" and v["_read"]["fallback_why"] == "setup"
    assert v["_read"]["setup_status"] == error.status_code
    assert v["_usage"]["model"] == gemini.MODEL


def test_no_claude_key_falls_back_too(monkeypatch, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    g = fake_gemini(json.dumps(gemini_answer()))
    v, _c = gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert g.calls == 1 and v["_read"]["fallback_why"] == "setup" and v["_read"]["setup_status"] == "no_key"


def test_a_setup_problem_without_a_gemini_key_still_fails(monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    monkeypatch.delenv("GEMINI_API_KEY")
    fake_claude(status_error(anthropic.BadRequestError, 400))
    g = fake_gemini(json.dumps(gemini_answer()))
    with pytest.raises(gemini.VisionConfigError) as got:
        gemini.analyze_images([(BACK, "image/jpeg", "back")])
    assert g.calls == 0 and got.value.status == 400


def test_a_heic_photo_is_read_by_gemini(monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake = fake_claude(json.dumps(gemini_answer()))
    g = fake_gemini(json.dumps(gemini_answer()))
    v, _c = gemini.analyze_images([(b"heic bytes", "image/heic", "back")])
    assert fake.requests == [] and g.calls == 1
    assert v["_read"] == {"reader": "gemini", "fallback": "gemini", "fallback_why": "heic"}


def test_split_front_is_ignored_on_claude(monkeypatch, fake_claude):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    fake = fake_claude(json.dumps(gemini_answer()))
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", BACK, "image/jpeg"),
                                                  "front": ("f.jpg", photo(2), "image/jpeg")},
                                  data={"pairing_confirmed": "true"})
    assert r.status_code == 200
    assert len(fake.requests) == 1                                         # one call, back and front together
    assert len(fake.requests[0]["messages"][0]["content"]) == 3


# ---------------------------------------------------------------- 6. photos

def test_a_photo_within_claudes_limits_goes_as_it_is():
    assert claude._photo(BACK, "image/jpeg") == (BACK, "image/jpeg")
    png = io.BytesIO()
    Image.new("RGB", (1600, 1200), "white").save(png, "PNG")
    assert claude._photo(png.getvalue(), "image/png") == (png.getvalue(), "image/png")


def test_a_photo_past_claudes_limits_is_shrunk(monkeypatch):
    wide = io.BytesIO()
    Image.new("RGB", (8100, 300), "white").save(wide, "PNG")
    data, mime = claude._photo(wide.getvalue(), "image/png")
    assert mime == "image/jpeg" and max(Image.open(io.BytesIO(data)).size) == claude.LONG_EDGE
    monkeypatch.setattr(claude, "MAX_PHOTO_BYTES", 1000)                    # past the size limit
    data, mime = claude._photo(BACK, "image/jpeg")
    assert data is not BACK and mime == "image/jpeg"
    assert Image.open(io.BytesIO(data)).size == (900, 1200)                 # already under the long edge


def test_cloud_vision_still_shrinks_as_before():
    assert cloud_vision.shrink(BACK) is BACK
    big = b"x" * (cloud_vision.MAX_SEND_BYTES + 1)
    assert cloud_vision.shrink(big) is big                                  # undecodable: sent as it is


# ---------------------------------------------------------------- 7. stored with the scan

psycopg = pytest.importorskip("psycopg")


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    from insidelabel.db.store import Store
    from insidelabel.media import LocalMedia
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


def test_a_claude_scan_stores_its_reader_and_tokens(env, monkeypatch, fake_claude):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    full = gemini_answer()
    fake_claude(Msg(json.dumps(left_out(full)), usage=(9100, 1050)))
    r = scan(device_id=str(uuid.uuid4()))
    rec = row(env, r.json()["scan_id"])
    t = rec["timings"]
    assert t["read"] == {"reader": "claude", "model": "claude-haiku-5-5", "thinking_level": None,
                         "media_resolution": None, "split_front": False}
    assert t["claude"]["input_tokens"] == 9100 and "gemini" not in t
    assert rec["model_raw"] == json.dumps(left_out(full))                  # the raw answer, as given (D-092)
    # Its stored answer replays with no reader to the same screen as Gemini's full answer.
    out, as_gemini = scan(replay=rec["model_raw"]), scan(replay=json.dumps(full))
    assert _same(out) == _same(as_gemini) and out.json()["screen"] == r.json()["screen"]


def test_a_gemini_scan_stores_as_it_always_has(env, fake_gemini):
    fake_gemini(json.dumps(gemini_answer()))
    r = scan(device_id=str(uuid.uuid4()))
    t = row(env, r.json()["scan_id"])["timings"]
    assert t["read"]["reader"] == "gemini" and t["gemini"]["input_tokens"] == 6000 and "claude" not in t


def test_a_fallback_is_one_read_counted_once(env, monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake_claude(status_error(anthropic.OverloadedError, 529))
    fake_gemini(json.dumps(gemini_answer()))
    device = str(uuid.uuid4())
    r = scan(device_id=device)
    assert r.status_code == 200
    t = row(env, r.json()["scan_id"])["timings"]
    assert t["read"]["reader"] == "claude"                                   # what was switched on
    assert t["read"]["fallback"] == "gemini" and t["read"]["fallback_why"] == "unavailable"
    # One read on the trail: Gemini's tokens only, and one hit on the day's limit.
    assert "claude" not in t and t["gemini"]["model"] == gemini.MODEL
    assert len(ratelimit.LIMITER._hits[("scan", "device", device)]) == 1
    assert repro.read_lines(t)[0] == ("read claude-haiku-5-5 · reader claude · "
                                      "gemini read it instead (unavailable)")


def test_out_of_claude_credit_is_a_result_counted_once_with_an_alarm(env, monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_claude(anthropic.BadRequestError("Your credit balance is too low to access the Anthropic API.",
                                          response=httpx2.Response(400, request=req), body=None))
    fake_gemini(json.dumps(gemini_answer()))
    with psycopg.connect(env) as c:
        c.execute("DELETE FROM problem_reports WHERE signature = 'claude_config:400'")
    device = str(uuid.uuid4())
    r = scan(device_id=device)
    assert r.status_code == 200 and list(r.json())[0] == "allergens"
    t = row(env, r.json()["scan_id"])["timings"]
    assert t["read"]["reader"] == "claude"                                   # what was switched on
    assert t["read"]["fallback"] == "gemini" and t["read"]["fallback_why"] == "setup"
    assert t["read"]["setup_status"] == 400
    assert "claude" not in t and t["gemini"]["model"] == gemini.MODEL
    assert len(ratelimit.LIMITER._hits[("scan", "device", device)]) == 1
    with psycopg.connect(env) as c:
        rep = c.execute("SELECT kind, server_error FROM problem_reports "
                        "WHERE signature = 'claude_config:400'").fetchall()
    assert len(rep) == 1 and rep[0][0] == "server" and "credit balance is too low" in rep[0][1]


def test_a_heic_scan_records_why(env, monkeypatch, fake_claude, fake_gemini):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake_claude(json.dumps(gemini_answer()))
    fake_gemini(json.dumps(gemini_answer()))
    device = str(uuid.uuid4())
    r = TestClient(main.app).post("/scan", files={"back": ("b.heic", b"\x00\x00\x00\x18ftypheic" + BACK, "image/heic")},
                                  data={"device_id": device})
    assert r.status_code == 200
    t = row(env, r.json()["scan_id"])["timings"]
    assert t["read"]["fallback"] == "gemini" and t["read"]["fallback_why"] == "heic"
    assert len(ratelimit.LIMITER._hits[("scan", "device", device)]) == 1


def test_a_failed_fallback_records_it_too(env, monkeypatch, fake_claude):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake_claude(status_error(anthropic.OverloadedError, 529))

    def busy(*_a, **_k):
        raise gemini.VisionUnavailable("Gemini busy too")
    monkeypatch.setattr(gemini, "_HAVE_SDK", True)
    monkeypatch.setattr(gemini, "call_gemini_sdk", busy)
    device = str(uuid.uuid4())
    r = scan(device_id=device)
    assert r.status_code == 503 and r.json()["error"] == "vision_unavailable"
    with psycopg.connect(env) as c:
        t = c.execute("SELECT timings FROM scans WHERE user_id = %s", (device,)).fetchone()[0]
    assert t["read"]["fallback"] == "gemini" and t["read"]["fallback_why"] == "unavailable"


def test_a_claude_refusal_is_the_refusal_screen(env, monkeypatch, fake_claude):
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake_claude(Msg(None, stop="refusal"))
    r = scan(device_id=str(uuid.uuid4()))
    assert r.status_code == 422 and r.json()["reliability"]["error"] == "vision_blocked"
    rec = row(env, r.json()["scan_id"])
    assert rec["error_code"] == "vision_blocked:refusal" and gemini.blocked_reason(rec["model_raw"]) == "refusal"


def test_a_stored_read_is_reused_whichever_reader_made_it(env, monkeypatch, fake_claude):
    """D-191: a refused Gemini scan's photos again, now with Claude switched on: no read at all."""
    device = str(uuid.uuid4())
    refused = gemini_answer(())
    refused.update(ingredients_status="not_found", ingredient_lines=[], ingredient_count=0)
    first = scan(device_id=device, replay=json.dumps(refused))
    assert first.status_code == 422
    monkeypatch.setenv("INSIDELABEL_READER", "claude")
    fake = fake_claude(json.dumps(gemini_answer()))
    again = scan(device_id=device)
    assert again.status_code == 422 and fake.requests == []
    rec = row(env, again.json()["scan_id"])
    assert rec["request"]["repeat_of"] == first.json()["scan_id"]
    assert rec["timings"]["read"]["reader"] == "gemini"                     # whose answer it is


# ---------------------------------------------------------------- 8. tools

def _batch_scan():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import batch_scan
    finally:
        sys.path.pop(0)
    return batch_scan


def test_batch_scan_reader_flag(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READER", "")                 # so the test leaves it as it found it
    bs = _batch_scan()
    assert bs.parse_args([]).reader is None
    args = bs.parse_args(["--reader", "claude"])
    bs.apply_args(args)
    assert os.environ["INSIDELABEL_READER"] == "claude" and gemini.read_settings()["reader"] == "claude"
    assert bs.parse_args(["--reader", "gemini"]).reader == "gemini"
    for bad in (["--reader", "haiku"], ["--reader", "claude", "--split-front"],
                ["--reader", "claude", "--thinking-level", "minimal"]):
        with pytest.raises(SystemExit):
            bs.parse_args(bad)
    assert bs.parse_args(["--reader", "gemini", "--split-front"]).split_front is True
    assert bs.RATES["claude"] == (0.10, 0.50) and bs.RATES["gemini"] == (0.75, 3.75)


def test_repro_prints_the_reader():
    lines = repro.read_lines({"read": {"reader": "claude", "model": "claude-haiku-5-5", "thinking_level": None,
                                       "media_resolution": None, "split_front": False},
                              "claude": {"input_tokens": 9100, "output_tokens": 1050, "thinking_tokens": None,
                                         "ms": 3200}})
    assert lines == ["read claude-haiku-5-5 · reader claude",
                     "tokens label (claude): in 9100 · out 1050 · thinking None · 3200 ms"]
    lines = repro.read_lines({"read": {"reader": "gemini", "model": "gemini-3.6-flash", "thinking_level": "low",
                                       "media_resolution": None, "split_front": False}})
    assert lines == ["read gemini-3.6-flash · reader gemini · thinking low · media default · split off"]
    lines = repro.read_lines({"read": {"reader": "claude", "model": "claude-haiku-5-5", "fallback": "gemini",
                                       "fallback_why": "setup", "setup_status": 400}})
    assert lines == ["read claude-haiku-5-5 · reader claude · gemini read it instead (setup 400)"]


def test_the_review_agent_and_table_read_stay_on_gemini():
    for path in ("src/insidelabel/review/agent.py", "src/insidelabel/review/table_read.py"):
        text = open(os.path.join(ROOT, path), encoding="utf-8").read()
        assert "claude" not in text.lower() and "_read_text" not in text, path
