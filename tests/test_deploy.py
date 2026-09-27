"""
The deploy files (D-114) keep the server's safety settings. A settings file is
easy to edit in a hurry; these are the lines that must not drift:

- invite-only on (D-102), one proxy hop (D-095), the public address;
- replay, the claim check and the shared review token never switched on
  (D-101, D-051, D-097);
- no key values in the repo (CLAUDE.md: keys live in the environment only);
- exactly one uvicorn process (D-095: the rate limits live in its memory),
  listening on localhost only, behind Caddy;
- Caddy doesn't trust X-Forwarded-For from anyone (a spoofed header would pick
  its own rate-limit key).
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(ROOT, "deploy")


def _read(*parts):
    return open(os.path.join(DEPLOY, *parts), encoding="utf-8").read()


def _settings(name):
    """KEY=value lines that are set (comments ignored)."""
    out = {}
    for line in _read(name).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def test_settings_template_keeps_the_server_switches():
    s = _settings("settings.env.example")
    assert s["INSIDELABEL_INVITE_ONLY"] == "on"
    assert s["INSIDELABEL_PROXY_HOPS"] == "1"
    assert s["INSIDELABEL_PUBLIC_URL"] == "https://insidelabel.ai"
    for never in ("INSIDELABEL_ALLOW_REPLAY", "INSIDELABEL_CLAIMS_TO_USERS",
                  "INSIDELABEL_REVIEW_TOKEN", "INSIDELABEL_OCR"):
        assert never not in s, f"{never} must not be set on the server"
    assert not any("KEY" in k for k in s), "API keys belong in secrets.env"


def test_secrets_template_holds_no_values():
    s = _settings("secrets.env.example")
    assert set(s) == {"GEMINI_API_KEY", "GOOGLE_VISION_KEY"}
    assert all(v == "" for v in s.values()), "never commit a key"


def test_one_process_on_localhost():
    unit = _read("systemd", "insidelabel.service")
    start = re.search(r"^ExecStart=(.*?)(?<!\\)$", unit, re.M | re.S).group(1)
    assert "--workers 1" in start
    assert "--host 127.0.0.1" in start
    assert "EnvironmentFile=/etc/insidelabel/secrets.env" in unit


def test_caddy_trusts_no_forwarded_header():
    caddy = "\n".join(l for l in _read("Caddyfile").splitlines() if not l.strip().startswith("#"))
    assert "trusted_proxies" not in caddy
    assert "reverse_proxy 127.0.0.1:8000" in caddy
    assert re.search(r"redir https://insidelabel\.ai\{uri\} permanent", caddy)


def test_the_review_agents_only_draft():
    # D-117: shadow until the measurement passes; publishing isn't even built yet.
    unit = _read("systemd", "insidelabel-review-agent.service")
    start = re.search(r"^ExecStart=(.*)$", unit, re.M).group(1)
    assert "tools/review_agent.py run" in start and "publish" not in start
    assert "EnvironmentFile=/etc/insidelabel/secrets.env" in unit      # it calls Gemini
    assert "ReadWritePaths" not in unit                                # writes only to the database
