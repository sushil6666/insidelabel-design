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

# D-148: photo scans each install may make in any 24 hours during the beta
# (Sushil's choice). The app shows lenses/screen.py's photo_limit() when this is
# the rule that refuses. To change it: this number, then deploy (OPERATIONS.md).
PHOTO_SCANS_A_DAY = 15
DAY = 86_400

# (limit, window in seconds). Starting values for the closed beta; the numbers
# are D-095's and can be tuned from real traffic.
RULES = {
    # Photo scans: each is a paid model call (about Rs 0.6). D-148: 15 a day per
    # install, a rolling 24 hours, so the wait the limiter computes is the time
    # the screen states. The old 20-in-10-minutes rule could never bite under it.
    # The IP rules stay as D-095 set them: 400 a day is about 26 installs at their
    # full 15 behind one carrier address, so the per-install limit is the one a
    # real household meets, and someone rotating install ids is still held to
    # 400 a day (about Rs 240).
    "scan": {"device": [(PHOTO_SCANS_A_DAY, DAY)],
             "ip": [(60, 600), (400, DAY)]},
    # Barcode-only lookups: a catalogue read, no model call.
    "lookup": {"device": [(120, 600)], "ip": [(600, 600)]},
    # D-204: name search, a catalogue read like a lookup. The app asks as the user types
    # (after a pause), so a few words cost a few requests; this stops a script walking
    # the catalogue two letters at a time, not a person.
    "search": {"device": [(120, 600)], "ip": [(600, 600)]},
    # Problem reports: people report once; the app's crash reporter already
    # sends each error once per session.
    "problem": {"device": [(10, 3_600)], "ip": [(60, 3_600)]},
    # Failed reviewer logins (D-097), counted per name and per address. Only
    # failures are counted; while locked, even the right password is refused.
    "review_login_fail": {"name": [(10, 900)], "ip": [(30, 900)]},
    "feedback": {"device": [(20, 86_400)], "ip": [(100, 86_400)]},
    "agree": {"device": [(20, 3_600)], "ip": [(200, 3_600)]},
    # Checking a photo as it's picked (D-104): no model call, a few per scan.
    "check_photo": {"device": [(60, 600)], "ip": [(300, 600)]},
    # D-201: a side photo of an infant pack, one Cloud Vision read (about 13 paise) and no model
    # call; at most two per result, so this only stops a loop. Not one of the day's photo scans.
    "side_photo": {"device": [(20, 600), (60, 86_400)], "ip": [(200, 600)]},
    # "Send it to us" (D-070): each is a reviewer's time.
    "send_to_us": {"device": [(10, 86_400)], "ip": [(50, 86_400)]},
    # "Delete my data" (D-129): once is enough; a few more for a flaky network.
    "forget": {"device": [(5, 3_600)], "ip": [(30, 3_600)]},
}

SCAN_TEXT = ("You've checked a lot of packs in a short time. Please wait about {minutes} "
             "minute{s} and try again.")
SEARCH_TEXT = "That's a lot of searches in a short time. Please wait about {minutes} minute{s} and try again."
PROBLEM_TEXT = "We've had a lot of reports from this phone just now. Please try again later."
SEND_TEXT = "You've sent us a lot of packs today. Please try again tomorrow."
FEEDBACK_TEXT = "Thank you for all the feedback today. Please send more tomorrow."
FORGET_TEXT = "That was tried a few times just now. Please try again in an hour."


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

    def blocking(self, bucket, **keys):
        """The (kind, limit, window) rules that would refuse one more request now; counts nothing."""
        rules = self.rules.get(bucket) or {}
        now = self.clock()
        out = []
        with self._lock:
            for kind, value in keys.items():
                if value is None or not rules.get(kind):
                    continue
                times = self._hits.get((bucket, kind, value), ())
                for limit, window in rules[kind]:
                    if self._wait(times, [(limit, window)], now) > 0:
                        out.append((kind, limit, window))
        return out

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

    def give_back(self, bucket, **keys):
        """
        D-191: un-count the newest request on every key given: one that turned out to cost
        nothing (the same photos as a refused scan, answered from its stored read).
        """
        rules = self.rules.get(bucket) or {}
        with self._lock:
            for kind, value in keys.items():
                q = self._hits.get((bucket, kind, value)) if value is not None and rules.get(kind) else None
                if q:
                    q.pop()


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
