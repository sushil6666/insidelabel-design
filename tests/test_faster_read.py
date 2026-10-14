"""
D-193 (Sushil, 2026-10-10, "yes D-193"): a faster read, measured first.

Photo scans took 8.9 s at the median over 2026-10-03 to 10-10, and Gemini's call was 97 %
of it. Every setting that could make it faster is a switch, off by default, until the
advisor's gold-set run shows one faster with no loss in reading:
  INSIDELABEL_READ_SPLIT_FRONT=on     the back and the front in two calls at once
  INSIDELABEL_THINKING_LEVEL=minimal  (Google lists minimal, low, medium, high for 3.6 Flash)
  INSIDELABEL_MEDIA_RESOLUTION=low    (or medium, high)
And every Gemini call keeps its own token counts (no shared global), stored with the scan.
No key here: every call is a fake.
"""
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
import uuid

import pytest

from fastapi.testclient import TestClient
from PIL import Image

from insidelabel import repro
from insidelabel.api import main
from insidelabel.extraction.providers import cloud_vision, gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWITCHES = ("INSIDELABEL_READ_SPLIT_FRONT", "INSIDELABEL_THINKING_LEVEL", "INSIDELABEL_MEDIA_RESOLUTION")


@pytest.fixture(autouse=True)
def _no_second_reader(monkeypatch):
    """A live scan here has no Cloud Vision key: Tesseract on a noise photo would only burn CPU."""
    from insidelabel.extraction.providers import ocr_check
    real = ocr_check.start_back_read
    monkeypatch.setattr(ocr_check, "start_back_read",
                        lambda b: real(b) if cloud_vision._REPLAY is not None or cloud_vision.cached(b) else None)


@pytest.fixture(autouse=True)
def _switches_off(monkeypatch):
    for k in SWITCHES:
        monkeypatch.delenv(k, raising=False)


def answer(ingredients=("Wheat flour", "Sugar", "Salt"), front=False, brand="Test", claims=(), statements=()):
    """One call's answer: the back's (front=False) or the front's alone."""
    return json.dumps({
        "image_content": {"back": "not_provided" if front else "food_pack", "front": "food_pack" if front else "not_provided"},
        "front_status": "read" if front else "not_provided", "back_status": "not_provided" if front else "read",
        "ingredients_status": "not_found" if front else "read",
        "product": {"brand": brand, "name": "Masala Crunch" if front else None, "variant": "Masala" if front else None,
                    "net_quantity": "90 g" if not front else None, "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []},
        "front_identity": {"brand": brand, "name": "Masala Crunch", "manufacturer": None} if front else None,
        "back_identity": None if front else {"brand": brand, "name": "Masala Crunch", "manufacturer": None,
                                             "fssai_licence": "10012345000123"},
        "ingredient_lines": [] if front else [", ".join(ingredients)],
        "ingredient_count": 0 if front else len(ingredients), "ingredients": [] if front else list(ingredients),
        "allergen_statement": None, "front_claims": list(claims), "front_claim_footnotes": [],
        "pack_statements": [{"text": t, "face": "front" if front else "back"} for t in statements],
        "extraction_notes": [],
        "confidence": {"ingredients": 0.0 if front else 0.98, "front_claims": 0.9 if front else 0.0,
                       "product_identity": 0.8}})


def photo(seed):
    im = Image.frombytes("L", (900, 1200), random.Random(seed).randbytes(900 * 1200))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=60)
    return out.getvalue()


BACK, FRONT = photo(1), photo(2)


class FakeSdk:
    """Stands in for call_gemini_sdk: an answer per role, a delay per role, its own usage."""

    def __init__(self, back=None, front=None, front_delay=0.0, front_error=None):
        self.back, self.front = back or answer(), front or answer(front=True, claims=["No added MSG"])
        self.front_delay, self.front_error, self.calls = front_delay, front_error, []

    def __call__(self, images, api_key=None, usage=None, settings=None):
        roles = [r for _d, _m, r in images]
        self.calls.append(roles)
        only_front = roles == ["front"]
        if only_front:
            time.sleep(self.front_delay)
            if self.front_error:
                raise self.front_error
        if usage is not None:
            usage.update({"input_tokens": 1000 * len(images), "output_tokens": 50 if only_front else 400,
                          "thinking_tokens": 7, "total_tokens": 1500, "model": gemini.MODEL,
                          "thinking_level": (settings or gemini.read_settings())["thinking_level"],
                          "media_resolution": None, "ms": 5})
        return self.front if only_front else self.back


