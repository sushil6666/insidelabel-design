"""
scan-speed (2026-10-01): a photo scan takes Gemini's time whether or not Cloud
Vision works, and a Vision outage reaches the problem reports.

The case: from 18:02 UTC on 2026-10-01 every Cloud Vision call answered HTTP 200
with a per-image {"code": 8, "message": "Resource has been exhausted (e.g. check
quota)."}. Scans fell back to Tesseract after Gemini had answered, nine passes one
after another, and took 50 to 80 s; the breaker re-opened after 60 s inside one
scan; nobody was told. Google's answers, Gemini and Tesseract are faked here: no
network call, no cost.
"""
import io
import json
import os
import time
import urllib.error

import pytest
from fastapi.testclient import TestClient

from insidelabel.api import main
from insidelabel.core import engine
from insidelabel.extraction.providers import cloud_vision as cv
from insidelabel.extraction.providers import gemini, ocr_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE8 = {"responses": [{"error": {"code": 8, "message": "Resource has been exhausted (e.g. check quota)."}}]}
READING = {
    "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
    "product": {"brand": None, "name": "Test biscuit", "variant": None, "net_quantity": None, "veg_mark": "veg"},
    "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
    "back_identity": {"brand": "Testco", "name": None, "manufacturer": None, "fssai_licence": None},
    "ingredient_lines": ["Wheat flour, Sugar, Emulsifier (322)"], "ingredient_count": 3,
    "ingredients": ["Wheat flour", "Sugar", "Emulsifier (322)"], "allergen_statement": None,
    "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
    "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
LABEL_TEXT = "INGREDIENTS: Wheat flour, Sugar, Preservative (211), Emulsifier (322). Made by Testco Foods."


def _photo(w=900, h=1200):
    """A plain photo with printed lines (a blank one is refused before any read, D-103)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (240, 236, 226))
    d = ImageDraw.Draw(im)
    for y in range(100, h - 100, 60):
        d.rectangle((80, y, w - 80, y + 18), fill=(40, 40, 50))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


PHOTO = _photo()


class Google:
    """Cloud Vision's answer, faked: code 8 (HTTP 200), an HTTP error, or text."""

    def __init__(self, answer="code8"):
        self.answer, self.calls = answer, 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        if self.answer == "code8":
            return io.BytesIO(json.dumps(CODE8).encode())
        if isinstance(self.answer, int):
            raise urllib.error.HTTPError(req.full_url, self.answer, "refused", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps({"responses": [{"fullTextAnnotation": {"text": self.answer}}]}).encode())


class Recorder:
    """Stands in for the database: keeps what /scan stores (its trace, problem reports)."""

    def __init__(self):
        self.calls = []

    def has_agreed(self, *a, **k):
        return True

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, k))
            return None
        return call

    def traces(self):
        return [k["trace"] for n, k in self.calls if "trace" in k]

    def problems(self):
        return [k for n, k in self.calls if n == "save_problem"]


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("GOOGLE_VISION_KEY", "test-key")
    monkeypatch.delenv("INSIDELABEL_OCR", raising=False)
    cv._CACHE.clear()
    monkeypatch.setattr(cv, "_down_until", 0.0)
    monkeypatch.setattr(cv, "_alarm", None)
    monkeypatch.setattr(ocr_check, "AVAILABLE", True)
    # A scan's result never waits for its read, so a slow fake's passes can outlive the
    # test; the next test's fake would then count them. Each test waits for its own reads.
    reads, start = [], ocr_check.start_back_read
    monkeypatch.setattr(ocr_check, "start_back_read", lambda b: reads.append(start(b)) or reads[-1])
    yield
    for read in reads:
        if read is not None:
            read.done.wait(30)


def tesseract(monkeypatch, text=LABEL_TEXT, each_s=0.0):
    calls = []

    def fake(img, *a, **k):
        calls.append(img.size)
        time.sleep(each_s)
        return text
    monkeypatch.setattr(ocr_check.pytesseract, "image_to_string", fake)
    return calls


def live_gemini(monkeypatch, seconds, after_read=False):
    """
    Gemini answering after `seconds`, as a live scan (no replay field) sees it.
    after_read: and not before the scan's own read of the back is done, for a test
    about what the read found rather than when; on a busy machine the photo's
    preparation alone can outlast a short mock, and the scan then (rightly) skips.
    """
    orig = gemini.analyze_images
    started = []
    start = ocr_check.start_back_read
    monkeypatch.setattr(ocr_check, "start_back_read", lambda b: started.append(start(b)) or started[-1])

    def slow(images, api_key=None, raw_response=None, on_attempt=None):
        time.sleep(seconds)
        if after_read:
            assert started and started[-1].done.wait(10)
        return orig(images, raw_response=json.dumps(READING))
    monkeypatch.setattr(gemini, "analyze_images", slow)


