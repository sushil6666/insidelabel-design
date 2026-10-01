"""
D-148: /.well-known/assetlinks.json, the Play app's link to this site. Chrome
drops the address bar only when the served statement names the package and the
SHA-256 of the certificate that signed the installed build. A missing or
malformed data/assetlinks.json must give a 404, never a 500 or a half statement.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from insidelabel.api import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD = ":".join(["AB"] * 32)
GOOGLE = ":".join(["0F"] * 32)
client = TestClient(main.app)


def _serve(monkeypatch, tmp_path, content):
    path = tmp_path / "assetlinks.json"
    if content is not None:
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    monkeypatch.setattr(main, "ASSETLINKS_FILE", str(path))
    return client.get("/.well-known/assetlinks.json")


def _data(*prints, package="ai.insidelabel.app.f"):
    return {"package_name": package, "fingerprints": [{"sha256": p} for p in prints]}


def test_serves_the_package_and_every_listed_fingerprint(monkeypatch, tmp_path):
    r = _serve(monkeypatch, tmp_path, _data(UPLOAD, GOOGLE))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": "ai.insidelabel.app.f",
                   "sha256_cert_fingerprints": [UPLOAD, GOOGLE]}}]


@pytest.mark.parametrize("content", [
    None,                                              # no file
    "",                                                # empty file
    "{not json",                                       # broken JSON
    "[]",                                              # wrong shape
    {"package_name": "ai.insidelabel.app.f"},          # no fingerprints key
    _data(),                                           # no fingerprints yet
    _data(UPLOAD, package=""),                         # no package
    _data(UPLOAD.lower()),                             # lower case: not how keytool prints it
    _data(UPLOAD[:-3]),                                # 31 pairs
    _data(UPLOAD.replace(":", "")),                    # no colons
    _data(UPLOAD, "SHA256: " + GOOGLE),                # one good, one pasted with its label
    {"package_name": "ai.insidelabel.app.f", "fingerprints": [UPLOAD]},  # rows, not strings
])
def test_missing_or_malformed_is_a_404_never_a_500(monkeypatch, tmp_path, content):
    r = _serve(monkeypatch, tmp_path, content)
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_the_committed_file_names_the_play_package_and_only_well_formed_fingerprints():
    # D-149: the package can never change. A bad paste must fail here, not as a
    # silent 404 on the server (the address bar would just come back).
    with open(os.path.join(ROOT, "data", "assetlinks.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["package_name"] == "ai.insidelabel.app.f"
    for row in data["fingerprints"]:
        assert main._SHA256_FINGERPRINT.match(row["sha256"]), row
    assert len({r["sha256"] for r in data["fingerprints"]}) == len(data["fingerprints"])


def test_the_committed_file_is_what_the_route_reads():
    assert main.ASSETLINKS_FILE.endswith(os.path.join("data", "assetlinks.json"))


def test_the_privacy_url_given_to_play_is_served():
    # Play Console's privacy policy URL is https://insidelabel.ai/privacy.html.
    r = client.get("/privacy.html")
    assert r.status_code == 200
    assert r.text == client.get("/privacy").text
