-- 013_agreements.sql - "Before you start" (D-105).
--
-- Correct data comes first in the beta. Before a first scan every tester
-- agrees to photograph only real packs, never AI-made or edited pictures or
-- screenshots, and that they are a person, not a program. The agreement is
-- the rule a reviewer points to when removing made-up data or closing an
-- invite. One row per install per version of the text (data/terms.json);
-- a new version asks everyone again.

CREATE TABLE agreements (
  user_id        uuid NOT NULL REFERENCES users(id),
  terms_version  text NOT NULL,
  agreed_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, terms_version)
);
