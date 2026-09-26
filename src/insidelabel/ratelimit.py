"""
ratelimit.py - per-install and per-IP limits on /scan and /problem (D-095).

Why: a scan with photos is a paid Gemini call (and a Cloud Vision read). With a
public URL, one runaway client, a retry loop in the app, or anyone who finds the
endpoint could spend the prepaid credit in minutes, and the credit has already
run out once (STATE §5). /problem stores up to 100 KB per report, so a crash
loop could fill the table.

Two keys, because neither is enough alone:
  * device_id is the app's install id. It is exact for real users but the
    client chooses it, so an abuser simply sends a new one each time.
  * The IP address can't be chosen, but in India most phones sit behind
    carrier-grade NAT (many households on one address), so its limit is loose.
Every rule for every key must pass. A refused request is not counted, so being
refused doesn't extend the wait, and one install's refusals don't eat into the
budget of others on the same IP.

Barcode-only lookups (no photo, no model call) have their own, looser budget:
a parent checking a shelf by barcode shouldn't use up their photo scans.

The counters live in this process (sliding windows in memory). That fits one
server process, which is the beta's deploy (STATE §8 item 13). With several
workers each keeps its own count, so the effective limit multiplies; move the
counters to Postgres or Redis before scaling out. A restart forgets them.

Behind a reverse proxy set INSIDELABEL_PROXY_HOPS to the number of proxies, and
the client address is read from X-Forwarded-For, counting from the right (the
entries further left are whatever the client chose to send). Unset or 0: the
socket's peer address, and the header is ignored.
"""

import os
import threading
import time
from collections import OrderedDict, deque

# (limit, window in seconds). Starting values for the closed beta; the numbers
# are D-095's and can be tuned from real traffic.
RULES = {
    # Photo scans: each is a paid model call. 20 in 10 minutes is a
    # pantry-clearing session; 100 a day is far past any real household.
    "scan": {"device": [(20, 600), (100, 86_400)],
             "ip": [(60, 600), (400, 86_400)]},
    # Barcode-only lookups: a catalogue read, no model call.
    "lookup": {"device": [(120, 600)], "ip": [(600, 600)]},
    # Problem reports: people report once; the app's crash reporter already
    # sends each error once per session.
    "problem": {"device": [(10, 3_600)], "ip": [(60, 3_600)]},
    # Failed reviewer logins (D-097), counted per name and per address. Only
    # failures are counted; while locked, even the right password is refused.
    "review_login_fail": {"name": [(10, 900)], "ip": [(30, 900)]},
    # Wrong invite codes (D-102): only failures count. Codes are 8 characters
    # from 31, so this is about noise, not about guessing one.
    "join_fail": {"device": [(10, 3_600)], "ip": [(30, 3_600)]},
    "feedback": {"device": [(20, 86_400)], "ip": [(100, 86_400)]},
    # Checking a photo as it's picked (D-104): no model call, a few per scan.
    "check_photo": {"device": [(60, 600)], "ip": [(300, 600)]},
    # "Send it to us" (D-070): each is a reviewer's time.
    "send_to_us": {"device": [(10, 86_400)], "ip": [(50, 86_400)]},
}

SCAN_TEXT = ("You've checked a lot of packs in a short time. Please wait about {minutes} "
             "minute{s} and try again.")
PROBLEM_TEXT = "We've had a lot of reports from this phone just now. Please try again later."
SEND_TEXT = "You've sent us a lot of packs today. Please try again tomorrow."
JOIN_TEXT = "Too many codes tried from this phone. Please wait a while and check your invite."
FEEDBACK_TEXT = "Thank you for all the feedback today. Please send more tomorrow."


class Limiter:
    def __init__(self, rules, clock=time.monotonic, max_keys=100_000):
        self.rules = rules
        self.clock = clock
        self.max_keys = max_keys
        self._hits = OrderedDict()           # (bucket, kind, value) -> deque of times, oldest first
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self._hits.clear()

    def _wait(self, times, rules, now):
        """Seconds until this key may go again under every rule, or 0."""
        wait = 0.0
        for limit, window in rules:
            in_window = [t for t in times if t > now - window]
            if len(in_window) >= limit:
                # The oldest hit that has to leave before one more fits.
                wait = max(wait, in_window[len(in_window) - limit] + window - now)
        return wait

    def wait(self, bucket, **keys):
        """Seconds until one more request would pass, or None; counts nothing."""
        rules = self.rules.get(bucket) or {}
        now = self.clock()
        with self._lock:
            w = max([self._wait(self._hits.get((bucket, kind, value), ()), rules[kind], now)
                     for kind, value in keys.items() if value is not None and rules.get(kind)] or [0.0])
        return w if w > 0 else None

    def hit(self, bucket, **keys):
        """
        Count one request against every key given (device=..., ip=...), or
        refuse it. Returns None when allowed, else the seconds to wait.
        Keys that are None are skipped.
        """
        rules = self.rules.get(bucket) or {}
        now = self.clock()
        with self._lock:
            ids = [(bucket, kind, value) for kind, value in keys.items()
                   if value is not None and rules.get(kind)]
            wait = 0.0
            for k in ids:
                wait = max(wait, self._wait(self._hits.get(k, ()), rules[k[1]], now))
            if wait > 0:
                return wait
            for k in ids:
                longest = max(w for _l, w in rules[k[1]])
                q = self._hits.get(k)
                if q is None:
                    q = self._hits[k] = deque()
                while q and q[0] <= now - longest:
                    q.popleft()
                q.append(now)
                self._hits.move_to_end(k)
            while len(self._hits) > self.max_keys:
                self._hits.popitem(last=False)          # least recently used key
            return None


LIMITER = Limiter(RULES)


def client_ip(request):
    """The caller's address: the socket peer, or X-Forwarded-For behind N trusted proxies."""
    try:
        hops = int(os.environ.get("INSIDELABEL_PROXY_HOPS", "0") or 0)
    except ValueError:
        hops = 0
    if hops > 0:
        chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else None
