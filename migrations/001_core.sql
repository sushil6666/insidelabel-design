-- 001_core.sql - beta transactional core (D-020).
--
-- Knowledge tables (additives, allergens, NOVA markers, claim rules, regulator
-- comparison) stay as versioned JSON in data/ for the beta; the engine reads
-- them from there. This schema holds what the app writes: products and their
-- versions, findings with their evidence, scans, corrections and the review queue.
--
-- Rules enforced by the database, not by convention:
--   D-026  product versions are SCD2; at most one current version per product
--   D-027  the raw model output is kept alongside resolved values
--   D-028  a version waiting for review can never be the current catalogue entry
--   D-031  model and engine versions are pinned on every version
--   D-043  a finding with no evidence row cannot be committed
--   D-045  a finding can only cite a verified document
--   D-074  at most 3 profiles per user; no names or birth dates on the server

-- ============ CATALOGUE ============

CREATE TABLE brands (
  id             bigserial PRIMARY KEY,
  name           text NOT NULL UNIQUE,
  parent_company text
);

-- Food categories use the FSSAI / Codex numbering (e.g. '14.1.4', '7.2.1'),
-- so a product's category can later be joined to per-category additive limits.
CREATE TABLE categories (
  id        bigserial PRIMARY KEY,
  code      text NOT NULL UNIQUE,
  name      text NOT NULL,
  parent_id bigint REFERENCES categories(id)
);

CREATE TABLE products (
  id            bigserial PRIMARY KEY,
  barcode       text UNIQUE,                 -- nullable; the cache key once known (D-024)
  brand_id      bigint REFERENCES brands(id),
  name          text NOT NULL,
  variant       text,
  category_id   bigint REFERENCES categories(id),
  net_qty_value numeric,
  net_qty_unit  text,
  scan_count    bigint NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX products_brand_category ON products (brand_id, category_id);

CREATE TABLE product_versions (
  id                 bigserial PRIMARY KEY,
  product_id         bigint NOT NULL REFERENCES products(id),
  version_no         int NOT NULL,

  -- What the label says (D-033: ingredient_lines is the source of truth).
  ingredient_lines   jsonb NOT NULL CHECK (jsonb_typeof(ingredient_lines) = 'array'),
  ingredients        jsonb NOT NULL CHECK (jsonb_typeof(ingredients) = 'array'),
  allergen_statement text,
  front_claims       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(front_claims) = 'array'),
  raw_extraction     jsonb,                  -- D-027: full model output, for re-parsing later

  -- Fingerprints: a changed hash on the same barcode is a reformulation.
  ingredients_hash   text NOT NULL,
  claims_hash        text,
  nutrition_hash     text,

  -- D-031: trace any verdict to the exact model / prompt / engine that produced it.
  model_name         text,
  prompt_version     text,
  engine_version     text NOT NULL,

  source             text NOT NULL CHECK (source IN ('seed', 'scan', 'reviewer')),
  status             text NOT NULL DEFAULT 'pending_review'
                     CHECK (status IN ('pending_review', 'published', 'rejected')),
  verified_by        text,
  verified_at        timestamptz,

  -- D-026 SCD2
  valid_from         timestamptz,
  valid_to           timestamptz,
  is_current         boolean NOT NULL DEFAULT false,

  front_image_key    text,
  back_image_key     text,
  created_at         timestamptz NOT NULL DEFAULT now(),

  UNIQUE (product_id, version_no),
  -- D-028: only a reviewed, published version can be what the catalogue serves.
  CONSTRAINT current_is_published CHECK (NOT is_current OR status = 'published'),
  CONSTRAINT current_is_open CHECK (NOT is_current OR valid_to IS NULL),
  CONSTRAINT published_is_verified CHECK (status <> 'published' OR verified_at IS NOT NULL)
);
CREATE UNIQUE INDEX product_versions_one_current ON product_versions (product_id) WHERE is_current;
CREATE INDEX product_versions_ingredients_hash ON product_versions (ingredients_hash);