@pytest.fixture
def sdk(monkeypatch):
    fake = FakeSdk()
    monkeypatch.setattr(gemini, "_HAVE_SDK", True)
    monkeypatch.setattr(gemini, "call_gemini_sdk", fake)
    return fake


def scan(**form):
    files = {"back": ("b.jpg", BACK, "image/jpeg")}
    if form.pop("with_front", True):
        files["front"] = ("f.jpg", FRONT, "image/jpeg")
    return TestClient(main.app).post("/scan", files=files, data={"pairing_confirmed": "true", **form})


# ---------------------------------------------------------------- the switches

def test_every_switch_is_off_by_default():
    # D-192 added the reader to the settings; Gemini is the default.
    assert gemini.read_settings() == {"reader": "gemini", "model": "gemini-3.6-flash", "thinking_level": "low",
                                      "media_resolution": None, "split_front": False}
    # The prompt is unchanged (D-193 point 6), so earlier scans and gold files still compare.
    assert main.PROMPT_VERSION == "01696584efa3"


def test_switch_values(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_THINKING_LEVEL", "minimal")
    monkeypatch.setenv("INSIDELABEL_MEDIA_RESOLUTION", "LOW")
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    assert gemini.read_settings() == {"reader": "gemini", "model": "gemini-3.6-flash", "thinking_level": "minimal",
                                      "media_resolution": "low", "split_front": True}
    # A value the API doesn't take reads as today: a typo in settings.env changes nothing.
    monkeypatch.setenv("INSIDELABEL_THINKING_LEVEL", "none")
    monkeypatch.setenv("INSIDELABEL_MEDIA_RESOLUTION", "ultra_high")
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "yes")
    assert gemini.read_settings()["thinking_level"] == "low"
    assert gemini.read_settings()["media_resolution"] is None and gemini.read_settings()["split_front"] is False


class _Resp:
    text = answer()

    class usage_metadata:                                        # noqa: N801 - the SDK's shape
        prompt_token_count, candidates_token_count, thoughts_token_count, total_token_count = 2300, 410, 12, 2722


def test_the_sdk_call_sends_the_settings_and_fills_the_callers_usage(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, **kw):
            self.models = self

        def generate_content(self, model, contents, config):
            seen["config"] = config
            return _Resp()
    monkeypatch.setattr(gemini.genai, "Client", Client)
    usage = {}
    gemini.call_gemini_json("p", [(BACK, "image/jpeg", "back")], {"type": "object"}, api_key="k", usage=usage)
    assert seen["config"].thinking_config.thinking_level.value.lower() == "low"
    assert seen["config"].media_resolution is None
    assert usage["input_tokens"] == 2300 and usage["output_tokens"] == 410 and usage["thinking_tokens"] == 12
    assert usage["thinking_level"] == "low" and usage["model"] == gemini.MODEL
    monkeypatch.setenv("INSIDELABEL_THINKING_LEVEL", "minimal")
    monkeypatch.setenv("INSIDELABEL_MEDIA_RESOLUTION", "medium")
    gemini.call_gemini_json("p", [(BACK, "image/jpeg", "back")], {"type": "object"}, api_key="k")
    assert seen["config"].thinking_config.thinking_level.value.lower() == "minimal"
    assert seen["config"].media_resolution.name == "MEDIA_RESOLUTION_MEDIUM"


def test_the_rest_fallback_sends_a_setting_only_when_switched(monkeypatch):
    cfg = gemini.build_request([(BACK, "image/jpeg", "back")])["generationConfig"]
    assert "thinkingConfig" not in cfg and "mediaResolution" not in cfg
    monkeypatch.setenv("INSIDELABEL_THINKING_LEVEL", "minimal")
    monkeypatch.setenv("INSIDELABEL_MEDIA_RESOLUTION", "low")
    cfg = gemini.build_request([(BACK, "image/jpeg", "back")])["generationConfig"]
    assert cfg["thinkingConfig"] == {"thinkingLevel": "MINIMAL"} and cfg["mediaResolution"] == "MEDIA_RESOLUTION_LOW"


def test_no_shared_usage_global_is_left():
    assert not hasattr(gemini, "LAST_USAGE")
    for path in ("tools/batch_scan.py", "tools/scan_label.py", "tools/table_read.py"):
        assert "LAST_USAGE" not in open(os.path.join(ROOT, path), encoding="utf-8").read(), path


