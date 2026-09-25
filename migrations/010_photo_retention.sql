-- 010_photo_retention.sql — D-080: a user's scan photos are deleted 30 days after
-- the scan unless something still needs them (D-098, `tools/retention.py`).
--
-- The keys stay on the row after deletion: they are content hashes, so they
-- still say which photo the scan used, and repro.py reports "photo not
-- available" instead of guessing. photos_deleted_at says when it went.

ALTER TABLE scans ADD COLUMN photos_deleted_at timestamptz;
-- The job's scan: old, not held, photos not yet deleted.
CREATE INDEX scans_retention ON scans (created_at)
  WHERE photos_deleted_at IS NULL AND NOT evidence_hold;
