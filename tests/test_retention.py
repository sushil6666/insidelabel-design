"""
Photo retention (D-080, D-098): a user's scan photo is deleted 30 days after the
scan, unless something still needs it:

  * the scan is held (evidence_hold: a problem report, "send it to us"),
  * the photo belongs to a catalogue version (the record's evidence, D-028),
  * an open review item points at the scan,
  * a newer scan sent the very same photo (keys are content hashes).

The job is dry-run by default. Photos live in a temporary media dir here.
"""
import json
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from gtins import gtin  # noqa: E402
from insidelabel import retention  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402

c = TestClient(main.app)


def vision(**kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": None, "name": "Keep Test", "variant": None, "net_quantity": None, "veg_mark": None},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": ["Sugar, Salt"], "ingredient_count": 2, "ingredients": ["Sugar", "Salt"],
         "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_OCR", "tesseract")
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    yield uri, main.MEDIA
    mp.undo()
    main.STORE, main.MEDIA = saved


def sql(uri, q, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(q, args).fetchall()


def scan(dev=None, photo=None, refused=True, days_old=31, uri=None):
    """A stored scan with a back photo, aged `days_old` days. Returns (scan_id, key)."""
    photo = photo or (b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes)
    r = c.post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
               data={"replay": vision(back_status="unreadable") if refused else vision(),
                     "barcode": gtin(),               # D-107: only barcoded packs get a version
                     "device_id": dev or str(uuid.uuid4())})
    sid = r.json()["scan_id"]
    rows = sql(uri, "UPDATE scans SET created_at = now() - make_interval(days => %s) WHERE id = %s "
                    "RETURNING back_image_key", days_old, sid)
    return sid, rows[0]["back_image_key"]


def exists(media, key):
    return media.get(key) is not None


def test_an_old_unheld_photo_is_deleted_and_the_scan_marked(env):
    uri, media = env
    sid, key = scan(uri=uri)
    assert exists(media, key)
    dry = retention.run(uri, media, apply=False)
    assert key in dry["delete"] and exists(media, key)              # dry run touches nothing
    out = retention.run(uri, media, apply=True)
    assert key in out["deleted"] and not exists(media, key)
    s = sql(uri, "SELECT back_image_key, photos_deleted_at FROM scans WHERE id = %s", sid)[0]
    assert s["photos_deleted_at"] is not None and s["back_image_key"] == key   # key kept: what was there
    assert key not in retention.run(uri, media, apply=True)["deleted"]         # nothing twice


def test_a_recent_photo_is_kept(env):
    uri, media = env
    _sid, key = scan(uri=uri, days_old=29)
    retention.run(uri, media, apply=True)
    assert exists(media, key)


def test_a_held_scan_keeps_its_photo(env):
    uri, media = env
    sid, key = scan(uri=uri)
    sql(uri, "UPDATE scans SET evidence_hold = true WHERE id = %s RETURNING id", sid)
    out = retention.run(uri, media, apply=True)
    assert key not in out["deleted"] and exists(media, key)


def test_a_catalogue_versions_photo_is_kept(env):
    uri, media = env
    # A readable scan: its photo becomes the evidence of a pending version.
    _sid, key = scan(uri=uri, refused=False)
    assert sql(uri, "SELECT count(*) AS n FROM product_versions WHERE back_image_key = %s", key)[0]["n"] == 1
    retention.run(uri, media, apply=True)
    assert exists(media, key)


def test_a_photo_sent_again_recently_is_kept(env):
    uri, media = env
    same = b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes
    _old, key = scan(uri=uri, photo=same, days_old=40)
    _new, key2 = scan(uri=uri, photo=same, days_old=1)
    assert key == key2
    retention.run(uri, media, apply=True)
    assert exists(media, key)


def test_an_open_review_item_keeps_its_scans_photo(env):
    uri, media = env
    sid, key = scan(uri=uri)
    sql(uri, "INSERT INTO corrections (scan_id, field) VALUES (%s, 'ingredients') RETURNING id", sid)
    sql(uri, "INSERT INTO review_queue (kind, scan_id) VALUES ('correction', %s) RETURNING id", sid)
    retention.run(uri, media, apply=True)
    assert exists(media, key)
    sql(uri, """UPDATE review_queue SET status = 'done', resolution = 'no_change', resolved_at = now()
                 WHERE scan_id = %s RETURNING id""", sid)
    retention.run(uri, media, apply=True)
    assert not exists(media, key)                                   # decided: the rule applies again


def test_a_photo_already_gone_is_just_marked(env):
    uri, media = env
    sid, key = scan(uri=uri)
    os.remove(media._path(key))
    out = retention.run(uri, media, apply=True)
    assert key in out["missing"]
    assert sql(uri, "SELECT photos_deleted_at FROM scans WHERE id = %s", sid)[0]["photos_deleted_at"]


def test_a_replay_after_deletion_says_the_photo_is_gone(env):
    from insidelabel import repro
    uri, media = env
    sid, _key = scan(uri=uri)
    retention.run(uri, media, apply=True)
    s = sql(uri, "SELECT * FROM scans WHERE id = %s", sid)[0]
    out = repro.replay_scan(s, media)
    assert any("photo not available" in n for n in out["notes"])


def test_the_cli_is_a_dry_run_unless_told(env, capsys):
    import importlib.util
    uri, media = env
    spec = importlib.util.spec_from_file_location(
        "retention_cli", os.path.join(os.path.dirname(__file__), "..", "tools", "retention.py"))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    _sid, key = scan(uri=uri)
    cli.main(["--db", uri, "--media", media.root])
    assert "dry run" in capsys.readouterr().out and exists(media, key)
    cli.main(["--db", uri, "--media", media.root, "--apply"])
    assert not exists(media, key)



def test_a_photo_sent_again_while_the_job_runs_is_kept(env):
    uri, media = env
    same = b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes
    _old, key = scan(uri=uri, photo=same, days_old=40)
    listed = retention.due(uri)
    assert key in listed
    scan(uri=uri, photo=same, days_old=0)             # sent again after the list was made
    out = retention.delete(uri, media, listed)
    assert key not in out["deleted"] and exists(media, key)
