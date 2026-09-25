"""
Reviewer accounts (D-097): one login per person instead of one shared token.

Passwords are hashed with scrypt from the standard library (no new dependency):
memory-hard, salted, and slow enough (~50 ms) that a stolen table is costly to
guess through. HTTP Basic sends the password on every request, photos
included, so a verified login is remembered in memory for a few minutes, keyed
by the stored hash: a reset or a disable takes effect on the next request.

    python tools/reviewers.py add asha        # prints a generated password once
"""

import hashlib
import hmac
import re
import secrets
import threading
import time

import psycopg
from psycopg.rows import dict_row

NAME = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")
MIN_PASSWORD = 12
_N, _R, _P = 2 ** 14, 8, 1           # scrypt cost: 16 MiB, ~50 ms here


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(bytes.fromhex(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), digest)


def _check_new(name, password):
    if not NAME.match(name or ""):
        raise ValueError("A reviewer name is 2–32 letters, digits, '.', '_' or '-'.")
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"A password needs at least {MIN_PASSWORD} characters.")


def generate_password():
    return secrets.token_urlsafe(15)                 # 20 characters


# ---------------------------------------------------------------- database

def _connect(conninfo):
    return psycopg.connect(conninfo, row_factory=dict_row)


def add(conninfo, name, password):
    _check_new(name, password)
    with _connect(conninfo) as c:
        if c.execute("SELECT 1 FROM reviewers WHERE name = %s", (name,)).fetchone():
            raise ValueError(f"Reviewer {name!r} already exists; use set_password to change it.")
        c.execute("INSERT INTO reviewers (name, password_hash) VALUES (%s, %s)", (name, hash_password(password)))


def set_password(conninfo, name, password):
    _check_new(name, password)
    with _connect(conninfo) as c:
        r = c.execute("""UPDATE reviewers SET password_hash = %s, password_set_at = now(),
                                active = true, disabled_at = NULL
                          WHERE name = %s RETURNING name""", (hash_password(password), name)).fetchone()
    if r is None:
        raise ValueError(f"No reviewer {name!r}.")


def disable(conninfo, name):
    with _connect(conninfo) as c:
        r = c.execute("""UPDATE reviewers SET active = false, disabled_at = now()
                          WHERE name = %s RETURNING name""", (name,)).fetchone()
    if r is None:
        raise ValueError(f"No reviewer {name!r}.")


def list_all(conninfo):
    with _connect(conninfo) as c:
        return c.execute("""SELECT name, active, created_at, password_set_at, last_login_at
                              FROM reviewers ORDER BY name""").fetchall()


def any_accounts(conninfo):
    """True once the first account exists (from then on the shared token is refused)."""
    try:
        with _connect(conninfo) as c:
            return c.execute("SELECT EXISTS (SELECT 1 FROM reviewers) AS e").fetchone()["e"]
    except psycopg.errors.UndefinedTable:
        return False                     # migration 009 not applied yet: still the shared token


def stored_hash(conninfo, name):
    """The active reviewer's password hash, or None."""
    with _connect(conninfo) as c:
        r = c.execute("SELECT password_hash FROM reviewers WHERE name = %s AND active", (name,)).fetchone()
    return r["password_hash"] if r else None


def touch(conninfo, name):
    with _connect(conninfo) as c:
        c.execute("UPDATE reviewers SET last_login_at = now() WHERE name = %s", (name,))


# ---------------------------------------------------------------- verified-login cache

_CACHE_S = 300
_DUMMY = hash_password(secrets.token_urlsafe(16))
_verified = {}                      # sha256(name, password, stored hash) -> expiry
_lock = threading.Lock()


def check(conninfo, name, password):
    """
    The stored hash when name + password is an active account, else None. The
    hash is returned because it keys the reviewer's form tokens (CSRF): a reset
    changes it, so forms issued before the reset stop working too.
    """
    stored = stored_hash(conninfo, name)
    if stored is None:
        verify_password(password, _DUMMY)          # same time as a wrong password: names don't leak
        return None
    key = hashlib.sha256(f"{name}\0{password}\0{stored}".encode()).hexdigest()
    now = time.monotonic()
    with _lock:
        if _verified.get(key, 0) > now:
            return stored
    if not verify_password(password, stored):
        return None
    with _lock:
        if len(_verified) > 1000:
            _verified.clear()
        _verified[key] = now + _CACHE_S
    touch(conninfo, name)
    return stored
