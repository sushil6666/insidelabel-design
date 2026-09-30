-- 020_barcode_changes.sql - D-142: a product's barcode changes only through a
-- recorded correction.
--
-- Found by the D-141 measurement (2026-09-30): product 42 was published under
-- 4901196008343, the camera scanner's read, while its own back photo reads
-- 8901499008343. The barcode is the catalogue key (D-024), and until now it
-- could be changed by typing another one on the review form, or by SQL, with
-- nothing kept of the old one.
--
-- Every change is a row here: old and new code, who, when, why, and how
-- ('correction': tools/barcodes.py fix; 'review': set while a never-published
-- product was reviewed). The trigger refuses an UPDATE of products.barcode
-- that has no row written in the same transaction, so a direct UPDATE fails.
-- The old code stays here after it leaves products: findable in the audit,
-- never by a scan.

CREATE TABLE barcode_changes (
  id           bigserial PRIMARY KEY,
  product_id   bigint NOT NULL REFERENCES products(id),
  old_barcode  text NOT NULL,
  new_barcode  text NOT NULL CHECK (new_barcode <> old_barcode),
  changed_by   text NOT NULL,
  reason       text NOT NULL CHECK (btrim(reason) <> ''),
  evidence     text,                         -- e.g. the photo key the printed digits were read from
  via          text NOT NULL CHECK (via IN ('correction', 'review')),
  xact         xid8 NOT NULL DEFAULT pg_current_xact_id(),
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX barcode_changes_product ON barcode_changes (product_id);
CREATE INDEX barcode_changes_old ON barcode_changes (old_barcode);
CREATE INDEX barcode_changes_new ON barcode_changes (new_barcode);

CREATE FUNCTION products_barcode_audited() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.barcode IS NOT NULL AND NEW.barcode IS DISTINCT FROM OLD.barcode AND NOT EXISTS (
       SELECT 1 FROM barcode_changes
        WHERE product_id = NEW.id AND old_barcode = OLD.barcode
          AND new_barcode IS NOT DISTINCT FROM NEW.barcode
          AND xact = pg_current_xact_id()) THEN
    RAISE EXCEPTION 'product % barcode % -> %: a barcode changes only with a barcode_changes row (D-142)',
      NEW.id, OLD.barcode, NEW.barcode;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER products_barcode_audited BEFORE UPDATE OF barcode ON products
  FOR EACH ROW EXECUTE FUNCTION products_barcode_audited();
