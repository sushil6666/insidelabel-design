-- 003_ingredient_findings.sql
--
-- D-040's tiers R1-R5 classify claim and regulatory rules. The engine's
-- per-ingredient additive flags (additives.json rows) are ingredient facts and
-- belong to none of them, so they get their own tier code, 'ING'. NOVA markers
-- stay R3 (definitional).

ALTER TABLE findings DROP CONSTRAINT findings_tier_check;
ALTER TABLE findings ADD CONSTRAINT findings_tier_check
  CHECK (tier IN ('R1', 'R2', 'R3', 'R4', 'R5', 'ING'));

-- Lookups the scan path makes on every request.
CREATE INDEX product_versions_pending
  ON product_versions (product_id, ingredients_hash) WHERE status = 'pending_review';
