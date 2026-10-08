-- 025_pack_pictures.sql - the pack picture (D-182).
--
-- A real photo of the pack's front, shown on every result for its barcode,
-- including a barcode-only hit where the shopper took no photo. It is a small
-- copy (480 px JPEG, no metadata), made when a person on /review approves it:
--   reviewer_upload  a photo a reviewer uploaded on /review/pictures;
--   shopper_photo    a shopper's front photo, ticked on a review item, from a
--                    scan whose install agreed to the terms that say so
--                    (data/terms.json 2026-10-08, Sushil's "Shoppers too").
-- The copy has its own key, so the shopper's own photo still goes at 30 days
-- (D-080, D-098); the copy is the pack's, like a catalogue version's photos.
-- It is never read for findings (D-004). The newest one not removed is shown.

CREATE TABLE pack_pictures (
  id           bigserial PRIMARY KEY,
  product_id   bigint NOT NULL REFERENCES products(id),
  image_key    text NOT NULL,
  source       text NOT NULL CHECK (source IN ('reviewer_upload', 'shopper_photo')),
  scan_id      uuid REFERENCES scans(id) ON DELETE SET NULL,   -- shopper_photo: where it came from
  taken_on     date NOT NULL,
  approved_by  text NOT NULL,
  approved_at  timestamptz NOT NULL DEFAULT now(),
  removed_by   text,
  removed_at   timestamptz,
  CHECK ((removed_at IS NULL) = (removed_by IS NULL))
);
CREATE INDEX pack_pictures_shown ON pack_pictures (product_id, approved_at DESC) WHERE removed_at IS NULL;
CREATE INDEX pack_pictures_key ON pack_pictures (image_key) WHERE removed_at IS NULL;
