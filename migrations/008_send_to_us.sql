-- 008_send_to_us.sql — "Send it to us" (D-070): the app hands a pack it
-- couldn't read to a reviewer, after two refused scans.
--
-- review_queue already had the 'send_to_us' kind and one scan_id (the latest
-- attempt, whose photo is usually the best). The earlier attempts matter too:
-- one may show the part of the label the other lost to glare. They are kept
-- here, in the order they were taken, so the reviewer sees every photo.

ALTER TABLE review_queue
  ADD COLUMN attempt_scan_ids uuid[] NOT NULL DEFAULT '{}';
-- Finding the item again when the same attempts are sent twice.
CREATE INDEX review_queue_attempts ON review_queue USING gin (attempt_scan_ids)
  WHERE kind = 'send_to_us';
