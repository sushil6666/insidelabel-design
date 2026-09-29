-- 018_nutrition_table.sql - the nutrition table on a catalogue version (D-133).
--
-- The vision model copies the table; lenses/nutrition.py keeps only the numbers
-- the second reading of the same photo and the table's own arithmetic agree on.
-- That checked table is stored on the version the scan creates or waits on. A
-- reviewer confirms it against the photo on /review before it is published
-- (publish records who confirmed it); an unconfirmed table is published as NULL.
--
-- A pack published before D-133 has no table. When a later scan reads one, the
-- scan makes a new version with the same content and the table, waiting for
-- review as kind 'nutrition', so the table goes through the same review and
-- history as any other change.

ALTER TABLE product_versions ADD COLUMN nutrition jsonb;

ALTER TABLE review_queue DROP CONSTRAINT review_queue_kind_check;
ALTER TABLE review_queue ADD CONSTRAINT review_queue_kind_check
  CHECK (kind IN ('new_product', 'send_to_us', 'correction', 'reformulation', 'front_photo', 'nutrition'));
