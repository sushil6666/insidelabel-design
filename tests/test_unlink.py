"""
D-128: after 30 days a scan keeps what the label said but loses who sent it: its
install id and the household profiles in its request. Held scans keep the
link until the hold ends, never past 12 months. Feedback, problem
reports and installs go after 12 months. The beta's per-day counts survive in
device_days (D-055).
"""
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from test_retention import c, env, scan as photo_scan, sql, vision  # noqa: E402,F401
from test_screen import FAMILY  # noqa: E402

from gtins import gtin  # noqa: E402
from insidelabel import retention  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402


def scan(uri, dev, days_old=31):
    r = c.post("/scan", files={"back": ("b.jpg", b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes, "image/jpeg")},
               data={"replay": vision(), "barcode": gtin(), "device_id": dev,
                     "avoid": "milk", "profiles": json.dumps(FAMILY)})
    sid = r.json()["scan_id"]
    sql(uri, "UPDATE scans SET created_at = now() - make_interval(days => %s) WHERE id = %s RETURNING id",
        days_old, sid)
    return sid


def row(uri, sid):
    return sql(uri, "SELECT user_id, request, unlinked_at, model_raw FROM scans WHERE id = %s", sid)[0]


def test_an_old_scan_loses_its_install_and_profiles_but_keeps_the_reading(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    sid = scan(uri, dev)
    before = row(uri, sid)
    assert str(before["user_id"]) == dev and before["request"]["profiles"] and before["request"]["avoid"]
    dry = retention.unlink(uri)
    assert dry["unlinked_scans"] >= 1 and row(uri, sid)["user_id"] is not None       # dry run: nothing changed
    retention.unlink(uri, apply=True)
    after = row(uri, sid)
    assert after["user_id"] is None and after["unlinked_at"] is not None
    assert "profiles" not in after["request"] and "avoid" not in after["request"]
    assert after["request"]["barcode"] and after["model_raw"] == before["model_raw"]  # the reading stays
    days = sql(uri, "SELECT day, scans FROM device_days WHERE user_id = %s", dev)
    assert [d["scans"] for d in days] == [1]


def test_a_recent_scan_keeps_its_link(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    sid = scan(uri, dev, days_old=29)
    retention.unlink(uri, apply=True)
    assert str(row(uri, sid)["user_id"]) == dev


def test_a_held_scan_keeps_its_link_until_12_months(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    sid = scan(uri, dev)
    sql(uri, "UPDATE scans SET evidence_hold = true WHERE id = %s RETURNING id", sid)
    retention.unlink(uri, apply=True)
    assert str(row(uri, sid)["user_id"]) == dev
    sql(uri, "UPDATE scans SET created_at = now() - interval '366 days' WHERE id = %s RETURNING id", sid)
    retention.unlink(uri, apply=True)
    r = sql(uri, "SELECT user_id, evidence_hold FROM scans WHERE id = %s", sid)[0]
    assert r["user_id"] is None and r["evidence_hold"] is False   # no report names it: the hold ended


def test_a_hold_with_a_report_left_stays(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    sid = scan(uri, dev, days_old=400)
    Store(uri).save_problem(kind="user", device_id=dev, scan_id=sid, comment="wrong sugar")
    retention.unlink(uri, apply=True)
    assert sql(uri, "SELECT evidence_hold FROM scans WHERE id = %s", sid)[0]["evidence_hold"] is True


def test_feedback_and_reports_go_after_12_months(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    store = Store(uri)
    old_fb = store.save_feedback(device_id=dev, rating=4, comment="old one")
    new_fb = store.save_feedback(device_id=dev, rating=5, comment="new one")
    old_rep = store.save_problem(kind="user", device_id=dev, comment="old report")["problem_id"]
    sql(uri, "UPDATE feedback SET created_at = now() - interval '366 days' WHERE id = %s RETURNING id", old_fb)
    sql(uri, "UPDATE problem_reports SET created_at = now() - interval '366 days' WHERE id = %s RETURNING id",
        old_rep)
    retention.unlink(uri, apply=True)
    assert [r["id"] for r in sql(uri, "SELECT id FROM feedback WHERE user_id = %s", dev)] == [new_fb]
    assert sql(uri, "SELECT id FROM problem_reports WHERE id = %s", old_rep) == []


def test_an_install_unseen_for_12_months_goes_with_its_links(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    sid = scan(uri, dev, days_old=400)
    sql(uri, "UPDATE users SET created_at = now() - interval '400 days' WHERE id = %s RETURNING id", dev)
    retention.unlink(uri, apply=True)
    assert sql(uri, "SELECT id FROM users WHERE id = %s", dev) == []
    assert sql(uri, "SELECT 1 FROM device_days WHERE user_id = %s", dev) == []
    assert row(uri, sid)["user_id"] is None and row(uri, sid)["model_raw"]   # the scan itself stays


def test_an_install_seen_lately_stays(env):
    uri, _ = env
    dev = str(uuid.uuid4())
    scan(uri, dev, days_old=400)
    scan(uri, dev, days_old=40)             # unlinked too, but device_days says it was seen
    sql(uri, "UPDATE users SET created_at = now() - interval '400 days' WHERE id = %s RETURNING id", dev)
    retention.unlink(uri, apply=True)
    assert sql(uri, "SELECT id FROM users WHERE id = %s", dev) != []


def test_beta_counts_survive_unlinking(env):
    uri, _ = env
    store = Store(uri)
    [code] = store.create_invites(1, label="T99")
    dev = str(uuid.uuid4())
    assert "error" not in store.join_invite(code, dev)
    scan(uri, dev, days_old=45)
    scan(uri, dev, days_old=10)
    before = next(r for r in store.beta_testers() if r["code"] == code)
    retention.unlink(uri, apply=True)
    after = next(r for r in store.beta_testers() if r["code"] == code)
    assert (after["scans"], after["days_active"]) == (before["scans"], before["days_active"]) == (2, 2)
