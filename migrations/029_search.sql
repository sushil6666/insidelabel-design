-- 029_search.sql - a pack opened from a search (D-204).
--
-- Search lists published packs by brand, name and variant; tapping one opens the same
-- reviewed result a barcode hit gives, at no AI cost. Its scan row says it came from a
-- search (resolved_via 'search'), so the numbers can tell searches from barcodes.
-- The search words themselves are never stored, with a device id or without one.

ALTER TABLE scans DROP CONSTRAINT scans_resolved_via_check;
ALTER TABLE scans ADD CONSTRAINT scans_resolved_via_check
  CHECK (resolved_via IN ('barcode', 'fingerprint', 'new_product', 'failed', 'no_barcode', 'screen', 'recheck',
                          'side', 'search'));
