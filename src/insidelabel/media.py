"""
Scan photo storage (D-028: keep source photos as evidence).

Local directory for now; Cloudflare R2 later behind the same two methods.
Keys are content hashes, so the same photo sent twice is stored once and a key
can never point at different bytes.

Retention (D-080) is not applied here yet: user originals are to be deleted at
30 days unless flagged, via an R2 lifecycle rule at deploy.
"""

import hashlib
import os
import re

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
        "image/heic": "heic", "image/heif": "heif"}
_KEY = re.compile(r"^[0-9a-f]{64}\.(jpg|png|webp|heic|heif)$")
MIME = {v: k for k, v in _EXT.items()}


class LocalMedia:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def put(self, data, mime):
        key = f"{hashlib.sha256(data).hexdigest()}.{_EXT.get(mime, 'jpg')}"
        path = self._path(key)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)               # never a half-written file under a real key
        return key

    def get(self, key):
        """(bytes, mime) or None. Rejects anything that isn't a well-formed key."""
        if not _KEY.match(key or ""):
            return None
        path = self._path(key)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read(), MIME[key.rsplit(".", 1)[1]]

    def _path(self, key):
        return os.path.join(self.root, key[:2], key)
