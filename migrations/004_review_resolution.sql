-- 004_review_resolution.sql — what a reviewer decided and why.

ALTER TABLE review_queue ADD COLUMN resolution text
  CHECK (resolution IN ('published', 'published_new_version', 'no_change', 'rejected'));
ALTER TABLE review_queue ADD COLUMN resolution_note text;
ALTER TABLE review_queue ADD COLUMN resolved_product_version_id bigint REFERENCES product_versions(id);

-- A finished item always records its outcome.
ALTER TABLE review_queue ADD CONSTRAINT resolved_has_outcome
  CHECK (status NOT IN ('done', 'rejected') OR (resolution IS NOT NULL AND resolved_at IS NOT NULL));

-- D-070: "we'll tell you when it's ready" — the app polls by install id.
CREATE INDEX review_queue_notify ON review_queue (notify_user_id, resolved_at DESC)
  WHERE notify_user_id IS NOT NULL;
