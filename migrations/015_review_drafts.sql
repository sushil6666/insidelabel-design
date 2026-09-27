-- 015_review_drafts.sql - review agents (D-117): who drafted each published
-- version, where its category came from, and the drafts the agents write.
--
-- verified_by (001) already says who pressed publish: a reviewer's name, or
-- 'agent'. drafted_by says who wrote the category, ingredient lines, claims and
-- note: a reviewer's name, 'claude' (pasted from a Claude session, as on
-- 2026-09-27) or 'gemini' (the D-117 drafter). NULL on versions published
-- before this migration, when nobody recorded it.

ALTER TABLE product_versions
  ADD COLUMN drafted_by      text CHECK (drafted_by ~ '^[A-Za-z0-9_.-]{2,32}$'),
  ADD COLUMN category_source text CHECK (category_source IN ('pack_declared', 'codex_descriptor', 'reviewer'));

-- One row per draft. A draft is written once and never edited: a new prompt
-- or a re-run writes a new row, so what the agents said is always replayable
-- (D-092). model_raw is Gemini's answer exactly as returned.
CREATE TABLE review_drafts (
  id                   bigserial PRIMARY KEY,
  review_item_id       bigint NOT NULL REFERENCES review_queue(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  drafter              text NOT NULL,
  model                text,
  prompt_version       text,
  build                text,
  model_raw            text,
  draft                jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(draft) = 'object'),
  checks               jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(checks) = 'array'),
  outcome              text NOT NULL CHECK (outcome IN ('confirmed', 'needs_person', 'error')),
  error                text,
  mode                 text NOT NULL CHECK (mode IN ('shadow', 'publish')),
  published_version_id bigint REFERENCES product_versions(id)
);
CREATE INDEX review_drafts_item ON review_drafts (review_item_id, created_at DESC);
