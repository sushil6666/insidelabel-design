-- 023_review_table_reads.sql - D-174: the nutrition table of a pack sent to us.
--
-- Item #71 (2026-10-07): a "send it to us" item held the table photo, but nothing
-- read it, so the pack was published without its table and the next scan asked the
-- user to photograph it again (D-168, item #72).
--
-- One row per attempt to read an item's table, written once and never edited
-- (D-092), failures included:
--   source          'stored_answer' (an earlier model answer of the item's scans,
--                   checked again: no new read) or 'table_read' (the table-only prompt)
--   scan_id         the scan whose photo and answer were used
--   model_raw       the model's answer as returned (or the D-172 blocked marker)
--   model_error     the error's class and text when the read failed (D-172)
--   ocr_reader, ocr_text   the second reading nutrition.check() used (D-133)
--   panel           nutrition.check()'s result: what a reviewer may publish
CREATE TABLE review_table_reads (
  id              bigserial PRIMARY KEY,
  review_item_id  bigint NOT NULL REFERENCES review_queue(id),
  scan_id         uuid REFERENCES scans(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  source          text NOT NULL CHECK (source IN ('stored_answer', 'table_read')),
  model           text,
  prompt_version  text,
  build           text,
  model_raw       text,
  model_error     text,
  ocr_reader      text,
  ocr_text        text,
  panel           jsonb,
  requested_by    text
);
CREATE INDEX review_table_reads_item ON review_table_reads (review_item_id, created_at DESC);
