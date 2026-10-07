"""
D-172 (problem report #7, 2026-10-07): Gemini's recitation guard blocked the whole answer for
a Britannia pack (finish reason RECITATION, no text), and /scan answered 502 vision_failed with
nothing stored and nothing logged. Now a RECITATION is retried; one that survives is a refusal
a person can read at once ("Send it to us"); and every model failure keeps its text.

Nothing here calls Google: the SDK is a fake, and /scan replays the stored marker.
"""
import base64
import json
import logging
import os
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402

from insidelabel import repro  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import gemini  # noqa: E402
from insidelabel.lenses import screen  # noqa: E402

c = TestClient(main.app, raise_server_exceptions=False)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = {"back": ("b.png", PNG, "image/png")}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- the SDK: blocked, retried
class _Candidate:
    def __init__(self, reason):
        self.finish_reason = getattr(gemini.genai_types.FinishReason, reason)


class _Resp:
    def __init__(self, text=None, reason="STOP"):
        self.text = text
        self.candidates = [_Candidate(reason)]
        self.usage_metadata = None


def _fake_sdk(monkeypatch, answers):
    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(1)
            return answers[min(len(calls), len(answers)) - 1]

    class Client:
        def __init__(self, **kw):
            self.models = Models()
    monkeypatch.setattr(gemini.genai, "Client", Client)
    monkeypatch.setattr(gemini, "_HAVE_SDK", True)
    return calls


def _answer():
    from test_problems import vision
    return vision()


def test_a_persistent_recitation_is_retried_twice_then_blocked(monkeypatch):
    calls = _fake_sdk(monkeypatch, [_Resp(reason="RECITATION")])
    seen = []
    with pytest.raises(gemini.VisionBlocked) as e:
        gemini.analyze_images([(PNG, "image/png", "back")], api_key="k",
                              on_attempt=lambda n, d, err: seen.append((n, d, type(err).__name__)))
    assert e.value.reason == "recitation" and isinstance(e.value, gemini.VisionError)
    assert len(calls) == 3
    assert seen == [(1, 0.0, "VisionBlocked"), (2, 0.0, "VisionBlocked")]


def test_a_recitation_that_passes_on_the_second_try_goes_through(monkeypatch):
    calls = _fake_sdk(monkeypatch, [_Resp(reason="RECITATION"), _Resp(text=_answer())])
    seen = []
    v, _c = gemini.analyze_images([(PNG, "image/png", "back")], api_key="k",
                                  on_attempt=lambda n, d, err: seen.append(n))
    assert len(calls) == 2 and seen == [1] and v["ingredients"]


def test_other_guards_are_not_retried(monkeypatch):
    calls = _fake_sdk(monkeypatch, [_Resp(reason="SAFETY")])
    with pytest.raises(gemini.VisionBlocked) as e:
        gemini.analyze_images([(PNG, "image/png", "back")], api_key="k")
    assert e.value.reason == "safety" and len(calls) == 1


def test_an_empty_answer_without_a_guard_stays_a_plain_error(monkeypatch):
    _fake_sdk(monkeypatch, [_Resp(reason="MAX_TOKENS")])
    with pytest.raises(gemini.VisionError) as e:
        gemini.analyze_images([(PNG, "image/png", "back")], api_key="k")
    assert not isinstance(e.value, gemini.VisionBlocked)


def test_the_rest_path_names_the_guard_too():
    assert gemini._block_reason([{"finishReason": "RECITATION"}]) == "RECITATION"
    assert gemini._block_reason([{"finishReason": "STOP"}]) is None


def test_the_marker_is_recognised_and_never_parsed(monkeypatch):
    marker = gemini.blocked_marker("recitation")
    assert json.loads(marker) == {"_blocked": "RECITATION"}
    assert gemini.blocked_reason(marker) == "recitation"
    for other in (None, "", _answer(), "not json", '{"_blocked": "X", "ingredients": []}'):
        assert gemini.blocked_reason(other) is None, other

    def never(text):
        raise AssertionError("the marker reached the parser")
    monkeypatch.setattr(gemini, "parse_vision_json", never)
    with pytest.raises(gemini.VisionBlocked) as e:
        gemini.analyze_images([(PNG, "image/png", "back")], raw_response=marker)
    assert e.value.reason == "recitation"


