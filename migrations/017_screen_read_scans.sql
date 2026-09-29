-- 017_screen_read_scans.sql - a photo of a screen is read, never catalogued (D-130).
--
-- Before D-130 a photo of a screen (a shop listing, a picture on a laptop) was
-- refused (D-103). Now the user gets a result marked "read from a screen", so
-- a pack can be looked at before going to the shop. A listing is a lead, never
-- the record (D-089): such a scan creates no product, version or review item.
-- Its scan row is kept so it can be replayed (D-092); its photos go at 30 days
-- (D-098), since no version holds them.

ALTER TABLE scans DROP CONSTRAINT scans_outcome_check;
ALTER TABLE scans ADD CONSTRAINT scans_outcome_check
  CHECK (outcome IN ('verdict', 'refused', 'vision_unavailable', 'vision_failed', 'unlisted', 'screen_read'));
ALTER TABLE scans DROP CONSTRAINT scans_resolved_via_check;
ALTER TABLE scans ADD CONSTRAINT scans_resolved_via_check
  CHECK (resolved_via IN ('barcode', 'fingerprint', 'new_product', 'failed', 'no_barcode', 'screen'));