# ---------------------------------------------------------------- usage per scan

def test_two_scans_at_once_keep_their_own_token_counts(monkeypatch):
    def slow_sdk(images, api_key=None, usage=None, settings=None):
        n = len(images[0][0]) % 1000
        time.sleep(0.2)
        usage.update({"input_tokens": n, "output_tokens": n + 1, "thinking_tokens": 0, "total_tokens": 2 * n + 1,
                      "model": gemini.MODEL, "thinking_level": "low", "media_resolution": None, "ms": 200})
        return answer()
    monkeypatch.setattr(gemini, "_HAVE_SDK", True)
    monkeypatch.setattr(gemini, "call_gemini_sdk", slow_sdk)
    out = {}

    def read(name, data):
        v, _c = gemini.analyze_images([(data, "image/jpeg", "back")])
        out[name] = v["_usage"]["input_tokens"]
    a, b = b"a" * 1001, b"b" * 1002
    threads = [threading.Thread(target=read, args=("a", a)), threading.Thread(target=read, args=("b", b))]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert out == {"a": 1, "b": 2}


def test_a_replay_has_no_usage():
    v, _c = gemini.analyze_images([(BACK, "image/jpeg", "back")], raw_response=answer())
    assert v["_usage"] is None


# ---------------------------------------------------------------- split front: the join

def test_join_takes_each_face_from_its_own_call():
    back = json.loads(answer(statements=["Proprietary food"]))
    front = json.loads(answer(front=True, claims=["No added MSG"], statements=["Ayurvedic recipe"]))
    v, _c = gemini.harden(gemini.join_answers(back, front), True, True)
    assert v["ingredients"] == ["Wheat flour", "Sugar", "Salt"] and v["back_status"] == "read"
    assert v["front_status"] == "read" and v["front_claims"] == ["No added MSG"]
    assert v["product"]["name"] == "Masala Crunch" and v["product"]["net_quantity"] == "90 g"    # gaps filled
    assert [s["face"] for s in v["pack_statements"]] == ["back", "front"]
    assert v["product_match"]["status"] == "match"                 # the brand is on both faces


def test_join_says_mismatch_only_for_two_brands():
    back = json.loads(answer(brand="Haldiram's"))
    back["back_identity"]["name"] = "Aloo Bhujia"                  # nothing in common with the front
    front = json.loads(answer(front=True, brand="Bikaji"))
    v, _c = gemini.harden(gemini.join_answers(back, front), True, True)
    assert v["product_match"]["status"] == "mismatch"              # D-108's refusal follows
    front["front_identity"]["brand"] = front["product"]["brand"] = None
    v, _c = gemini.harden(gemini.join_answers(back, front), True, True)
    assert v["product_match"]["status"] == "indeterminate"         # no anchor: never a match by default


def test_a_front_not_in_yet_is_not_joined():
    late = gemini.FrontRead([(FRONT, "image/jpeg", "front")], raw_response=answer(front=True))
    late.done.clear()                                              # still reading, as far as the back knows
    v, _c = gemini.analyze_split([(BACK, "image/jpeg", "back"), (FRONT, "image/jpeg", "front")], late,
                                 raw_response=answer())
    assert v["_front_joined"] is False and v["front_status"] == "not_provided" and v["ingredients"]


# ---------------------------------------------------------------- split front: /scan

def test_split_is_off_by_default_one_call(sdk):
    r = scan()
    assert r.status_code == 200, r.text
    assert sdk.calls == [["back", "front"]]


