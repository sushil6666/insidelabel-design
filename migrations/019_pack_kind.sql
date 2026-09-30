-- 019_pack_kind.sql - the kind of pack on a catalogue version (D-139, D-140).
--
-- core/pack_kind.py decides from the words the pack prints (prompt rule 11) and
-- its licences whether a pack is ordinary food, a health supplement, a food for
-- infants, a food for special dietary or medical use, or not food at all (a
-- drug licence and no FSSAI licence, D-116). The result shows different parts
-- for each, so the catalogue keeps the kind the scan decided, with the printed
-- evidence, for the reviewer to see on /review and for later catalogue hits.
--
-- NULL means the version was stored before D-139: it is read as ordinary food,
-- unless its product's category is 13.x (data/pack_kinds.json).

ALTER TABLE product_versions ADD COLUMN pack_kind text
  CHECK (pack_kind IN ('food', 'supplement', 'infant', 'special_medical', 'not_food'));
ALTER TABLE product_versions ADD COLUMN pack_kind_evidence jsonb;
