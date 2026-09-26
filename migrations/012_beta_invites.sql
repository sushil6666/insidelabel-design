-- 012_beta_invites.sql - the invite-only web beta (D-102).
--
-- The beta is a retention test with ~50 named testers (D-007, D-055). One code
-- per tester: it lets them in, and it ties their installs, scans and feedback
-- together, so "did this person come back in week 4?" has an answer even when
-- they use a phone and a laptop. The label is how Sushil knows the tester
-- ("T07", a first name); the app never shows it and the server never sends it.

CREATE TABLE invites (
  code         text PRIMARY KEY CHECK (code ~ '^[A-HJKMNP-Z2-9]{8}$'),   -- no 0/O, 1/I/L
  label        text,
  max_devices  smallint NOT NULL DEFAULT 3 CHECK (max_devices > 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  revoked_at   timestamptz
);

-- An install belongs to one tester.
CREATE TABLE invite_devices (
  user_id    uuid PRIMARY KEY REFERENCES users(id),
  code       text NOT NULL REFERENCES invites(code),
  joined_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invite_devices_code ON invite_devices (code);

-- "Send feedback" in the app. Separate from "Report a mistake" (wrong content,
-- to reviewers, D-076) and "Report a problem" (the app broke, D-092): this is
-- what the tester thinks.
CREATE TABLE feedback (
  id           bigserial PRIMARY KEY,
  user_id      uuid REFERENCES users(id),
  invite_code  text REFERENCES invites(code),
  rating       smallint CHECK (rating BETWEEN 1 AND 5),
  comment      text NOT NULL CHECK (length(comment) BETWEEN 1 AND 4000),
  screen       text,                  -- where it was sent from: home, result…
  app_version  text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feedback_created ON feedback (created_at DESC);
