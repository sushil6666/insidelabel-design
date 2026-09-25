"""
retention.py - delete users' scan photos after 30 days (D-080, D-098).

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
