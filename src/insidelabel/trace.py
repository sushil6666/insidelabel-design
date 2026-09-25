"""
trace.py - what it takes to reproduce a request later (D-092).

A scan's result is fixed by five things: the photos, the model's raw answer,
the request options, the code, and the data tables. Photos are kept by
media.py; the raw answer and options go on the scan row (store.py). This module
names the last two, and gives every request an id that ties the phone's event
trail, the server log and the scan row together.

- REQUEST_ID: one per HTTP request. The app sends its own (so a request that
  never reached us still has an id in the phone's trail); otherwise we make one.
  Returned in the X-Request-ID header and in error bodies.
- BUILD: the git commit the server runs, "-dirty" if tracked files were edited.
  Set INSIDELABEL_BUILD at deploy, where there is no .git directory.
- DATA_VERSION: a hash of data/*.json. ENGINE_VERSION alone can't say which
  additive table produced a verdict; this can.
"""

import contextvars
import hashlib
import logging
import os
import re
import subprocess
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.environ.get("INSIDELABEL_DATA", os.path.join(ROOT, "data"))

REQUEST_ID = contextvars.ContextVar("request_id", default=None)
_VALID_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def accept_or_new(incoming):
    """The client's id if it is well formed, else a fresh one. Never trusts free text."""
    return incoming if incoming and _VALID_ID.match(incoming) else str(uuid.uuid4())


def current_request_id():
    return REQUEST_ID.get()


def _data_version(path=DATA_DIR):
    h = hashlib.sha256()
    try:
        for name in sorted(os.listdir(path)):
            if name.endswith(".json"):
                h.update(name.encode() + b"\0")
                with open(os.path.join(path, name), "rb") as f:
                    h.update(f.read())
    except OSError:
        return "unknown"
    return h.hexdigest()[:12]


def _build():
    if os.environ.get("INSIDELABEL_BUILD"):
        return os.environ["INSIDELABEL_BUILD"]
    try:
        run = lambda *a: subprocess.run(["git", "-C", ROOT, *a], capture_output=True,  # noqa: E731
                                        text=True, timeout=3, check=True).stdout.strip()
        sha = run("rev-parse", "--short=12", "HEAD")
        dirty = run("status", "--porcelain", "--untracked-files=no")
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


DATA_VERSION = _data_version()
BUILD = _build()


# A logger filter would miss child loggers (insidelabel.api, …); a record
# factory sees every record. Only our own lines get the prefix.
_factory = logging.getLogRecordFactory()


def _record(*args, **kwargs):
    record = _factory(*args, **kwargs)
    rid = REQUEST_ID.get()
    record.request_id = rid
    if rid and record.name.startswith("insidelabel"):
        record.msg = f"[req {rid}] {record.msg}"
    return record


if not getattr(logging.getLogRecordFactory(), "_insidelabel", False):
    _record._insidelabel = True
    logging.setLogRecordFactory(_record)
