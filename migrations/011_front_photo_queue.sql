-- 011_front_photo_queue.sql - D-100: a front-of-pack photo for a product the
-- catalogue already has, but without its front.
--
-- The front carries the brand's claims and the product's name as it is sold.
-- A published version read from the back alone has neither. When a user adds
-- the front later, it goes to a reviewer as its own kind of item: the
-- ingredients don't change, only the claims and the photo they are read from.
-- The photo is kept by the open item (retention.py holds open items' scans).

ALTER TABLE review_queue DROP CONSTRAINT review_queue_kind_check;
ALTER TABLE review_queue ADD CONSTRAINT review_queue_kind_check
  CHECK (kind IN ('new_product', 'send_to_us', 'correction', 'reformulation', 'front_photo'));
