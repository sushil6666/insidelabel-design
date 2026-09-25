"""
Individual reviewer logins (D-097): each reviewer has their own password, so a
decision is tied to a person, one person can be locked out without resetting
everyone, and a leaked password is one account, not the whole screen.

The shared INSIDELABEL_REVIEW_TOKEN only works while no account exists (to
create the first one without being locked out); after that it is refused.
"""
import base64
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.review import accounts, routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

TOKEN = "shared-token-xyz"


@pytest.fixture(scope="module")
def env(fresh_db):
    uri = fresh_db[0]
    saved = routes.SERVICE
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    yield uri
    mp.undo()
    routes.SERVICE = saved


def client(name, password):
    cred = base64.b64encode(f"{name}:{password}".encode()).decode()
    return TestClient(main.app, headers={"Authorization": f"Basic {cred}"})


def csrf(page_html):
    return re.search(r'name="csrf" value="([0-9a-f]+)"', page_html).group(1)


def test_passwords_are_hashed():
    h = accounts.hash_password("correct horse battery")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert accounts.verify_password("correct horse battery", h)
    assert not accounts.verify_password("correct horse", h)
    assert accounts.hash_password("correct horse battery") != h          # salted


def test_the_shared_token_works_only_until_the_first_account(env):
    assert client("asha", TOKEN).get("/review").status_code == 200       # bootstrap
    accounts.add(env, "asha", "asha-password-1")
    assert client("asha", TOKEN).get("/review").status_code == 401       # now refused
    assert client("ravi", TOKEN).get("/review").status_code == 401
    assert client("asha", "asha-password-1").get("/review").status_code == 200


def test_each_reviewer_has_their_own_password(env):
    accounts.add(env, "ravi", "ravi-password-1")
    assert client("ravi", "ravi-password-1").get("/review").status_code == 200
    assert client("ravi", "asha-password-1").get("/review").status_code == 401   # not someone else's
    assert client("nobody", "ravi-password-1").get("/review").status_code == 401


def test_a_disabled_reviewer_is_locked_out(env):
    accounts.add(env, "meena", "meena-password-1")
    assert client("meena", "meena-password-1").get("/review").status_code == 200
    accounts.disable(env, "meena")
    assert client("meena", "meena-password-1").get("/review").status_code == 401
    assert client("asha", "asha-password-1").get("/review").status_code == 200  # nobody else is


def test_a_reset_password_replaces_the_old_one_at_once(env):
    accounts.add(env, "kiran", "kiran-password-1")
    old = client("kiran", "kiran-password-1")
    page = old.get("/review").text                                      # the verified login is cached…
    accounts.set_password(env, "kiran", "kiran-password-2")
    assert old.get("/review").status_code == 401                        # …but not past a reset
    new = client("kiran", "kiran-password-2")
    assert new.get("/review").status_code == 200
    # A form token from before the reset is no longer accepted.
    assert new.post("/review/claim-next", data={"csrf": csrf(page)}).status_code == 403


def test_form_tokens_are_per_reviewer(env):
    a, r = client("asha", "asha-password-1"), client("ravi", "ravi-password-1")
    assert r.post("/review/claim-next", data={"csrf": csrf(a.get("/review").text)}).status_code == 403
    assert a.post("/review/claim-next", data={"csrf": csrf(a.get("/review").text)},
                  follow_redirects=False).status_code == 303


def test_guessing_is_slowed_down(env):
    accounts.add(env, "sunil", "sunil-password-1")
    codes = [client("sunil", f"guess-{i}").get("/review").status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    # Locked for a while even with the right password: the guesser can't tell.
    assert client("sunil", "sunil-password-1").get("/review").status_code == 429
    assert client("asha", "asha-password-1").get("/review").status_code == 200    # others unaffected


def test_short_passwords_and_bad_names_are_refused(env):
    with pytest.raises(ValueError):
        accounts.add(env, "tiny", "short")
    with pytest.raises(ValueError):
        accounts.add(env, "bad name!", "long-enough-password")
    with pytest.raises(ValueError):
        accounts.add(env, "asha", "another-password-1")                 # already exists


def test_the_cli_adds_lists_and_disables(env, capsys, monkeypatch):
    import importlib.util
    import os
    spec = importlib.util.spec_from_file_location(
        "reviewers_cli", os.path.join(os.path.dirname(__file__), "..", "tools", "reviewers.py"))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.main(["--db", env, "add", "neha"])                              # no password given: one is made
    out = capsys.readouterr().out
    pw = re.search(r"password: (\S+)", out).group(1)
    assert len(pw) >= 16
    assert client("neha", pw).get("/review").status_code == 200
    cli.main(["--db", env, "list"])
    assert re.search(r"neha\s+active", capsys.readouterr().out)
    cli.main(["--db", env, "disable", "neha"])
    assert client("neha", pw).get("/review").status_code == 401


def test_decisions_carry_the_reviewers_own_name(env):
    uri = env
    with psycopg.connect(uri) as c:
        vid = None
        pid = c.execute("INSERT INTO products (name) VALUES ('Login Test') RETURNING id").fetchone()[0]
        vid = c.execute(
            """INSERT INTO product_versions (product_id, version_no, ingredient_lines, ingredients,
                                             ingredients_hash, engine_version, source)
               VALUES (%s, 1, '["Sugar"]', '["Sugar"]', %s, '0.1', 'scan') RETURNING id""",
            (pid, uuid.uuid4().hex)).fetchone()[0]
        c.execute("INSERT INTO review_queue (kind, product_version_id) VALUES ('new_product', %s)", (vid,))
    a = client("asha", "asha-password-1")
    r = a.post("/review/claim-next", data={"csrf": csrf(a.get("/review").text)}, follow_redirects=False)
    item = int(r.headers["location"].rsplit("/", 1)[1])
    with psycopg.connect(uri) as c:
        assert c.execute("SELECT claimed_by FROM review_queue WHERE id = %s", (item,)).fetchone()[0] == "asha"


def test_a_database_without_migration_009_keeps_the_shared_token(env, monkeypatch):
    # The code can reach a server before its migration does; /review must not 500.
    with psycopg.connect(env) as c:
        c.execute("ALTER TABLE reviewers RENAME TO reviewers_hidden")
    try:
        assert client("asha", TOKEN).get("/review").status_code == 200
    finally:
        with psycopg.connect(env) as c:
            c.execute("ALTER TABLE reviewers_hidden RENAME TO reviewers")
    assert client("asha", TOKEN).get("/review").status_code == 401