def scan(monkeypatch, store=None):
    if store is not None:
        monkeypatch.setattr(main, "STORE", store)
    t0 = time.monotonic()
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", PHOTO, "image/jpeg")})
    return r, time.monotonic() - t0


# ---------------------------------------------------------------- the breaker and the alarm

def test_code_8_with_http_200_trips_the_breaker_for_ten_minutes_and_raises_the_alarm(monkeypatch):
    g = Google("code8")
    monkeypatch.setattr(cv.urllib.request, "urlopen", g)
    assert cv.read_text(PHOTO) is None
    assert cv.DOWN_OUTAGE_S == 600
    assert cv.DOWN_OUTAGE_S - 5 < cv._down_until - cv.time.monotonic() <= cv.DOWN_OUTAGE_S
    assert cv.take_alarm() == "code_8" and cv.take_alarm() is None          # once per trip
    assert cv.alarm_text("code_8").startswith("Cloud Vision refused (code 8): scans use the fallback reader")
    assert "OPERATIONS.md" in cv.alarm_text("code_8")
    assert cv.read_text(_photo(901)) is None and g.calls == 1                # skipped while tripped


def test_http_429_is_an_outage_too(monkeypatch):
    monkeypatch.setattr(cv.urllib.request, "urlopen", Google(429))
    assert cv.read_text(PHOTO) is None
    assert cv._down_until - cv.time.monotonic() > cv.DOWN_TRANSIENT_S
    assert cv.take_alarm() == "http_429"


def test_another_per_image_error_is_still_brief_and_silent(monkeypatch):
    bad = {"responses": [{"error": {"code": 3, "message": "Bad image data."}}]}
    monkeypatch.setattr(cv.urllib.request, "urlopen", lambda req, timeout=None: io.BytesIO(json.dumps(bad).encode()))
    assert cv.read_text(PHOTO) is None
    assert 0 < cv._down_until - cv.time.monotonic() <= cv.DOWN_TRANSIENT_S
    assert cv.take_alarm() is None


def test_a_scan_calls_vision_once_never_retries_and_files_one_problem_report(monkeypatch):
    g = Google("code8")
    monkeypatch.setattr(cv.urllib.request, "urlopen", g)
    tesseract(monkeypatch)
    live_gemini(monkeypatch, 0.3, after_read=True)
    store = Recorder()
    r, _ = scan(monkeypatch, store)
    assert r.status_code == 200 and g.calls == 1                             # no second try in the scan
    ocr = r.json()["reliability"]["ocr_cross_check"]
    assert ocr["reader"] == "tesseract" and ocr["fallback_from"] == "cloud_vision code_8"
    assert ocr["missing"] == ["211"]                                          # the fallback still recovers
    probs = store.problems()
    assert len(probs) == 1 and probs[0]["kind"] == "server" and probs[0]["signature"] == "ocr_config:code_8"
    assert probs[0]["server_error"].startswith("Cloud Vision refused (code 8): scans use the fallback reader")
    # The next scan inside the 10 minutes: no call to Google, no second report.
    r, _ = scan(monkeypatch, store)
    assert r.status_code == 200 and g.calls == 1 and len(store.problems()) == 1


# ---------------------------------------------------------------- the fallback runs alongside Gemini

def test_tesseract_runs_alongside_gemini_not_after_it(monkeypatch):
    monkeypatch.setattr(cv.urllib.request, "urlopen", Google("code8"))
    calls = tesseract(monkeypatch, each_s=0.1)              # 6 passes, two at a time: ~0.3 s
    live_gemini(monkeypatch, 0.8)
    r, took = scan(monkeypatch)
    ocr = r.json()["reliability"]["ocr_cross_check"]
    assert ocr["available"] and ocr["reader"] == "tesseract" and ocr["passes"] == 6
    # Before: 0.8 s of Gemini, then 9 passes in a row (0.9 s). Now: Gemini's time.
    assert took < 1.3, f"{took:.2f}s: the fallback ran after Gemini"
    # One read for every check: the cross-check, the identity check, the table.
    assert len(calls) == 6


def test_the_identity_check_uses_the_same_read(monkeypatch):
    monkeypatch.setattr(cv.urllib.request, "urlopen", Google("code8"))
    calls = tesseract(monkeypatch)
    live_gemini(monkeypatch, 0.3, after_read=True)
    r, _ = scan(monkeypatch)
    assert len(calls) == 6                                    # was 9: two identity reads more
    assert r.status_code == 200


