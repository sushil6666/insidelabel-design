-- 021_barcode_check.sql - D-143: a barcode sent with a scan is set against the
-- scan's own photos and OCR text, and a reviewer checks one nothing else shows.
--
-- The camera scanner takes a code seen in two frames of one view; the same blur
-- can give the same wrong code twice. Product 42 was published under the
-- camera's 4901196008343 while its back photo reads 8901499008343 (D-142).
--
-- scans.barcode_check: barcode.confirm()'s answer plus where the code came from,
--   {"code", "status": confirmed | mismatch | not_shown, "photo_codes", "ocr_codes", "source"}.
--   NULL: no barcode, no photo, or the scan predates this.
-- review_queue.barcode_checked_by: the reviewer who ticked that they checked a
--   barcode the photos didn't confirm, before publishing it.

ALTER TABLE scans ADD COLUMN barcode_check jsonb
  CHECK (barcode_check IS NULL OR jsonb_typeof(barcode_check) = 'object');
ALTER TABLE review_queue ADD COLUMN barcode_checked_by text;
