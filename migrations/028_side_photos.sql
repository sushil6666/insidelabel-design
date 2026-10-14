-- 028_side_photos.sql - a photo of a tin's side, for the notices FSSAI's rules ask for (D-201).
--
-- An infant pack's result names the notices regulation 4 asks for that we didn't see on
-- the scan's photos; tins and boxes often print them on a side. "Photograph the side"
-- adds one photo (at most two) to that result. It is read by Cloud Vision only (Tesseract
-- when Vision is off), never by the model, and only regulation 4's statements are looked
-- for in its text.
--
-- resolved_via 'side', outcome 'side_photo': the photo's own scan row, so it replays
-- (D-092): the trace keeps the text, the reader and which statements it found.
-- parent_scan_id: the scan whose result it added to, so /review shows it beside that
-- scan. A side photo never changes a catalogue version and never creates a review item
-- (Sushil, accepting D-201): no product_version_id is set on its row.

ALTER TABLE scans ADD COLUMN parent_scan_id uuid NULL REFERENCES scans(id) ON DELETE SET NULL;
CREATE INDEX scans_parent ON scans (parent_scan_id) WHERE parent_scan_id IS NOT NULL;

ALTER TABLE scans DROP CONSTRAINT scans_resolved_via_check;
ALTER TABLE scans ADD CONSTRAINT scans_resolved_via_check
  CHECK (resolved_via IN ('barcode', 'fingerprint', 'new_product', 'failed', 'no_barcode', 'screen', 'recheck',
                          'side'));

ALTER TABLE scans DROP CONSTRAINT scans_outcome_check;
ALTER TABLE scans ADD CONSTRAINT scans_outcome_check
  CHECK (outcome IN ('verdict', 'refused', 'vision_unavailable', 'vision_failed', 'unlisted', 'screen_read',
                     'side_photo'));
