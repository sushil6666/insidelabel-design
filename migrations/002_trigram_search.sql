-- requires-extension: pg_trgm
-- 002_trigram_search.sql - fuzzy product-name search (D-020, D-059 free name search).
-- Needs the postgresql-contrib package. The embedded test server lacks it, so
-- the migration runner skips this file there (and records nothing); it applies
-- on any real Postgres install.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX products_name_trgm ON products USING gin (name gin_trgm_ops);
