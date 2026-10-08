"""
D-129 "Delete my data": POST /forget erases what an install id points at. Scans
stay, unlinked, with what the label said; a photo that became a catalogue
version's evidence stays (the pack's record); every other photo of theirs goes.
"""
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from test_retention import c, env, exists, scan as photo_scan, sql  # noqa: E402,F401
from test_screen import FAMILY  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402


def test_delete_my_data_erases_the_install_and_its_photos(env):
    uri, media = env
    dev = str(uuid.uuid4())
    store = Store(uri)
    refused, gone_key = photo_scan(dev=dev, refused=True, days_old=2, uri=uri)
    readable, kept_key = photo_scan(dev=dev, refused=False, days_old=2, uri=uri)
    sql(uri, "UPDATE scans SET request = request || %s WHERE id = %s RETURNING id",
        json.dumps({"profiles": FAMILY, "avoid": ["milk"]}), refused)
    store.save_feedback(device_id=dev, comment="nice")
    store.save_problem(kind="user", device_id=dev, scan_id=refused, comment="odd")
    # D-184: no new codes, but a code joined before D-162 can still be on the server.
    sql(uri, "INSERT INTO invites (code) VALUES ('T98T98T9') RETURNING code")
    sql(uri, "INSERT INTO invite_devices (user_id, code) VALUES (%s, 'T98T98T9') RETURNING code", dev)

    r = c.post("/forget", json={"device_id": dev})
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    d = r.json()["deleted"]
    assert d["feedback"] == 1 and d["problem_reports"] == 1 and d["photos"] >= 1

    assert sql(uri, "SELECT 1 FROM users WHERE id = %s", dev) == []
    assert sql(uri, "SELECT 1 FROM invite_devices WHERE user_id = %s", dev) == []
    for sid in (refused, readable):
        s = sql(uri, "SELECT user_id, request, evidence_hold, model_raw FROM scans WHERE id = %s", sid)[0]
        assert s["user_id"] is None and not s["evidence_hold"] and s["model_raw"]   # the reading stays
        assert "profiles" not in s["request"] and "avoid" not in s["request"]
    assert not exists(media, gone_key)
    assert exists(media, kept_key)                  # the pending catalogue version's evidence
    assert c.post("/forget", json={"device_id": dev}).json() == {"status": "nothing_stored"}


def test_an_open_send_to_us_request_is_closed(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    a, _ = photo_scan(dev=dev, refused=True, days_old=1, uri=uri)
    b, _ = photo_scan(dev=dev, refused=True, days_old=1, uri=uri)
    rid = Store(uri).send_to_us(device_id=dev, scan_ids=[a, b])["review_id"]
    c.post("/forget", json={"device_id": dev})
    q = sql(uri, "SELECT status, notify_user_id FROM review_queue WHERE id = %s", rid)[0]
    assert q["status"] == "rejected" and q["notify_user_id"] is None


def test_a_photo_another_install_also_sent_stays(env):
    uri, media = env
    photo = b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes
    mine, key = photo_scan(dev=str(uuid.uuid4()), photo=photo, days_old=1, uri=uri)
    photo_scan(dev=str(uuid.uuid4()), photo=photo, days_old=1, uri=uri)
    dev = str(sql(uri, "SELECT user_id FROM scans WHERE id = %s", mine)[0]["user_id"])
    c.post("/forget", json={"device_id": dev})
    assert exists(media, key)


def test_a_new_or_bad_id_is_nothing(env):
    assert c.post("/forget", json={"device_id": str(uuid.uuid4())}).json() == {"status": "nothing_stored"}
    assert c.post("/forget", json={"device_id": "not-a-uuid"}).json() == {"status": "nothing_stored"}


def test_forget_is_rate_limited(env):
    dev = str(uuid.uuid4())
    codes = [c.post("/forget", json={"device_id": dev}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
    main.ratelimit.LIMITER.reset()
