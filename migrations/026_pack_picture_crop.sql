-- 026_pack_picture_crop.sql - the crop a reviewer drew on a pack picture (D-186).
--
-- A shopper's front photo can show the pack in a hand over a floor; a reviewer on
-- /review may crop it to the pack before it becomes the pack picture. The rectangle
-- is kept as {"left", "top", "width", "height"}: fractions 0 to 1 of the photo after
-- its EXIF rotation, the image the reviewer saw. NULL means the photo was used whole
-- (every row before this one). The small copy under image_key is already cropped;
-- the shopper's original is not changed and still goes at 30 days (D-080, D-098).

ALTER TABLE pack_pictures ADD COLUMN crop jsonb;
