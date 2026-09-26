-- 014_unlisted_scans.sql - a pack without a barcode is read, not catalogued (D-107).
--
-- The catalogue is filed by barcode (D-024). A scan without one still gets its
-- result, but creates no product, version or review item. Its scan row is kept
-- so it can be replayed (D-092); its photos go at 30 days (D-098), since no
-- version holds them. 'verdict' keeps meaning "a result tied to a version".

ALTER TABLE scans DROP CONSTRAINT scans_outcome_check;
ALTER TABLE scans ADD CONSTRAINT scans_outcome_check
  CHECK (outcome IN ('verdict', 'refused', 'vision_unavailable', 'vision_failed', 'unlisted'));
ALTER TABLE scans DROP CONSTRAINT scans_resolved_via_check;
ALTER TABLE scans ADD CONSTRAINT scans_resolved_via_check
  CHECK (resolved_via IN ('barcode', 'fingerprint', 'new_product', 'failed', 'no_barcode'));
