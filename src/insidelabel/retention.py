"""
retention.py - delete users' scan photos after 30 days (D-080, D-098), and unlink
scans from the install that sent them (D-128).

D-080: "user scan photos: delete full originals at 30 days unless flagged".
A photo is deleted only when every scan that sent it is older than the limit
and nothing else still needs it. Kept, whatever its age:

  * photos of a held scan (evidence_hold): a user's problem report (D-092) or
    a pack sent to us (D-070);
  * photos on a product version that isn't rejected: the catalogue record's
    evidence, which reviewers check against (D-028, "seed and reviewer photos
    are kept in full");
  * photos of scans an open or claimed review item points at (its scan, its
    earlier attempts);
  * a photo another scan sent within the limit: keys are content hashes, so the
    same bytes sent twice share one file.

D-080 planned an R2 lifecycle rule on an "originals" prefix. A lifecycle rule
can't see these exceptions, so this job decides, and only its deletions reach
the store: run it daily at deploy (cron), whatever the storage behind `media`.
Dry run unless apply=True. Rows keep their keys; photos_deleted_at is set.
"""

import psycopg
from psycopg.rows import dict_row

DAYS = 30

_CANDIDATES = """
WITH scan_keys AS (
  SELECT s.id, s.created_at, s.evidence_hold, s.photos_deleted_at, k.key
    FROM scans s
    CROSS JOIN LATERAL (VALUES (s.back_image_key), (s.front_image_key)) AS k(key)
   WHERE k.key IS NOT NULL
), under_review AS (
  SELECT scan_id AS id FROM review_queue WHERE status IN ('open', 'claimed') AND scan_id IS NOT NULL
  UNION
  SELECT unnest(attempt_scan_ids) FROM review_queue WHERE status IN ('open', 'claimed')
), keep AS (
  SELECT key FROM scan_keys
   WHERE evidence_hold OR created_at >= now() - make_interval(days => %(days)s)
      OR id IN (SELECT id FROM under_review)
  UNION
  SELECT k.key FROM product_versions v
   CROSS JOIN LATERAL (VALUES (v.back_image_key), (v.front_image_key)) AS k(key)
   WHERE k.key IS NOT NULL AND v.status <> 'rejected'
)
SELECT DISTINCT key FROM scan_keys
 WHERE photos_deleted_at IS NULL AND created_at < now() - make_interval(days => %(days)s)
   AND key NOT IN (SELECT key FROM keep)
 ORDER BY key
"""


# The same keep-rules for one key, checked again just before its file goes: a
# scan may have sent the same photo since the list was made.
_STILL_NEEDED = """
SELECT EXISTS (
  SELECT 1 FROM scans s
   WHERE (s.back_image_key = %(key)s OR s.front_image_key = %(key)s)
     AND (s.evidence_hold OR s.created_at >= now() - make_interval(days => %(days)s)
          OR s.id IN (SELECT scan_id FROM review_queue WHERE status IN ('open', 'claimed') AND scan_id IS NOT NULL
                      UNION SELECT unnest(attempt_scan_ids) FROM review_queue WHERE status IN ('open', 'claimed')))
) OR EXISTS (
  SELECT 1 FROM product_versions v
   WHERE (v.back_image_key = %(key)s OR v.front_image_key = %(key)s) AND v.status <> 'rejected'
) AS needed
"""


def due(conninfo, days=DAYS):
    """Keys whose photos the rules say can go now."""
    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        return [r["key"] for r in conn.execute(_CANDIDATES, {"days": days}).fetchall()]


def delete(conninfo, media, keys, days=DAYS):
    """Delete the listed photos that are still due; mark their scans."""
    out = {"delete": list(keys), "deleted": [], "missing": []}
    for key in keys:
        with psycopg.connect(conninfo, row_factory=dict_row) as conn:
            if conn.execute(_STILL_NEEDED, {"key": key, "days": days}).fetchone()["needed"]:
                continue
        # File first, then the rows: a crash in between leaves a row that the
        # next run marks as "missing", never a row that says deleted while the
        # photo is still there.
        (out["deleted"] if media.delete(key) else out["missing"]).append(key)
        with psycopg.connect(conninfo) as conn:
            conn.execute("""UPDATE scans SET photos_deleted_at = now()
                             WHERE photos_deleted_at IS NULL AND (back_image_key = %s OR front_image_key = %s)""",
                         (key, key))
    return out


def run(conninfo, media, days=DAYS, apply=False):
    """
    {"delete": keys due, "deleted": removed now, "missing": already gone}.
    With apply=False nothing is removed or marked.
    """
    keys = due(conninfo, days)
    if not apply:
        return {"delete": keys, "deleted": [], "missing": []}
    return delete(conninfo, media, keys, days)