# ---------------------------------------------------------------- /scan: a refusal, not a 502
@pytest.fixture(scope="module")
def db(fresh_db, tmp_path_factory):
    from insidelabel.media import LocalMedia
    old = (main.STORE, main.MEDIA)
    main.STORE = Store(fresh_db[0])
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield fresh_db[0]
    main.STORE, main.MEDIA = old


def row(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchone()


def _blocked(monkeypatch):
    """analyze_images as Gemini behaved for report #7: two retries, then blocked."""
    def blocked(images, raw_response=None, on_attempt=None, **kw):
        for n in (1, 2):
            on_attempt(n, 0.0, gemini.VisionBlocked("recitation"))
        raise gemini.VisionBlocked("recitation", "Empty response. Finish reason: RECITATION")
    monkeypatch.setattr(main.gemini, "analyze_images", blocked)


def _photo():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise((800, 600), 60).convert("RGB").save(buf, "JPEG")   # D-103: a real photo reaches the model
    return buf.getvalue()


PHOTO = _photo()


def scan(dev, **data):
    files = BACK if "replay" in data else {"back": ("b.jpg", PHOTO, "image/jpeg")}
    return c.post("/scan", files=files, data={"device_id": dev, **data})


def test_a_blocked_scan_is_a_refusal_a_person_can_read_at_once(db, monkeypatch, caplog):
    _blocked(monkeypatch)
    dev, bc = str(uuid.uuid4()), gtin()
    with caplog.at_level(logging.WARNING, logger="insidelabel.api"):
        r = scan(dev, barcode=bc)
    assert r.status_code == 422, r.text
    j = r.json()
    s = j["screen"]
    assert list(j)[0] == "allergens"                                     # D-060
    assert s["state"] == "retake" and s["can_send"] is True and s["send_now"] is True
    assert s["headline"]["text"] == screen.HEADLINE["vision_blocked"]
    assert s["problem"] == {"code": "vision_blocked", "label": screen.PROBLEM_LABEL["vision_blocked"],
                            "fix": screen.RETAKE["vision_blocked"]}
    assert s["problem"]["label"] == "Our reader couldn't read this label"
    assert s["retake"].startswith("Your photos look fine. Send them to us")
    row_ = row(db, "SELECT * FROM scans WHERE id = %s", j["scan_id"])
    assert row_["outcome"] == "refused" and row_["error_code"] == "vision_blocked:recitation"
    assert row_["model_raw"] == gemini.blocked_marker("recitation")
    assert "RECITATION" in row_["model_error"] and len(row_["model_error"]) <= 1000
    assert [x["error"] for x in row_["timings"]["vision_retries"]] == ["VisionBlocked", "VisionBlocked"]
    assert not row_["evidence_hold"]                                     # held only when sent (D-080)
    assert any("model failed" in m and j["request_id"] in m for m in caplog.messages)

    # "Send it to us" takes this one scan (D-070's two attempts don't apply), and holds it then.
    sent = c.post("/send-to-us", json={"device_id": dev, "scan_ids": [j["scan_id"]]})
    assert sent.status_code == 200, sent.text
    assert row(db, "SELECT evidence_hold FROM scans WHERE id = %s", j["scan_id"])["evidence_hold"]


def test_without_a_barcode_there_is_nothing_to_send(db, monkeypatch):            # D-107
    _blocked(monkeypatch)
    s = scan(str(uuid.uuid4())).json()["screen"]
    assert s["can_send"] is False and s["send_now"] is False
    assert s["problem"]["fix"] == screen.RETAKE_BLOCKED_NO_BARCODE


def test_other_refusals_still_need_two_attempts(db):
    from test_problems import vision
    dev = str(uuid.uuid4())
    r = scan(dev, replay=vision(back_status="unreadable"), barcode=gtin())
    assert r.status_code == 422 and r.json()["screen"]["send_now"] is False
    sent = c.post("/send-to-us", json={"device_id": dev, "scan_ids": [r.json()["scan_id"]]})
    assert sent.status_code == 422 and sent.json()["error"] == "need_two_attempts"


def test_any_other_model_failure_stays_502_and_keeps_its_text(db, caplog):
    with caplog.at_level(logging.WARNING, logger="insidelabel.api"):
        r = scan(str(uuid.uuid4()), replay="this is not json {")
    assert r.status_code == 502 and r.json()["error"] == "vision_failed"
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", r.headers["x-request-id"])
    assert s["model_error"].startswith("VisionError: Model did not return parseable JSON")
    assert any("model failed" in m and r.headers["x-request-id"] in m for m in caplog.messages)


def test_a_busy_model_keeps_its_text_too(db, monkeypatch):
    def busy(images, raw_response=None, **kw):
        raise gemini.VisionUnavailable("Upstream unavailable after 4 attempts. Last error: 503")
    monkeypatch.setattr(main.gemini, "analyze_images", busy)
    r = scan(str(uuid.uuid4()))
    assert r.status_code == 503
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", r.headers["x-request-id"])
    assert s["model_error"] == "VisionUnavailable: Upstream unavailable after 4 attempts. Last error: 503"


# ---------------------------------------------------------------- replay and the other readers
def test_the_blocked_scan_replays_to_the_same_refusal(db, monkeypatch):           # D-092
    _blocked(monkeypatch)
    j = scan(str(uuid.uuid4()), barcode=gtin()).json()
    monkeypatch.undo()
    s = dict(row(db, "SELECT * FROM scans WHERE id = %s", j["scan_id"]))
    out = repro.replay_scan(s)
    assert out["status"] == 422
    assert out["screen"]["problem"] == j["screen"]["problem"] and out["screen"]["send_now"] is True
    assert "the model blocked its answer (recitation)" in out["notes"]


# Every file that reads scans.model_raw, and why the D-172 marker is safe there. A new
# reader fails this test until it is checked and listed (Sushil, accepting D-172).
MODEL_RAW_READERS = {
    "src/insidelabel/api/main.py": "writes it; a replay goes through gemini.analyze_images",
    "src/insidelabel/db/store.py": "stores it (_TRACE_COLS)",
    "src/insidelabel/extraction/providers/gemini.py": "blocked_reason() recognises the marker",
    "src/insidelabel/repro.py": "passes it back to /scan as a replay; notes a blocked answer",
    "tools/repro.py": "show replays it; --save skips a blocked answer",
    "src/insidelabel/review/agent.py": "its own drafts' model_raw (review_drafts), not scans",
    "src/insidelabel/review/service.py": "review_drafts.model_raw; scan rows are shown, never parsed",
    "tools/review_agent.py": "review_drafts.model_raw (recheck), not scans",
}


def test_every_reader_of_model_raw_is_known():
    found = set()
    for top in ("src", "tools"):
        for d, _dirs, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith(".py"):
                    p = os.path.join(d, f)
                    if re.search(r"\bmodel_raw\b", open(p, encoding="utf-8").read()):
                        found.add(os.path.relpath(p, ROOT))
    assert found <= set(MODEL_RAW_READERS), f"new reader of model_raw: {sorted(found - set(MODEL_RAW_READERS))}"


def test_repro_save_skips_a_blocked_scan():
    src = open(os.path.join(ROOT, "tools", "repro.py"), encoding="utf-8").read()
    assert 'and not gemini.blocked_reason(s["model_raw"])' in src
    assert 'print(f"    model error {s[\'model_error\']}")' in src


def test_the_health_report_counts_a_blocked_scan(db, monkeypatch):
    _blocked(monkeypatch)
    scan(str(uuid.uuid4()), barcode=gtin())
    with psycopg.connect(db) as conn:
        rows = dict(conn.execute("SELECT outcome, count(*) FROM scans GROUP BY 1").fetchall())
    assert rows.get("refused", 0) >= 1                 # health_report's scans_by_outcome: no parsing