-- Publish a reviewed version and close the previous current one, atomically.
CREATE FUNCTION publish_version(p_version_id bigint, p_reviewer text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_product bigint;
BEGIN
  SELECT product_id INTO v_product FROM product_versions
   WHERE id = p_version_id FOR UPDATE;
  IF v_product IS NULL THEN
    RAISE EXCEPTION 'product_version % does not exist', p_version_id;
  END IF;
  -- Lock the product row so two reviewers can't publish at once.
  PERFORM 1 FROM products WHERE id = v_product FOR UPDATE;

  UPDATE product_versions
     SET is_current = false, valid_to = now()
   WHERE product_id = v_product AND is_current;

  UPDATE product_versions
     SET status = 'published', verified_by = p_reviewer, verified_at = now(),
         valid_from = now(), valid_to = NULL, is_current = true
   WHERE id = p_version_id;
END $$;

-- ============ CITATIONS, FINDINGS & EVIDENCE ============

-- D-044: per document, never per institution. D-045: verified_at is NOT NULL,
-- so a finding cannot reference an unverified document at all.
CREATE TABLE citations (
  key           text PRIMARY KEY,          -- e.g. 'FSSAI_FA_XXVI', 'EU_2022_63'
  title         text NOT NULL,
  url           text NOT NULL,
  document_date date,
  verified_at   date NOT NULL,
  verified_by   text
);

CREATE TABLE findings (
  id                 bigserial PRIMARY KEY,
  product_version_id bigint NOT NULL REFERENCES product_versions(id),
  rule_code          text NOT NULL,        -- rule tables are JSON in the beta
  rule_version       text NOT NULL,
  tier               text NOT NULL CHECK (tier IN ('R1', 'R2', 'R3', 'R4', 'R5')),
  kind               text NOT NULL CHECK (kind IN ('fact', 'inference', 'potential_concern',
                                                   'regulatory_context', 'preference', 'uncertainty')),
  severity           text NOT NULL,
  rendered_text      text NOT NULL,        -- rule-generated, passes the D-042 lint
  citation_key       text REFERENCES citations(key),
  engine_version     text NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX findings_version ON findings (product_version_id);

CREATE TABLE evidence (
  id                 bigserial PRIMARY KEY,
  product_version_id bigint NOT NULL REFERENCES product_versions(id),
  kind               text NOT NULL CHECK (kind IN ('ingredient', 'nutrition', 'claim', 'citation')),
  pointer            jsonb NOT NULL,       -- {"ingredient_position": 7} / {"claim_index": 0}
  quoted_text        text,                 -- the label's own words
  image_key          text,
  bbox               jsonb
);

CREATE TABLE finding_evidence (
  finding_id  bigint NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
  evidence_id bigint NOT NULL REFERENCES evidence(id),
  PRIMARY KEY (finding_id, evidence_id)
);

-- D-043: checked at COMMIT, so a finding and its evidence can be inserted in
-- either order inside one transaction, but never committed without evidence.
-- Evidence must also belong to the same product version as the finding.
CREATE FUNCTION assert_finding_has_evidence(v_id bigint) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM findings WHERE id = v_id) THEN
    RETURN;                              -- finding itself deleted; nothing to check
  END IF;
  IF NOT EXISTS (SELECT 1 FROM finding_evidence WHERE finding_id = v_id) THEN
    RAISE EXCEPTION 'finding % has no evidence (D-043)', v_id;
  END IF;
  IF EXISTS (
    SELECT 1 FROM finding_evidence fe
      JOIN evidence e ON e.id = fe.evidence_id
      JOIN findings f ON f.id = fe.finding_id
     WHERE fe.finding_id = v_id AND e.product_version_id <> f.product_version_id
  ) THEN
    RAISE EXCEPTION 'finding % cites evidence from another product version', v_id;
  END IF;
END $$;

CREATE FUNCTION findings_evidence_trigger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM assert_finding_has_evidence(NEW.id);
  RETURN NULL;
END $$;

CREATE FUNCTION finding_evidence_link_trigger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM assert_finding_has_evidence(OLD.finding_id);
  IF TG_OP = 'UPDATE' THEN
    PERFORM assert_finding_has_evidence(NEW.finding_id);
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER findings_need_evidence
  AFTER INSERT OR UPDATE ON findings
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION findings_evidence_trigger();

CREATE CONSTRAINT TRIGGER finding_evidence_removed
  AFTER DELETE OR UPDATE ON finding_evidence
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION finding_evidence_link_trigger();

-- What a consumer surface may read: citations re-verified within 18 months.
CREATE VIEW consumer_findings AS
SELECT f.*
  FROM findings f
  LEFT JOIN citations c ON c.key = f.citation_key
 WHERE f.citation_key IS NULL
    OR c.verified_at > (now() - interval '18 months')::date;

-- ============ USERS, PROFILES & SCANS ============

-- Beta: an anonymous install id. No name, no email, no phone (PII minimisation).
CREATE TABLE users (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  tier       text NOT NULL DEFAULT 'free'
);

-- D-074: nickname stays on the device; the server sees an id and an age band.
CREATE TABLE user_profiles (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  age_band           text NOT NULL CHECK (age_band IN ('toddler', 'kid', 'young', 'adult', 'older')),
  allergen_codes     text[] NOT NULL DEFAULT '{}',
  strict_may_contain boolean NOT NULL DEFAULT true,
  consent_at         timestamptz NOT NULL,           -- parental consent at creation
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION check_profile_limit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM users WHERE id = NEW.user_id FOR UPDATE;   -- serialise per user
  IF (SELECT count(*) FROM user_profiles WHERE user_id = NEW.user_id) >= 3 THEN
    RAISE EXCEPTION 'a user can have at most 3 profiles in the beta (D-074)';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER user_profiles_limit BEFORE INSERT ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION check_profile_limit();

CREATE TABLE scans (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid REFERENCES users(id),
  product_version_id bigint REFERENCES product_versions(id),   -- null when the scan failed
  resolved_via       text NOT NULL CHECK (resolved_via IN ('barcode', 'fingerprint', 'new_product', 'failed')),
  cache_hit          boolean NOT NULL DEFAULT false,
  outcome            text NOT NULL CHECK (outcome IN ('verdict', 'refused', 'vision_unavailable', 'vision_failed')),
  error_code         text,                 -- reliability error when refused
  front_image_key    text,
  back_image_key     text,
  latency_ms         int,
  ai_cost_paise      int,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT verdict_has_version CHECK (outcome <> 'verdict' OR product_version_id IS NOT NULL)
);
CREATE INDEX scans_user_time ON scans (user_id, created_at DESC);
CREATE INDEX scans_version_time ON scans (product_version_id, created_at DESC);

-- D-076 "Report a mistake" on every result.
CREATE TABLE corrections (
  id                 bigserial PRIMARY KEY,
  scan_id            uuid REFERENCES scans(id),
  product_version_id bigint REFERENCES product_versions(id),
  user_id            uuid REFERENCES users(id),
  field              text NOT NULL,
  proposed_value     text,
  note               text,
  status             text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'accepted', 'rejected', 'duplicate')),
  reviewed_by        text,
  reviewed_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);

