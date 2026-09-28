-- 016_unlink_after_30_days.sql - D-128: keep what a scan read, not who scanned it.
--
-- After 30 days the daily retention job removes a scan's link to its install id
-- (user_id) and the household profiles from its request, and stamps unlinked_at.
-- What the label said stays. A scan held for a problem report or "send it to
-- us" keeps its link until the hold ends, and at most 12 months.
--
-- device_days keeps the one thing the beta needs from the link: on which days
-- each install scanned, and how many times (D-055's W4 retention). It goes
-- with the install id, 12 months after the device was last seen.

ALTER TABLE scans ADD COLUMN unlinked_at timestamptz;
CREATE INDEX scans_unlink ON scans (created_at) WHERE unlinked_at IS NULL;

CREATE TABLE device_days (
  user_id  uuid NOT NULL REFERENCES users(id),
  day      date NOT NULL,
  scans    int NOT NULL CHECK (scans > 0),
  PRIMARY KEY (user_id, day)
);