# -- D-128: keep what the label said, not who scanned it ----------------------
#
# After DAYS a scan loses its install id and the household profiles in its
# request (a child's age band and avoid list); what was read stays. A held
# scan (a problem report, "send it to us") keeps its link, so a replay has the
# profiles it ran with (D-092), until the hold ends and never past KEEP_DAYS.
# A review needs the photo, which the rules above keep, not the install. Before the link goes, the scan is counted in device_days so the
# beta can still see which days each install scanned (D-055).
#
# KEEP_DAYS is the life of what is about the person: feedback, problem
# reports, and an install id with its invite link and agreement, counted from
# the device's last sign of use.

KEEP_DAYS = 365

_UNLINK = """
WITH due AS (
  SELECT id, user_id, created_at FROM scans
   WHERE unlinked_at IS NULL
     AND (created_at < now() - make_interval(days => %(keep)s)
          OR (created_at < now() - make_interval(days => %(days)s)
              AND NOT evidence_hold))
   FOR UPDATE
), counted AS (
  INSERT INTO device_days (user_id, day, scans)
  SELECT user_id, created_at::date, count(*) FROM due WHERE user_id IS NOT NULL GROUP BY 1, 2
  ON CONFLICT (user_id, day) DO UPDATE SET scans = device_days.scans + EXCLUDED.scans
)
UPDATE scans s SET user_id = NULL, request = s.request - 'profiles' - 'avoid', unlinked_at = now()
  FROM due WHERE s.id = due.id
"""

# "Show the result on next open" (D-070) needs the install id only until it was shown.
_UNLINK_NOTIFY = """
UPDATE review_queue SET notify_user_id = NULL
 WHERE notify_user_id IS NOT NULL AND status IN ('done', 'rejected')
   AND resolved_at < now() - make_interval(days => %(days)s)
"""

# A hold ends with its reason: no report left that names the scan. An open
# review still keeps the photo (the rules above), not the hold.
_RELEASE_HOLDS = """
UPDATE scans SET evidence_hold = false
 WHERE evidence_hold AND created_at < now() - make_interval(days => %(keep)s)
   AND id NOT IN (SELECT scan_id FROM problem_reports WHERE scan_id IS NOT NULL)
   AND coalesce(request_id, '') NOT IN (
         SELECT e->>'request_id' FROM problem_reports, jsonb_array_elements(events) e
          WHERE jsonb_typeof(e) = 'object' AND e->>'request_id' IS NOT NULL)
"""

_GONE_DEVICES = """
SELECT u.id FROM users u
 WHERE greatest(u.created_at,
                (SELECT max(day)::timestamptz FROM device_days d WHERE d.user_id = u.id),
                (SELECT max(created_at) FROM scans s WHERE s.user_id = u.id),
                (SELECT max(created_at) FROM feedback f WHERE f.user_id = u.id),
                (SELECT max(created_at) FROM problem_reports p WHERE p.user_id = u.id),
                (SELECT max(agreed_at) FROM agreements a WHERE a.user_id = u.id),
                (SELECT max(joined_at) FROM invite_devices i WHERE i.user_id = u.id))
       < now() - make_interval(days => %(keep)s)
"""


def unlink(conninfo, days=DAYS, keep_days=KEEP_DAYS, apply=False):
    """
    D-128. {"unlinked_scans", "released_holds", "feedback", "problem_reports",
    "devices"}: what was (or, as a dry run, would be) unlinked or deleted.
    """
    p = {"days": days, "keep": keep_days}
    out = {}
    with psycopg.connect(conninfo) as conn:
        out["problem_reports"] = conn.execute(
            "DELETE FROM problem_reports WHERE created_at < now() - make_interval(days => %(keep)s)", p).rowcount
        out["feedback"] = conn.execute(
            "DELETE FROM feedback WHERE created_at < now() - make_interval(days => %(keep)s)", p).rowcount
        out["released_holds"] = conn.execute(_RELEASE_HOLDS, p).rowcount
        out["unlinked_scans"] = conn.execute(_UNLINK, p).rowcount
        conn.execute(_UNLINK_NOTIFY, p)
        gone = [r[0] for r in conn.execute(_GONE_DEVICES, p).fetchall()]
        forget_users(conn, gone)
        out["devices"] = len(gone)
        if not apply:
            conn.rollback()
    return out


def forget_users(conn, ids):
    """
    Remove install ids and everything that still points at them, inside the
    caller's transaction (D-128: 12 months unseen; "Delete my data"). Scans stay,
    unlinked, with what the label said. Photos are the caller's job.
    """
    if not ids:
        return
    conn.execute("""UPDATE scans SET user_id = NULL, request = request - 'profiles' - 'avoid',
                                    unlinked_at = coalesce(unlinked_at, now())
                     WHERE user_id = ANY(%s)""", (ids,))
    for table in ("device_days", "agreements", "invite_devices", "user_profiles"):
        conn.execute(f"DELETE FROM {table} WHERE user_id = ANY(%s)", (ids,))
    for table, col in (("problem_reports", "user_id"), ("feedback", "user_id"),
                       ("corrections", "user_id"), ("review_queue", "notify_user_id")):
        conn.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} = ANY(%s)", (ids,))
    conn.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))