-- ============ REVIEW QUEUE (D-028, D-070, D-073) ============

CREATE TABLE review_queue (
  id                 bigserial PRIMARY KEY,
  kind               text NOT NULL CHECK (kind IN ('new_product', 'send_to_us', 'correction', 'reformulation')),
  scan_id            uuid REFERENCES scans(id),
  product_version_id bigint REFERENCES product_versions(id),
  correction_id      bigint REFERENCES corrections(id),
  notify_user_id     uuid REFERENCES users(id),   -- D-070: show the result on next open
  status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'claimed', 'done', 'rejected')),
  claimed_by         text,
  claimed_at         timestamptz,
  resolved_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT has_subject CHECK (scan_id IS NOT NULL OR product_version_id IS NOT NULL OR correction_id IS NOT NULL)
);
CREATE INDEX review_queue_open ON review_queue (created_at) WHERE status = 'open';

-- Hand the oldest open item to one reviewer. SKIP LOCKED lets several
-- reviewers pull from the queue at once without ever getting the same item.
CREATE FUNCTION claim_next_review(p_reviewer text)
RETURNS SETOF review_queue LANGUAGE sql AS $$
  UPDATE review_queue q
     SET status = 'claimed', claimed_by = p_reviewer, claimed_at = now()
   WHERE q.id = (
     SELECT id FROM review_queue
      WHERE status = 'open'
      ORDER BY created_at, id
      LIMIT 1
      FOR UPDATE SKIP LOCKED)
  RETURNING q.*;
$$;
