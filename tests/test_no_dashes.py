"""
No em dash (U+2014) or en dash (U+2013) anywhere in the project (Sushil,
2026-09-26). Plain hyphens, colons and "to" instead. Checks every file git
tracks, code, docs, data and the web app alike. Recorded model output
(predictions/, reports/) is not tracked and not checked: it is kept verbatim.

Code that must match these characters in label text writes them as escapes
("\\u2013"), which this test allows.
"""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHES = {"\u2014": "em dash", "\u2013": "en dash"}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [p for p in out.decode().split("\0") if p]


def test_no_em_or_en_dash_in_any_tracked_file():
    found = []
    for rel in tracked_files():
        try:
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue                                   # binary files (photos, icons)
        for n, line in enumerate(text.splitlines(), 1):
            for ch, name in DASHES.items():
                if ch in line:
                    found.append(f"{rel}:{n}: {name}")
    assert not found, "use -, : or 'to' instead:\n" + "\n".join(found[:40])
