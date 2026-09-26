-- 009_reviewers.sql - one login per reviewer (D-097).
--
-- Until now the reviewer screen had one shared password (INSIDELABEL_REVIEW_TOKEN)
-- and the username was whatever the reviewer typed: every decision carried a
-- name nobody had proved, one leaked password opened the whole screen, and
-- removing one person meant changing it for everyone. Decisions already store
-- the reviewer's name (claimed_by, published_by…); this makes the name mean
-- something.

CREATE TABLE reviewers (
  name           text PRIMARY KEY CHECK (name ~ '^[A-Za-z0-9_.-]{2,32}$'),
  password_hash  text NOT NULL,              -- scrypt$N$r$p$salt$hash, never the password
  active         boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  password_set_at timestamptz NOT NULL DEFAULT now(),
  disabled_at    timestamptz,
  last_login_at  timestamptz
);
