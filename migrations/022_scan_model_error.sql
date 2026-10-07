-- 022_scan_model_error.sql - D-172: a model failure keeps its own words.
--
-- Problem report #7 (2026-10-07): /scan answered 502 vision_failed twice for a
-- Britannia pack and left nothing to read: model_raw empty, no log line. Re-read
-- on the server, Gemini had blocked its answer (finish reason RECITATION).
--
-- scans.model_error: the error's class and text, first 1000 characters, for every
--   VisionError, VisionUnavailable, VisionConfigError and VisionBlocked. NULL when
--   the model answered, or the scan predates this.
ALTER TABLE scans ADD COLUMN model_error text;
