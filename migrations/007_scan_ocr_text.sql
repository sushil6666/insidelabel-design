-- 007_scan_ocr_text.sql - the independent reader's text on every scan row, so a
-- replay is exact (D-092, D-093).
--
-- Migration 006 kept the model's raw answer on each scan, but not what the
-- independent OCR read. Replaying a scan therefore called Cloud Vision again:
-- a paid call, a different answer if Google's model changed, and no answer at
-- all when the photo has gone (D-080) or was left out of a saved regression.
-- The OCR text is part of the input that fixed the result, like model_raw.
--
-- Shape: {"back": {"reader": "cloud_vision", "text": "..."}}. A Tesseract read
-- keeps only its reader: its check votes over several passes, so one text
-- wouldn't replay it, and re-running Tesseract locally costs nothing.
-- '{}' means no OCR ran, or the scan predates this migration.

ALTER TABLE scans
  ADD COLUMN ocr jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(ocr) = 'object');