def test_split_reads_both_faces_and_joins_them(sdk, monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    r = scan()
    assert r.status_code == 200, r.text
    assert sorted(sdk.calls) == [["back"], ["front"]]
    assert r.json()["extracted"]["front_claims"] == ["No added MSG"]


def test_a_slow_front_never_holds_the_result(sdk, monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    sdk.front_delay = 1.5
    t0 = time.monotonic()
    r = scan()
    assert r.status_code == 200, r.text
    assert time.monotonic() - t0 < 1.5 + 5                          # the background wait comes after the answer
    assert r.json()["extracted"]["front_claims"] == [] and r.json()["extracted"]["ingredients"]


def test_a_failing_front_never_costs_the_result(sdk, monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    sdk.front_error = gemini.VisionUnavailable("busy")
    monkeypatch.setattr(gemini, "MAX_ATTEMPTS", 1)
    r = scan()
    assert r.status_code == 200, r.text
    assert r.json()["extracted"]["ingredients"] == ["Wheat flour", "Sugar", "Salt"]


def test_a_split_scan_replays_the_same(monkeypatch):
    form = {"replay": answer(), "replay_front": answer(front=True, claims=["No added MSG"])}
    joined = scan(**form)
    assert joined.json()["extracted"]["front_claims"] == ["No added MSG"]
    skipped = scan(replay=answer(), replay_front=gemini.SKIPPED_FRONT)
    assert skipped.status_code == 200 and skipped.json()["extracted"]["front_claims"] == []
    # repro passes them from the row.
    data = repro.form_for({"images": ["back", "front"]}, "raw", "front raw", {"front_joined": True})
    assert data["replay_front"] == "front raw"
    assert repro.form_for({}, "raw", None, {"front_joined": False})["replay_front"] == gemini.SKIPPED_FRONT
    assert "replay_front" not in repro.form_for({}, "raw", None, {})


def test_repro_prints_the_read(monkeypatch):
    lines = repro.read_lines({"read": {"model": "gemini-3.6-flash", "thinking_level": "low",
                                       "media_resolution": None, "split_front": True},
                              "gemini": {"input_tokens": 2300, "output_tokens": 400, "thinking_tokens": 9, "ms": 8100},
                              "front_joined": False, "front_error": "VisionUnavailable: busy"})
    assert lines[0] == "read gemini-3.6-flash · thinking low · media default · split on"
    assert lines[1] == "tokens label: in 2300 · out 400 · thinking 9 · 8100 ms"
    assert lines[2] == "front joined: False (VisionUnavailable: busy)"
    assert repro.read_lines({}, {"repeat_of": "abc"}) == ["same photos as scan abc: answered from its stored read"]


# ---------------------------------------------------------------- stored with the scan

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


def stored(uri, scan_id):
    with psycopg.connect(uri) as c:
        return c.execute("SELECT timings, model_raw, model_raw_front FROM scans WHERE id = %s",
                         (scan_id,)).fetchone()


def test_usage_and_settings_are_stored_with_the_scan(env, sdk):
    r = scan(device_id=str(uuid.uuid4()))
    timings, _raw, front = stored(env, r.json()["scan_id"])
    assert timings["read"] == gemini.read_settings()
    assert timings["gemini"]["input_tokens"] == 2000 and timings["gemini"]["thinking_level"] == "low"
    assert front is None and "front_joined" not in timings


def test_a_late_front_answer_is_kept_on_the_row(env, sdk, monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    sdk.front_delay = 1.0
    r = scan(device_id=str(uuid.uuid4()))
    assert r.status_code == 200
    # The test client runs the background task before it returns.
    timings, _raw, front = stored(env, r.json()["scan_id"])
    assert timings["front_joined"] is False and timings["front_late"] is True
    assert front == sdk.front and timings["gemini_front"]["output_tokens"] == 50


def test_a_joined_front_answer_is_kept_on_the_row(env, sdk, monkeypatch):
    monkeypatch.setenv("INSIDELABEL_READ_SPLIT_FRONT", "on")
    real = gemini.analyze_split

    def wait_for_front(images, front_read, **kw):
        front_read.done.wait(5)
        return real(images, front_read, **kw)
    monkeypatch.setattr(main.gemini, "analyze_split", wait_for_front)
    r = scan(device_id=str(uuid.uuid4()))
    timings, _raw, front = stored(env, r.json()["scan_id"])
    assert timings["front_joined"] is True and front == sdk.front
    assert timings["gemini_front"]["output_tokens"] == 50


# ---------------------------------------------------------------- batch_scan

def test_batch_scan_flags(tmp_path):
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}
    out = subprocess.run([sys.executable, "tools/batch_scan.py", "--photos", str(tmp_path), "--out",
                          str(tmp_path / "pred"), "--thinking-level", "minimal", "--media-resolution", "low",
                          "--split-front"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert "'thinking_level': 'minimal'" in out.stderr and "'media_resolution': 'low'" in out.stderr
    assert "'split_front': True" in out.stderr
    refused = subprocess.run([sys.executable, "tools/batch_scan.py", "--photos", str(tmp_path), "--out", "reports/x"],
                             cwd=ROOT, env=env, capture_output=True, text=True)
    assert refused.returncode != 0 and "inside reports/" in refused.stderr
