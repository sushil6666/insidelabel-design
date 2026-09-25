-- 006_problem_reports.sql — every scan can be reproduced, and users can say
-- when something broke (D-092).
--
-- A scan's result is fixed by: the photos (media store), the model's raw
-- answer, the request options, the code (build) and the data tables
-- (data_version). Until now the raw answer lived only on a product version,
-- which is shared by identical scans and doesn't exist at all for a refused or
-- failed scan, the cases most worth debugging. So each scan row now keeps its
-- own copy.
--
-- "Report a problem" is not "Report a mistake" (D-076): a mistake is wrong
-- content and goes to reviewers; a problem is the app misbehaving and goes to
-- the developer. Different table, different queue.

-- ============ TRACE ON EVERY SCAN ============

ALTER TABLE scans
  ADD COLUMN request_id     text,           -- X-Request-ID; also in the phone's event trail
  ADD COLUMN build          text,           -- git commit the server ran
  ADD COLUMN data_version   text,           -- hash of data/*.json
  ADD COLUMN engine_version text,
  ADD COLUMN prompt_version text,
  ADD COLUMN model_raw      text,           -- the model's answer exactly as returned, before any correction
  ADD COLUMN request        jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(request) = 'object'),
                                            -- options sent: barcode, profiles (ref/age/avoid only), pairing…
  ADD COLUMN timings        jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(timings) = 'object'),
  -- D-080: user originals are deleted at 30 days "unless flagged". A problem
  -- report flags them, so the evidence outlives the retention rule.
  ADD COLUMN evidence_hold  boolean NOT NULL DEFAULT false;
CREATE INDEX scans_request_id ON scans (request_id);

-- ============ PROBLEM REPORTS ============

CREATE TABLE problem_reports (
  id            bigserial PRIMARY KEY,
  kind          text NOT NULL CHECK (kind IN ('user', 'auto', 'server')),
                -- user: tapped "Report a problem"; auto: an app crash; server: an unhandled exception
  user_id       uuid REFERENCES users(id),
  scan_id       uuid REFERENCES scans(id),
  request_id    text,                        -- the request that failed, when known
  comment       text,
  app_version   text,
  build         text,                        -- server build and data when the report arrived
  data_version  text,
  client        jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(client) = 'object'),
                -- phone, browser, screen, network, feature support; never nicknames (D-074)
  events        jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(events) = 'array'),
                -- the phone's trail: screens, API calls with request ids, errors
  server_error  text,                        -- traceback, for kind 'server'
  signature     text,                        -- error class + place, to group repeats
  status        text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'reproduced', 'fixed', 'not_a_bug', 'duplicate')),
  note          text,                        -- the developer's finding
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX problem_reports_open ON problem_reports (created_at DESC) WHERE status = 'open';
CREATE INDEX problem_reports_signature ON problem_reports (signature);
