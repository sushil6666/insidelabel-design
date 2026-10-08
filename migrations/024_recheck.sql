-- 024_recheck.sql - a published pack is checked again against the real pack (D-175).
--
-- Brands change recipes under the same barcode. A barcode hit on a pack last
-- checked more than 15 days ago offers one optional photo of the ingredient list.
-- That photo is compared with the published list for free first (the text Cloud
-- Vision, or Tesseract, reads from it); only when it isn't clearly the same does
-- the paid read run, exactly the normal photo path.
--
-- last_verified_at: when a photo of the pack last matched this version, by the
-- free comparison or by a paid read with the same ingredients hash. NULL until
-- then. Nothing else on the version changes when a photo matches. The "last
-- check" is the newer of verified_at (publish, a person) and this (a machine
-- check); the result names them apart, never as one "checked" date.
--
-- resolved_via 'recheck': a scan whose photo matched the published version for
-- free. No model call, no review item, no new version; its trace keeps the text
-- and the decision (D-092).

ALTER TABLE product_versions ADD COLUMN last_verified_at timestamptz NULL;

ALTER TABLE scans DROP CONSTRAINT scans_resolved_via_check;
ALTER TABLE scans ADD CONSTRAINT scans_resolved_via_check
  CHECK (resolved_via IN ('barcode', 'fingerprint', 'new_product', 'failed', 'no_barcode', 'screen', 'recheck'));
