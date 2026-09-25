-- 005_provenance_and_leads.sql — where a record came from (D-088, D-089).
--
-- A marketplace listing (Flipkart, Amazon, Blinkit, Zepto, Swiggy Instamart…)
-- is a *lead*: it tells us a product exists and is worth adding. It is never
-- the source of a catalogue record. The canonical record is read from the
-- physical pack — front and back label — and goes through review (D-028).
--
-- Rules enforced here:
--   D-089  only a version read from a physical label can be published
--   D-089  a lead can only be marked 'label_captured' / 'published' once it is
--          linked to a version read from a physical label

-- ============ PROVENANCE ON EVERY VERSION ============

-- Every version made so far came from photos of real packs, hence the default.
ALTER TABLE product_versions ADD COLUMN production_source text NOT NULL DEFAULT 'physical_label'
  CHECK (production_source IN ('physical_label', 'marketplace_listing'));
ALTER TABLE product_versions ADD CONSTRAINT published_is_physical_label
  CHECK (status <> 'published' OR production_source = 'physical_label');

-- ============ LEADS ============

CREATE TABLE product_leads (
  id                 bigserial PRIMARY KEY,

  -- What the listing says the product is: enough to go and buy the right pack.
  product            text NOT NULL,
  brand              text,
  variant            text,
  net_quantity       text,
  barcode            text,

  source_type        text NOT NULL DEFAULT 'marketplace_reference'
                     CHECK (source_type IN ('marketplace_reference', 'user_share', 'store_visit', 'open_data_reference')),
  source_platform    text CHECK (source_platform IN
                       ('Flipkart', 'Amazon', 'Blinkit', 'Zepto', 'Swiggy Instamart',
                        'BigBasket', 'JioMart', 'Open Food Facts', 'Other')),
  source_url         text,
  -- Private research evidence only: a content hash of the screenshot kept in
  -- research/. Never served by the API, never shown to users, never read into
  -- a catalogue record.
  screenshot_sha256  text CHECK (screenshot_sha256 ~ '^[0-9a-f]{64}$'),
  captured_on        date NOT NULL DEFAULT current_date,
  noted_by           text NOT NULL,
  notes              text,

  production_source  text NOT NULL DEFAULT 'physical_label' CHECK (production_source = 'physical_label'),
  evidence_status    text NOT NULL DEFAULT 'needs_primary_source'
                     CHECK (evidence_status IN ('needs_primary_source', 'pack_obtained',
                                                'label_captured', 'published', 'abandoned')),
  product_version_id bigint REFERENCES product_versions(id),
  status_note        text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT captured_has_version CHECK (
    evidence_status NOT IN ('label_captured', 'published') OR product_version_id IS NOT NULL),
  CONSTRAINT abandoned_has_reason CHECK (evidence_status <> 'abandoned' OR status_note IS NOT NULL)
);
CREATE INDEX product_leads_status ON product_leads (evidence_status, created_at);
CREATE INDEX product_leads_barcode ON product_leads (barcode) WHERE barcode IS NOT NULL;
CREATE UNIQUE INDEX product_leads_screenshot ON product_leads (screenshot_sha256)
  WHERE screenshot_sha256 IS NOT NULL;

-- A lead can only be closed by a version read from a physical label.
CREATE FUNCTION lead_version_is_physical() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.product_version_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM product_versions
        WHERE id = NEW.product_version_id AND production_source = 'physical_label') THEN
    RAISE EXCEPTION 'lead % can only be linked to a version read from a physical label', NEW.id;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER product_leads_physical BEFORE INSERT OR UPDATE ON product_leads
  FOR EACH ROW EXECUTE FUNCTION lead_version_is_physical();

-- When the linked version (or a later version of the same product) is
-- published, the lead is done.
CREATE FUNCTION close_leads_on_publish() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'published' AND OLD.status IS DISTINCT FROM 'published' THEN
    UPDATE product_leads l
       SET evidence_status = 'published'
      FROM product_versions lv
     WHERE lv.id = l.product_version_id
       AND lv.product_id = NEW.product_id
       AND l.evidence_status = 'label_captured';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER product_versions_close_leads AFTER UPDATE OF status ON product_versions
  FOR EACH ROW EXECUTE FUNCTION close_leads_on_publish();