def test_a_read_that_misses_gemini_never_delays_the_result(monkeypatch, caplog):
    monkeypatch.setattr(cv.urllib.request, "urlopen", Google("code8"))
    tesseract(monkeypatch, each_s=1.5)                       # far slower than Gemini
    live_gemini(monkeypatch, 0.2)
    store = Recorder()
    r, took = scan(monkeypatch, store)
    assert r.status_code == 200
    assert took < 1.0, f"{took:.2f}s: the result waited for the cross-check"
    ocr = r.json()["reliability"]["ocr_cross_check"]
    assert ocr["available"] is False and ocr["reason"] == "deadline" and ocr["reader"] == "skipped"
    trace = store.traces()[-1]
    assert trace["timings"]["ocr"] == "skipped (deadline)"
    assert trace["ocr"] == {"back": {"reader": "skipped", "text": None, "passes": 0}}
    # The existing gate (D-062): no omission detector, nothing shown as checked.
    assert r.json()["reliability"]["verdict_safe_to_display"] is False


def test_vision_working_is_unchanged_one_call_and_its_text(monkeypatch):
    g = Google(LABEL_TEXT)
    monkeypatch.setattr(cv.urllib.request, "urlopen", g)
    calls = tesseract(monkeypatch)
    live_gemini(monkeypatch, 0.3, after_read=True)
    r, _ = scan(monkeypatch)
    ocr = r.json()["reliability"]["ocr_cross_check"]
    assert ocr["reader"] == "cloud_vision" and ocr["missing"] == ["211"]
    assert g.calls == 1 and calls == []


# ---------------------------------------------------------------- replays repeat the original

def test_a_replay_votes_on_the_passes_the_original_counted(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    calls = tesseract(monkeypatch)
    with ocr_check.replaying_passes({cv.digest(PHOTO): 3}):
        read = ocr_check.start_back_read(PHOTO)
        read.done.wait(5)
    res = ocr_check.result_of(read, READING["ingredients"])
    assert res["available"] and res["passes"] == 3 and len(calls) == 3
    with ocr_check.replaying_passes({cv.digest(PHOTO): 0}):
        read = ocr_check.start_back_read(PHOTO)
        read.done.wait(5)
    assert ocr_check.result_of(read, READING["ingredients"])["reason"] == "deadline"


# ---------------------------------------------------------------- the same additives found

def _label_photo(lines):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 46) \
        if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ImageFont.load_default()
    im = Image.new("RGB", (1800, 160 + 70 * len(lines)), (236, 232, 220))
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        d.text((90, 80 + 70 * i), ln, fill=(25, 25, 30), font=font)
    im = im.rotate(1.2, fillcolor=(200, 196, 186)).filter(ImageFilter.GaussianBlur(1.0))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


@pytest.mark.parametrize("name", ["ziggy-donut-cake-choco-vanilla", "patanjali-doodh-biscuits"])
def test_the_one_read_finds_the_same_additives_as_the_old_vote(monkeypatch, name):
    import shutil
    if not shutil.which("tesseract"):
        pytest.skip("tesseract not installed")
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    gold = json.load(open(os.path.join(ROOT, "gold", name + ".json"), encoding="utf-8"))
    photo = _label_photo(gold["ingredient_lines"])
    old, _detail, _n = ocr_check.vote_ins(photo)              # the old path: six passes, one by one
    read = ocr_check.start_back_read(photo)
    read.done.wait(120)
    new = ocr_check.result_of(read, [])
    assert new["available"] and set(new["ocr_ins"]) == old
    assert old, "the fixture should carry additives the reader can see"
    assert old <= set(engine._ADDITIVE_BY_INS)


def test_passes_run_two_at_a_time_with_one_thread_each():
    assert ocr_check.TESS_WORKERS == 2
    assert os.environ.get("OMP_THREAD_LIMIT") == "1"


# ---------------------------------------------------------------- the read-only query for the server

def test_the_scan_speed_query_in_operations_runs_on_the_real_schema(fresh_db):
    import re
    import psycopg
    ops = open(os.path.join(ROOT, "OPERATIONS.md"), encoding="utf-8").read()
    block = ops.split("# Scan speed per day", 1)[1].split("```", 1)[0]
    sql = re.search(r'-c "(.*)"', block, re.S).group(1)
    assert sql.lstrip().upper().startswith("SELECT")                     # read-only
    uri = fresh_db[0]
    with psycopg.connect(uri, autocommit=True) as conn:
        for ms, reader in ((8000, "cloud_vision"), (12000, "tesseract"), (9000, "skipped"), (54000, None)):
            ocr = json.dumps({"back": {"reader": reader}} if reader else {})
            conn.execute("INSERT INTO scans (resolved_via, outcome, latency_ms, back_image_key, ocr) "
                         "VALUES ('failed', 'refused', %s, 'k.jpg', %s)", (ms, ocr))
        rows = conn.execute(sql).fetchall()
    assert len(rows) == 1
    _day, n, p50, p90, mx, vision, tess, skipped, none = rows[0]
    assert (n, vision, tess, skipped, none) == (4, 1, 1, 1, 1)
    assert float(mx) == 54.0 and float(p50) == 10.5 and float(p90) > 30
