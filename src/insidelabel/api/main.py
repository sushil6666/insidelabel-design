"""
Inside Label - API (v0.1)

    POST /analyze      raw ingredient text  -> layered verdict (engine verbatim)
    POST /claim-check  text + front claims  -> verdict + claim contradictions
    POST /allergen-check  ingredients + avoid list -> five-state allergen result
    POST /compare      2-4 scanned packs    -> best pick of these, with reasons
    GET  /regulators/{ins}                  -> India vs EU vs US, information only
    GET  /health

    POST /scan         one or two images   -> verdict + identity + claim check
                       (+ barcode: a reviewed catalogue entry skips the vision call)
    POST /report       "Report a mistake" on a scan (D-076)
    POST /send-to-us   two refused scans -> the review queue (D-070)
    GET  /access       rules agreed? the app's switches (D-105, D-171)
    POST /feedback     a user's comment + optional rating (D-102)
    GET  /.well-known/assetlinks.json   the Play app's link to this site (D-148)

THE GUARD THAT MATTERS
----------------------
engine.analyze("") returns score 100, grade A, binary "clean". That is correct
behaviour for the engine - no flagged ingredients means no penalties - but it
is the single most dangerous output this API can emit, because "we could not
read the label" and "this product is clean" become indistinguishable to the
user. Every path into the engine therefore refuses input that yields no usable
ingredient tokens, rather than passing an empty list through and letting a
false CLEAN out the door.
"""

import datetime as dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import mimetypes  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import uuid  # noqa: E402
from typing import Optional  # noqa: E402

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from insidelabel import barcode as barcode_rules  # noqa: E402
from insidelabel import photo_check  # noqa: E402
from insidelabel import photo_join  # noqa: E402
from insidelabel import pictures  # noqa: E402
from insidelabel import ratelimit  # noqa: E402
from insidelabel import table_hint  # noqa: E402
from insidelabel import trace  # noqa: E402
from insidelabel.core import engine, pack_kind  # noqa: E402
from insidelabel.claims import checker as claim_checker  # noqa: E402
from insidelabel.lenses import allergens as allergen_checker  # noqa: E402
from insidelabel.lenses import diet as diet_checker  # noqa: E402
from insidelabel.lenses import compare as shelf  # noqa: E402
from insidelabel.lenses import infant as infant_lens  # noqa: E402
from insidelabel.lenses import side_by_side  # noqa: E402
from insidelabel.lenses import nutrition  # noqa: E402
from insidelabel.lenses import regulators  # noqa: E402
from insidelabel.lenses import screen as result_screen  # noqa: E402
from insidelabel.reliability import gates as rel  # noqa: E402
from insidelabel.review import checker as review_checker  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402
from insidelabel.extraction.providers import gemini  # noqa: E402
from insidelabel.extraction.providers import ocr_check  # noqa: E402
from insidelabel.extraction.providers.prompt import MODEL, VISION_PROMPT  # noqa: E402
from insidelabel.extraction.schemas import (  # noqa: E402
    AllergenCheckRequest,
    AnalyzeRequest,
    CompareRequest,
    AgreeRequest,
    FeedbackRequest,
    ForgetRequest,
    ProblemRequest,
    ReportRequest,
    SendToUsRequest,
    AnalyzeResponse,
    ClaimCheckRequest,
    ClaimCheckResponse,
)

ENGINE_VERSION = "0.1"
# D-031: pinned on every stored version. Any edit to the prompt changes it.
PROMPT_VERSION = hashlib.sha256(VISION_PROMPT.encode()).hexdigest()[:12]

log = logging.getLogger("insidelabel.api")

# Persistence is optional: set INSIDELABEL_DB to a Postgres URI to store scans.
# Without it the API behaves exactly as before and stores nothing.
STORE = None
MEDIA = None
if os.environ.get("INSIDELABEL_DB"):
    from insidelabel.db.store import Store
    from insidelabel.media import LocalMedia
    STORE = Store(os.environ["INSIDELABEL_DB"])
    # D-028: scan photos are kept as evidence for review. Local dir until R2.
    MEDIA = LocalMedia(os.environ.get("INSIDELABEL_MEDIA", "media"))


# D-051: the front-vs-back claim check runs in shadow until it has been measured
# on real claim-bearing packs (≥ 5, 0 false contradictions). It is still
# computed and stored for reviewers; users see it only when this is "on".
CLAIMS_TO_USERS = os.environ.get("INSIDELABEL_CLAIMS_TO_USERS", "off").lower() == "on"

# D-101: `replay` (a recorded model answer used instead of a model call) is for
# tests, repro.py and local tools. On a public server anyone could send an
# invented reading: it skips the paid model step and lands in the review queue.
# Off unless INSIDELABEL_ALLOW_REPLAY=on. In-process tools set REPLAY_ALLOWED.
REPLAY_ALLOWED = None          # None: follow the environment, read per request


def _replay_allowed():
    if REPLAY_ALLOWED is not None:
        return REPLAY_ALLOWED
    return os.environ.get("INSIDELABEL_ALLOW_REPLAY", "off").lower() == "on"


# D-171: the app's own shutter for the label photos (ImageCapture at the camera's full
# resolution). Off until Sushil has compared it with the phone's camera app on real packs;
# off, the steps take the photo with the camera app as before. The app reads it from /access.
LIVE_SHUTTER = None            # None: follow the environment, read per request


def _live_shutter():
    if LIVE_SHUTTER is not None:
        return LIVE_SHUTTER
    return os.environ.get("INSIDELABEL_LIVE_SHUTTER", "off").lower() == "on"


# D-105: "Before you start", the rules every install agrees to before a first
# scan. The text is data (wording-linted); a new version asks everyone again.
with open(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "terms.json"), encoding="utf-8") as _f:
    TERMS = {k: v for k, v in json.load(_f).items() if not k.startswith("_")}


def _user_claim_check(cc, front_claims):
    """What a user sees of the claim check: the real result, or 'not released yet'."""
    if CLAIMS_TO_USERS:
        return cc
    return {"status": "not_checked", "reason": "claims_not_released", "claims_examined": 0,
            "checked": [], "unmatched_claims": list(front_claims or [])}


def _save_images(images):
    """{"front": key, "back": key} for the photos sent, or {} when not storing."""
    if MEDIA is None:
        return {}
    try:
        return {role: MEDIA.put(data, mime) for data, mime, role in images}
    except OSError:
        log.exception("photo storage failed")
        return {}


def _model_error(tr, e):
    """
    D-172: a model failure's own words go with the scan (scans.model_error) and into the log
    with the request id. Report #7's two failures left nothing to read: no text, no line.
    """
    tr["model_error"] = f"{type(e).__name__}: {e}"[:1000]
    log.warning("model failed, request %s: %s", tr.get("request_id"), tr["model_error"])


def _record_read(tr, read):
    """
    D-192: when Claude was the reader switched on and Gemini read instead (Claude busy after
    its retries, or a HEIC photo), timings.read says so: "fallback": "gemini" and why.
    """
    if read and read.get("fallback"):
        tr["timings"]["read"]["fallback"] = read["fallback"]
        tr["timings"]["read"]["fallback_why"] = read.get("fallback_why")


def _blocked_refusal(e, tr, *, back_read, back_bytes, t_vision, t0, keys, images, barcode, device_id,
                     avoid_codes, who, people):
    """
    D-172: Gemini's guard stopped the answer after its retries. A refusal, never a 502: the
    scan is stored as refused (vision_blocked:<reason>) with a replay marker (D-092), and a
    pack with a barcode can go to a person at once ("Send it to us", D-096).
    D-174: Cloud Vision's text of the back photo, when it has been read by now (it isn't
    waited for), is kept as on any scan, so the table of a pack sent to us is checked
    against it without paying for the same reading twice.
    """
    tr["timings"]["vision_ms"] = _ms(t_vision)
    tr["model_raw"] = gemini.blocked_marker(e.reason)
    _model_error(tr, e)
    text = cloud_vision.cached(back_bytes) if back_bytes and back_read is not None else None
    if text is not None:
        tr["ocr"] = {"back": {"reader": "cloud_vision", "text": text}}
    reliability = {"error": "vision_blocked", "reason": e.reason, "ingredients_complete": False,
                   "verdict_safe_to_display": False, "caveats": []}
    scan_id = _persist(STORE and STORE.record_failed_scan, "refused", error_code=f"vision_blocked:{e.reason}",
                       device_id=device_id, latency_ms=_ms(t0), front_key=keys.get("front"),
                       back_key=keys.get("back"), trace=tr)
    return JSONResponse(status_code=422, content={
        # A refused scan still answers the allergy question: "couldn't confirm" (D-037, D-072).
        "allergens": allergen_block(avoid_codes, [], None, reliable=False, who=who),
        "diet": diet_block(avoid_codes, [], reliable=False),
        "screen": result_screen.build(
            verdict=None, display=None, claim_check=None, extracted=None,
            reliability=reliability, profiles=people, allergen_confidence=0.0,
            allergen_reliable=False, has_barcode=barcode is not None,
            photos_sent=[r for _d, _m, r in images]),
        "scan_id": _str(scan_id),
        "request_id": tr["request_id"],
        "verdict": None,
        "product": None,
        "reliability": reliability,
        "engine_version": ENGINE_VERSION,
    })


def _setup_alarm(signature, message):
    """
    A setup problem (key, billing, credit) as a 'server' problem report, at most
    once an hour per kind, so `tools/repro.py list` shows it first thing (D-092).
    """
    log.error("SETUP ALARM %s: %s", signature, message)
    _persist(STORE and STORE.save_problem, kind="server", request_id=trace.current_request_id(),
             build=trace.BUILD, data_version=trace.DATA_VERSION,
             client={"source": "setup_alarm"}, server_error=message, signature=signature)


def _rate_limit(request, bucket, device_id, text):
    """
    D-095: refuse with 429 before any work when this install or address is over
    its limit. Not stored as a scan: nothing was read, so there is nothing to
    replay, and a flood must not turn into database writes. Logged with the id.
    """
    try:
        device = str(uuid.UUID(str(device_id))) if device_id else None
    except ValueError:
        device = None                     # an invalid id is ignored; the IP limit still applies
    wait = ratelimit.LIMITER.hit(bucket, device=device, ip=ratelimit.client_ip(request))
    if wait is None:
        return
    seconds = max(1, int(wait + 0.999))
    minutes = max(1, round(seconds / 60))
    log.warning("rate limited: %s device=%s wait=%ss", bucket, device, seconds)
    detail = {"error": "rate_limited",
              "detail": text.format(minutes=minutes, s="" if minutes == 1 else "s"),
              "retryable": True, "retry_after_s": seconds}
    # D-148: this install's daily photo scans are used. The app shows this screen
    # (lenses/screen.py) in place of an error; `detail` stays a sentence for older apps.
    if bucket == "scan" and ("device", ratelimit.PHOTO_SCANS_A_DAY, ratelimit.DAY) in \
            ratelimit.LIMITER.blocking("scan", device=device):
        words = result_screen.photo_limit(seconds, ratelimit.PHOTO_SCANS_A_DAY)
        detail["photo_limit"] = words
        detail["detail"] = f"{words['title']}. {words['barcode']} {words['when']}"
    raise HTTPException(status_code=429, headers={"Retry-After": str(seconds)}, detail=detail)


def _persist(fn, *args, **kwargs):
    """
    Run a store call. A database failure is logged loudly but never costs the
    user their result: the verdict was already computed from their photo.
    """
    if STORE is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 - any storage failure, logged with traceback
        log.exception("scan persistence failed")
        return None

app = FastAPI(
    title="Inside Label API",
    version="0.1.0",
    description=(
        "Ingredient-list analysis. The engine states ingredient facts only - "
        "it never says a product is safe for any person or condition. Segment "
        "lenses sit above this API, not inside it."
    ),
)

# D-092: every request gets an id (the app's own, or a new one). It goes back in
# the X-Request-ID header, into every log line, onto the scan row and into error
# bodies, so a report from a phone can be matched to exactly what the server did.
# An exception nothing else handled is stored as a 'server' problem report.
@app.middleware("http")
async def request_ids(request, call_next):
    rid = trace.accept_or_new(request.headers.get("x-request-id"))
    token = trace.REQUEST_ID.set(rid)
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 - the last line of defence; logged and stored
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        tb = traceback.extract_tb(exc.__traceback__)
        where = f"{os.path.basename(tb[-1].filename)}:{tb[-1].lineno}" if tb else "?"
        _persist(STORE and STORE.save_problem, kind="server", request_id=rid,
                 build=trace.BUILD, data_version=trace.DATA_VERSION,
                 client={"method": request.method, "path": request.url.path},
                 server_error=traceback.format_exc(limit=40),
                 signature=f"{type(exc).__name__}@{where}")
        response = JSONResponse(status_code=500, content={
            "error": "server_error", "detail": "Something went wrong on our side.",
            "request_id": rid})
    finally:
        trace.REQUEST_ID.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


# Reviewer screen (D-028). Active only when the database is configured.
from insidelabel.review import routes as review_routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

app.include_router(review_routes.router)
if STORE is not None:
    review_routes.SERVICE = ReviewService(STORE.conninfo, ENGINE_VERSION)
    review_routes.MEDIA = MEDIA

# The PWA (D-010), served from the same origin as the API so the phone needs no
# CORS and the service worker's scope is /app/. Static files only; it renders
# the `screen` block of /scan and makes no judgements of its own.
WEB_DIR = os.environ.get("INSIDELABEL_WEB", os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "web")))
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")        # module scripts refuse other types
mimetypes.add_type("video/mp4", ".mp4")            # the film on home (web/film/); some systems lack these
mimetypes.add_type("image/webp", ".webp")
if os.path.isdir(WEB_DIR):
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="app")

    # D-102: the public pages around the app - landing, privacy, about. Plain
    # HTML in web/site/, linted with the app's wording rules (tests/test_web.py).
    SITE_DIR = os.path.join(WEB_DIR, "site")
    _SITE_PAGES = {"/": "index.html", "/privacy": "privacy.html", "/about": "about.html",
                   "/how": "how.html", "/site.css": "site.css",      # D-127: what result words mean
                   "/privacy.html": "privacy.html"}                  # the Play listing's privacy URL

    def _site_page(path):
        name = _SITE_PAGES[path]
        full = os.path.join(SITE_DIR, name)
        if not os.path.exists(full):
            return RedirectResponse("/app/")
        return FileResponse(full)

    for _path in _SITE_PAGES:
        app.add_api_route(_path, (lambda p: (lambda: _site_page(p)))(_path), methods=["GET"],
                          include_in_schema=False)


# D-148: the Play app is a Trusted Web Activity of /app/ (D-010). Chrome shows it
# without an address bar only when this file names the app's package and the
# SHA-256 of the certificate that signed the installed build: Google's app signing
# key for an install from Play (D-012), the upload key for one installed by hand.
# The fingerprints are data (data/assetlinks.json), read on each request so a
# deploy that changes them needs no restart. A missing or malformed file is a 404,
# never a 500 and never a partial statement: Android then just keeps the bar.
ASSETLINKS_FILE = os.path.join(trace.DATA_DIR, "assetlinks.json")
_SHA256_FINGERPRINT = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){31}$")


def assetlinks_statements(path):
    """The Digital Asset Links statement list for `path`, or None if it isn't usable."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        package = data["package_name"]
        prints = [row["sha256"] for row in data["fingerprints"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(package, str) or not package or not prints:
        return None
    if not all(isinstance(p, str) and _SHA256_FINGERPRINT.match(p) for p in prints):
        return None
    return [{"relation": ["delegate_permission/common.handle_all_urls"],
             "target": {"namespace": "android_app", "package_name": package,
                        "sha256_cert_fingerprints": prints}}]


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks():
    statements = assetlinks_statements(ASSETLINKS_FILE)
    if statements is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    return JSONResponse(statements)


# ---------------------------------------------------------------------------
def guard_ingredients(raw: str) -> None:
    """
    Refuse input the engine would score as a perfect 100 for the wrong reason.
    Raises HTTPException(422). Does not touch the engine or its thresholds.
    """
    if not raw or not raw.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": "empty_ingredients",
                "detail": "raw_ingredients is empty.",
                "hint": "An empty list would read as nothing found. Refused rather than returned.",
            },
        )
    if not engine.tokenize(raw):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_ingredient_tokens",
                "detail": "No ingredient tokens could be parsed from the input.",
                "hint": "An unparseable list would read as nothing found. Refused rather than returned.",
            },
        )


# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "build": trace.BUILD,                 # D-092
        "data_version": trace.DATA_VERSION,
        "additives_loaded": len(engine._ADDITIVE_BY_INS),
        "nova_markers_loaded": len(engine.NOVA["markers"]),
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    """Wrap engine.analyze(). The verdict is returned exactly as the engine built it."""
    guard_ingredients(req.raw_ingredients)
    verdict = engine.analyze(req.raw_ingredients)
    return {
        "verdict": verdict,
        "engine_version": ENGINE_VERSION,
        # D-086: optional and information only. Built from the verdict; never feeds it.
        "regulators": regulators.compare(verdict) if req.compare_regulators else None,
    }


@app.post("/claim-check", response_model=ClaimCheckResponse)
def claim_check(req: ClaimCheckRequest):
    """
    Text-only claim checking. Exists so the claim rules can be exercised
    against real labels without spending a vision call per iteration; /scan
    will call the same claim_checker.check_claims().
    """
    guard_ingredients(req.raw_ingredients)
    if req.front_status not in ("read", "not_provided", "unreadable"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "bad_front_status",
                "detail": 'front_status must be "read", "not_provided", or "unreadable".',
            },
        )
    verdict = engine.analyze(req.raw_ingredients)
    return {
        "verdict": verdict,
        "claim_check": claim_checker.check_claims(
            req.front_claims, req.raw_ingredients, verdict, req.front_status
        ),
        "engine_version": ENGINE_VERSION,
    }


# ---------------------------------------------------------------------------
# Allergens (D-060, D-071, D-072)
# ---------------------------------------------------------------------------
def parse_avoid(avoid):
    """Accept a list or a comma-separated string of allergen codes. 422 on unknown codes."""
    if avoid is None:
        return []
    items = avoid.split(",") if isinstance(avoid, str) else avoid
    codes = list(dict.fromkeys(c.strip().lower() for c in items if c and c.strip()))
    # D-198: the two diet codes share the avoid list; allergen_block() reads only allergens.
    unknown = [c for c in codes if c not in allergen_checker.ALLERGENS and c not in diet_checker.DIETS]
    if unknown:
        raise HTTPException(status_code=422, detail={
            "error": "unknown_allergen",
            "detail": f"Unknown allergen code(s): {', '.join(unknown)}.",
            "hint": "Valid codes: " + ", ".join([*allergen_checker.ALLERGENS, *diet_checker.DIETS]) + ".",
        })
    return codes


def parse_profiles(raw):
    """The /scan `profiles` form field: JSON [{ref, age, avoid}], no names (D-074)."""
    if raw is None or not raw.strip():
        return []
    try:
        return result_screen.parse_profiles(json.loads(raw))
    except (ValueError, TypeError) as e:          # JSONDecodeError and ProfileError are ValueErrors
        raise HTTPException(status_code=422, detail={"error": "bad_profiles", "detail": str(e)})


def allergen_block(codes, ingredients, statement, confidence=1.0, reliable=True, who=None, where="photo"):
    """
    The first thing a client renders when the profile has an avoid list (D-060).
    where="pack": a catalogue hit, so no line says "in the photo" (D-188).
    Results are sorted strongest state first, so results[0] is the headline.
    """
    codes = [c for c in (codes or []) if c in allergen_checker.ALLERGENS]      # D-198: diet codes go to diet_block()
    if not codes:
        return None
    results = allergen_checker.check(
        ingredients or [], statement, codes, confidence=confidence, reliable=reliable)
    order = {"contains": 0, "may_contain": 1, "cannot_confirm": 2, "uncertain": 3, "not_listed": 4}
    rows = sorted(results.values(), key=lambda r: order[r.state])
    return {
        "avoid": codes,
        "min_confidence": allergen_checker.ALLERGEN_MIN_CONFIDENCE,
        "results": [
            {
                "code": r.code,
                "state": r.state,
                "evidence": r.evidence or None,
                "statement_seen": r.statement_seen,
                "text": r.parent_text(who or "your child", where),
            }
            for r in rows
        ],
    }


def diet_block(codes, ingredients, veg_mark=None, confidence=1.0, reliable=True, complete=True, where="photo",
               product_name=None):
    """
    D-198: /scan's `diet` block, right after `allergens` (which stays first and unchanged,
    D-060): "Vegetarian only" and "No onion or garlic" for the avoid list's diet codes.
    veg_mark: product.veg_mark as read, or the catalogue version's stored one (None: none
    known, so the list only). Never a verdict, score or concern level (D-004).
    """
    codes = [c for c in (codes or []) if c in diet_checker.DIETS]
    if not codes:
        return None
    results = diet_checker.check(ingredients or [], codes, veg_mark=veg_mark, mark_from=where,
                                 confidence=confidence, reliable=reliable, complete=complete,
                                 product_name=product_name)
    order = {"contains": 0, "cannot_confirm": 1, "uncertain": 2, "not_listed": 3}
    rows = sorted(results.values(), key=lambda r: order[r.state])
    return {
        "avoid": codes,
        "veg_mark": veg_mark if veg_mark in diet_checker.MARKS else None,
        "mark_from": where if veg_mark in diet_checker.MARKS else None,
        "min_confidence": diet_checker.MIN_CONFIDENCE,
        "results": [{"code": r.code, "state": r.state, "evidence": r.evidence or None,
                     "sources": r.sources, "text": diet_checker.text(r, where)} for r in rows],
    }


@app.get("/allergens")
def list_allergens():
    """Codes a client may put on an avoid list, with display labels."""
    return {
        "allergens": [
            {"code": a["code"], "label": a["label"],
             "fssai_mandatory": a.get("fssai_mandatory", True)}
            for a in allergen_checker.ALLERGENS.values()
        ],
        # D-198: shown after the allergens in the avoid-list editor; same `avoid` list.
        "diets": [{"code": d["code"], "label": d["label"]} for d in diet_checker.DIETS.values()],
    }


@app.post("/allergen-check")
def allergen_check(req: AllergenCheckRequest):
    """
    Text-only allergen check, for exercising the tables without a vision call.
    Input is taken as fully read and reliable; /scan applies the real gate.
    """
    codes = parse_avoid(req.avoid)
    return {"allergens": allergen_block(codes, req.ingredients, req.allergen_statement, who=req.who)}


# ---------------------------------------------------------------------------
# Shelf comparison (D-057)
# ---------------------------------------------------------------------------
# D-200: a pack compares only with packs of its own kind; each refusal has its own sentence.
# D-202 (Sushil, 2026-10-14): an infant pack is checked one pack at a time; with the infant switch
# off, D-140's refusal stays word for word.
INFANT_ONE_AT_A_TIME = "We check foods for infants one pack at a time."
MIXED_COMPARE = {
    "infant": "We compare an infant food only with other infant foods.",
    "supplement": "We compare a supplement only with other supplements.",
}


def _pack_out(p, who):
    return {
        "id": p.id,
        "name": p.name,
        "fully_checked": p.fully_checked,
        "unknown_ins": p.unknown_ins,
        "facts": [
            {"key": f.key, "tier": f.tier, "text": f.parent_text,
             "technical": f.technical, "positive": f.positive}
            for f in p.facts
        ],
        "allergens": [
            {"code": r.code, "state": r.state, "evidence": r.evidence or None,
             "text": r.parent_text(who)}
            for r in p.allergens.values()
        ],
        # D-198: the diet choices, by the same rules; a quiet line never blocks a pick.
        "diet": [
            {"code": r.code, "state": r.state, "evidence": r.evidence or None,
             "text": diet_checker.text(r)} | ({"quiet": True} if diet_checker.green_quiet(r) else {})
            for r in p.diet.values()
        ],
    }


@app.post("/compare")
def compare_packs(req: CompareRequest):
    """
    Names the best pick of the packs scanned, never of the category. Ranked by
    concern tiers, never by score. A pack that fails the avoid list, can't be
    fully checked, or has an unknown additive is never the best pick.
    """
    if req.age not in shelf.AGE_BANDS:
        raise HTTPException(status_code=422, detail={
            "error": "bad_age",
            "detail": f"age must be one of {', '.join(shelf.AGE_BANDS)}.",
        })
    # D-140: the server itself decides what can be compared, whatever the client sends.
    # Refused if any of: the kind the client reports, the kind the pack's printed
    # statements give, or the kind stored for that scan says it can't be compared.
    # With INSIDELABEL_INFANT_TO_USERS off, an infant food never is (D-140's shadow).
    group = []
    for p in req.packs:
        kinds = {p.kind or "food", pack_kind.decide({"pack_statements": [
            s for s in p.pack_statements if isinstance(s, dict) and isinstance(s.get("text"), str)]})["code"]}
        stored = _persist(STORE.kind_of_scan, p.id) if STORE else None
        if stored:
            kinds.add(stored)
        blocked = sorted(kinds - pack_kind.comparable())
        if blocked:
            raise HTTPException(status_code=422, detail={
                "error": "not_comparable", "reason": "infant_food" if "infant" in blocked else blocked[0],
                "pack": p.id,
                "detail": ((INFANT_ONE_AT_A_TIME if pack_kind.infant_to_users() else
                            "We don't compare or rank foods for infants.") if "infant" in blocked
                           else "We compare ordinary foods only for now."),
            })
        # D-200: any source naming the stricter kind decides it, so a pack can't join another kind's comparison.
        group.append("infant" if "infant" in kinds else "supplement" if "supplement" in kinds else "food")
    if len(set(group)) > 1:
        odd = next(p.id for p, k in zip(req.packs, group) if k != group[0])
        raise HTTPException(status_code=422, detail={
            "error": "not_comparable", "reason": "mixed_kinds", "pack": odd,
            "detail": MIXED_COMPARE["infant" if "infant" in group else "supplement"],
        })
    codes = parse_avoid(req.avoid)
    if len({p.id for p in req.packs}) != len(req.packs):
        raise HTTPException(status_code=422, detail={
            "error": "duplicate_pack", "detail": "Each pack needs a distinct id.",
        })
    if group[0] != "food":
        # D-200: supplements and infant foods side by side, with no pick (lenses/side_by_side.py).
        return side_by_side.compare(group[0], [p.model_dump() for p in req.packs], avoid=codes, who=req.who)
    packs = [shelf.Product(p.id, p.name, p.ingredients, reliable=p.reliable,
                           allergen_statement=p.allergen_statement, confidence=p.confidence,
                           veg_mark=p.veg_mark)
             for p in req.packs]
    r = shelf.compare(packs, age=req.age, avoid=codes, who=req.who,
                      strict_may_contain=req.strict_may_contain)
    who = r["who"]
    if r["best"]:
        outcome = "best"
    elif r["tie"]:
        outcome = "tie"
    elif r["blocked"] or r["allergen_unsure"]:
        outcome = "no_clear_pick"
    elif any(p.unknown_ins for p in r["not_checked"]):
        outcome = "unknown_additives"
    else:
        outcome = "unreadable"
    ids = lambda group: [p.id for p in group]  # noqa: E731
    return {
        "outcome": outcome,
        "who": who,
        "age": r["age"],
        "avoid": r["avoid"],
        "best": r["best"].id if r["best"] else None,
        "why_best": r["why_best"],
        "allergen_lines": r["allergen_lines"],
        "tie": ids(r["tie"]),
        "others": ids(r["others"]),
        "blocked": ids(r["blocked"]),
        "allergen_unsure": ids(r["allergen_unsure"]),
        "not_checked": ids(r["not_checked"]),
        "packs": [_pack_out(p, who) for p in packs],
        "summary": shelf.render(r),
    }


# ---------------------------------------------------------------------------
# India vs EU vs US (D-086) - information only
# ---------------------------------------------------------------------------
@app.get("/regulators")
def list_regulators():
    """Every additive with a checked comparison, regulators-differ first."""
    rows = [regulators.row(i) for i in regulators.ROWS]
    rows.sort(key=lambda r: not r["differs"])
    return {"basis": regulators.BASIS, "additives": rows}


@app.get("/regulators/{ins}")
def regulator_row(ins: str):
    r = regulators.row(ins.strip().lower())
    if r is None:
        raise HTTPException(status_code=404, detail={
            "error": "not_compared",
            "detail": f"INS {ins} has not been compared across regulators yet.",
        })
    return {"basis": regulators.BASIS, **r}


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc):
    detail = exc.detail
    rid = trace.current_request_id()          # D-092: quote this when reporting
    headers = getattr(exc, "headers", None)       # e.g. Retry-After on a 429 (D-095)
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content={**detail, "request_id": rid},
                            headers=headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "request_error", "detail": str(detail), "request_id": rid},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Scan helpers: barcode, timing, catalogue results (D-024, D-073)
# ---------------------------------------------------------------------------
def _clean_barcode(code):
    """
    D-103: a retail pack's GTIN or a 422 naming what's wrong (check digit, a
    carton code, a shop's in-store code, a book…), before anything is read.
    """
    if code is None or not code.strip():
        return None
    b, reason = barcode_rules.check(code)
    if reason:
        raise HTTPException(status_code=422, detail={
            "error": "bad_barcode", "reason": reason, "detail": barcode_rules.MESSAGES[reason],
        })
    return b


def lost_words_matter(ingredients, lost, allergen_statement=None, lost_ins=()):
    """
    D-159: would the words Cloud Vision read in the ingredient list, and Gemini's list
    lacks (review_checker.independent_read's LOST), change this scan's result? The rules
    judge (D-004): the same ones the result is built from run on Gemini's list, and on
    the list with what was lost added, and their answers are compared. No word list
    here; the tables decide. True when anything differs: an allergen's state for any
    code (allergens.json), the engine's verdict (additives, sugar names, sweeteners,
    NOVA markers, band), the ingredient notes, the household lines for any age band,
    or the baby lines.

    D-160: two runs, not one per word: the list, and the list with each lost word as its
    own entry (the sorted words joined could form an `exclude` phrase: "coconut milk",
    "egg free"), the words joined as one more entry (so "corn syrup" still reads as one
    name), and the lost INS numbers (review_checker.lost_ins_numbers) as "INS n"
    entries, so a dropped "Preservative (211)" counts. One run holds them all: the
    allergen check strips `exclude` phrases entry by entry, and the engine's findings
    only add up, so the joined entry can't hide a separate "milk". A misread number that
    is no additive changes nothing and doesn't ask.

    Beside the gate, not in review/checker.py: it is /scan's question (what the user
    would see), and the D-117 checker stays word-for-word strict without it.
    """
    if not lost and not lost_ins:
        return False
    listed = list(ingredients or [])
    added = list(lost) + ([" ".join(lost)] if len(lost) > 1 else []) + [f"INS {n}" for n in lost_ins]
    return _rule_answers(listed, allergen_statement) != _rule_answers(listed + added, allergen_statement)


def cross_check(ingredients, allergen_statement, ocr_text):
    """
    D-118's question: does Cloud Vision's text of the back confirm Gemini's list, and when
    it doesn't, would what differs change the user's result? Returns (matters, check):
    check is None when the text confirms the list, else what it found, for the scan's
    trace (D-092). /scan asks for a clearer photo only when it matters (and once per pack,
    D-191); tools/cross_check_replay.py runs the same on stored scans.

    D-159: what only Cloud Vision read (LOST, and D-160's numbers) matters only when it
    would change the user's result. D-191 (Sushil, 2026-10-10): so do the words of Gemini's
    list it never saw (MISSING), after the ones it read glued to a neighbour; and no list
    found in its text no longer asks on its own (MISSING is counted against the whole text).
    The D-117 checker still sends the words to a person.
    """
    section, missing, lost = review_checker.independent_read(ingredients, ocr_text, allergen_statement)
    check, error = {"section_found": bool(section), "missing": missing, "lost": lost}, False
    try:
        # D-160: the numbers too; LOST holds words only. Against the list as it now
        # stands (after D-093's recovery), so a number recovered in a form the parser
        # can't read ("Raising agents (500(ii)") still counts as lost.
        check["lost_ins"] = review_checker.lost_ins_numbers(ingredients, ocr_text)
    except Exception:                                                      # noqa: BLE001
        log.exception("lost-numbers check failed")
        check["lost_ins"], error = [], True
    if not error and section and not missing and not lost and not check["lost_ins"]:
        return False, None
    matters = error or missing == ["(no text)"]
    if not matters:
        try:
            glued = review_checker.glued_seen(missing, ingredients, ocr_text)
            if glued:
                check["glued"] = glued
            unseen = [w for w in missing if w not in glued]
            matters = (lost_words_matter(ingredients, lost, allergen_statement, check["lost_ins"])
                       or missing_words_matter(ingredients, unseen, allergen_statement))
        except Exception:                                                  # noqa: BLE001
            # D-160: a failed check never costs the result; it asks, as before D-159.
            log.exception("lost-words check failed")
            matters, error = True, True
    if error:
        check["error"] = True
    return matters, check


def _rule_answers(entries, allergen_statement):
    """What the rules make of a list (D-159): everything a word could change on the result."""
    verdict = engine.analyze(", ".join(entries))
    flags = sorted((f["matched_as"], f["type"], f["concern"]) for f in verdict["flags"])
    verdict = {k: v for k, v in verdict.items() if k not in ("flags", "ingredient_count_parsed")}
    states = {c: r.state for c, r in allergen_checker.check(
        entries, allergen_statement, list(allergen_checker.ALLERGENS)).items()}
    notes = [n["id"] for n in engine.ingredient_notes(entries)]
    facts = {age: [(f.key, f.tier, f.parent_text) for f in
                   shelf.extract_facts(shelf.Product("x", "x", entries), age).facts if f.tier == "strong"]
             for age in shelf.AGE_BANDS}
    baby = [line["text"] for line in result_screen.baby_lines("food", entries, True)]
    return flags, verdict, states, notes, facts, baby


def missing_words_matter(ingredients, missing, allergen_statement=None):
    """
    D-191: lost_words_matter()'s sibling for MISSING, the words of Gemini's list that Cloud
    Vision never saw (review_checker.independent_read). Such a word may be one Gemini made
    up, so the rules run on the list as read and on the list with those words struck out;
    True when any answer differs (an allergen for any code, an additive or INS number, the
    verdict, the notes, the age lines, the baby lines). "ginger", "peas" or a glued reader
    word ("contaadded") change nothing and don't ask; "milk" or "INS 211" do.
    """
    if not missing:
        return False
    listed = list(ingredients or [])
    struck = []
    for entry in listed:
        for w in missing:
            entry = re.sub(rf"(?i)(?<![a-z]){re.escape(w)}(?![a-z])", " ", entry)
        if re.search(r"[A-Za-z0-9]", entry):
            struck.append(" ".join(entry.split()))
    return _rule_answers(listed, allergen_statement) != _rule_answers(struck, allergen_statement)


async def _table_answer(hit, panel, barcode, barcode_source, images, keys, ocr_result, vision, device_id, t0, tr):
    """
    D-168: the answer to a table photo for a published pack. Only the checked table
    (nutrition.check(), D-133) is used: the ingredient list isn't gated, kept or changed.
    A photo that shows another barcode (D-143's check) or no usable table stores no
    version; every read is kept with its trace (D-092). One line of the server's words.
    """
    check = await run_in_threadpool(barcode_rules.confirm, barcode, [(r, d) for d, _m, r in images],
                                    ocr_result.get("ocr_text"))
    tr["barcode_check"] = {**check, "source": barcode_source}
    state = (panel or {}).get("status")
    status = ("different_barcode" if check["status"] == "mismatch"
              else "added" if state in ("read", "partial")
              else "no_table" if state in (None, "not_read", "missing") else "unclear")
    saved = None
    if status == "added" and STORE and hit:
        saved = _persist(STORE.add_table, hit, table=panel, back_key=keys.get("back"),
                         verdict=engine.analyze(", ".join(hit["ingredients"])),
                         model_name=vision.get("_model") or MODEL, prompt_version=PROMPT_VERSION,
                         engine_version=ENGINE_VERSION, device_id=device_id, latency_ms=_ms(t0), trace=tr)
        if saved is None:
            status = "already_waiting"        # another table arrived meanwhile: the same thanks is true
    scan_id = saved["scan_id"] if saved else _persist(
        STORE and STORE.record_failed_scan, "refused", error_code=f"table_{status}", device_id=device_id,
        latency_ms=_ms(t0), back_key=keys.get("back"), trace=tr)
    answer = "added" if status == "already_waiting" else status
    words = result_screen.TABLE_ANSWER[answer]
    return {"table": {"status": status, "text": words, "kind": result_screen.TABLE_ANSWER_KIND[answer]}, "scan_id": _str(scan_id),
            "request_id": tr["request_id"], "nutrition": nutrition.public(panel),
            "catalogue": {"source": "scan", "queued_for_review": saved and saved["queued"]}}


# D-175: how long a re-check photo waits for its free read before the paid read decides
# instead. Cloud Vision answers in 1 to 3 s; a Tesseract fallback can take far longer (44.6 s
# seen on 2026-10-07), and the free check must never cost more time than it saves.
RECHECK_WAIT_S = 10.0


async def _free_recheck(hit, back_bytes, tr, wait_all=False):
    """
    D-175: the free comparison of a re-check photo with the published list. Waits for the
    one independent read of the photo (Cloud Vision, about 13 paise, or Tesseract when
    Vision is off, Rs 0; D-093) and asks review_checker.unchanged(). Its answer only ever
    decides "same, skip the paid read" (D-004, D-034). Any failure is "not_clear": the
    normal read runs, which costs money but never says "unchanged" wrongly.
    Waits RECHECK_WAIT_S at most; a replay (wait_all) waits for the whole read, so it repeats
    the original. Returns {"read": the BackRead, for the paid path to reuse, "check": the
    decision with its input text and reader, kept on the scan's trace (D-092)}.
    """
    t = time.monotonic()
    read = ocr_check.start_back_read(back_bytes)
    try:
        await run_in_threadpool(read.done.wait, None if wait_all else RECHECK_WAIT_S)
        got = ocr_check.result_of(read, hit["ingredients"])
        text = got.get("ocr_text") if got.get("available") else None
        check = (review_checker.unchanged(hit["ingredients"], hit["allergen_statement"], text) if text
                 else {"decision": "not_clear", "reason": got.get("reason") or "no_text"})
        check.update({"reader": got.get("reader"), "text": text})
    except Exception:                                                      # noqa: BLE001
        log.exception("free re-check failed")
        check = {"decision": "not_clear", "reason": "error", "reader": None, "text": None}
    check["product_version_id"] = str(hit["product_version_id"])
    tr["timings"]["recheck_ms"] = _ms(t)
    if check["decision"] == "unchanged":
        tr["ocr"] = {"back": {"reader": check["reader"], "text": check["text"],
                              "recheck": {k: v for k, v in check.items() if k != "text"}}}
    else:
        # Kept now, so a paid read that fails still stores what the free check saw.
        tr["ocr"] = {"back": {"recheck": check}}
    return {"read": read, "check": check}


# D-191: what must be the same for a scan to be the same as an earlier one: the photos (by
# content hash, matched in the query) and every choice sent with them. Where each photo came
# from (camera, upload) is not a choice: the same picture from the gallery is the same photo.
SAME_CHOICES = ("barcode", "barcode_answer", "avoid", "profiles", "pairing_confirmed", "compare_regulators",
                "images", "back_parts", "back_kinds", "accept_unconfirmed", "screen_pack", "table_only", "recheck")


def _same_photos(device_id, keys, request):
    """D-191: this phone's refused scan of these photos with these choices in the last day, or None."""
    for row in _persist(STORE.recent_refusals, device_id, keys.get("back"), keys.get("front")) or []:
        if (row["error_code"] or "").startswith("vision_blocked"):
            continue                       # D-172: Google's guard, not the photo; another read may pass
        then = row["request"] or {}
        if all(then.get(k) == request.get(k) for k in SAME_CHOICES):
            return row
    return None


# D-193: how long a late front answer is waited for after the result went (the SDK's own
# timeout is 120 s, and retries can add to it).
LATE_FRONT_WAIT_S = 300


def _save_late_front(front_read, request_id):
    """D-193: the front's split-read answer that came after the result, on the scan row."""
    front_read.done.wait(LATE_FRONT_WAIT_S)
    _persist(STORE and STORE.save_late_front, request_id, model_raw_front=front_read.raw,
             usage=dict(front_read.usage) or None,
             error=front_read.error or (None if front_read.done.is_set() else "no answer in time"))


def _ms(t0):
    return int((time.monotonic() - t0) * 1000)


def _str(v):
    return str(v) if v is not None else None


def _parse_screen_pack(raw):
    """
    D-130: the list from an earlier screen read, sent back by the phone's shop
    list so this pack's answer can say what differs. Only words: no names (D-074).
    """
    if not raw or not raw.strip():
        return None
    try:
        v = json.loads(raw)
        ings, stmt = v["ingredients"], v.get("allergen_statement")
        ok = (isinstance(ings, list) and 0 < len(ings) <= 200
              and all(isinstance(i, str) and len(i) <= 300 for i in ings)
              and (stmt is None or (isinstance(stmt, str) and len(stmt) <= 1000)))
    except (ValueError, TypeError, KeyError):
        ok = False
    if not ok:
        raise HTTPException(status_code=422, detail={
            "error": "bad_screen_pack",
            "detail": 'screen_pack is JSON {"ingredients": [text, ...], "allergen_statement": text or null}.'})
    return {"ingredients": ings, "allergen_statement": stmt}


def _compare_input(kind, **read):
    """D-200: {"compare_input": ...} for a pack Compare sets side by side, else {} (the answer unchanged)."""
    got = result_screen.compare_input(kind["code"], **read)
    return {} if got is None else {"compare_input": got}


def _withhold(kind, result):
    """
    D-140: a kind in shadow (infant foods) gets no result from the server, whatever the
    client: no score, grade or band (verdict, display), no claim, nutrition or EU/US
    result. The allergen lines, the kind and the ingredient list stay (the screen block).
    The scan is still stored whole for reviewers (save_scan ran before this).
    """
    fields, reason = pack_kind.withhold(kind["code"])          # D-200: the switch picks the reason
    if fields:
        for f in fields:
            result[f] = None
        result["withheld"] = {"fields": list(fields), "reason": reason}
    # D-139: a supplement has no score, grade, band or NOVA count; its flags stay for reviewers.
    for field, keys in pack_kind.WITHHOLD_KEYS.get(kind["code"], {}).items():
        if isinstance(result.get(field), dict):
            result[field] = {k: (None if k in keys else v) for k, v in result[field].items()}
            result.setdefault("withheld", {"fields": [], "reason": pack_kind.WITHHOLD_REASON[kind["code"]]})
            result["withheld"]["fields"].append(field + "." + ",".join(keys))
    return result


def _not_food_answer(kind, vision, reliability, barcode, images, keys, device_id, t0, tr, *,
                     avoid_codes, who, people):
    """
    D-190: the not-food result for a pack with no ingredient list read (an Ayurvedic
    medicine's formula). The same screen a not_food pack gets; no verdict, since there
    is no list to judge. Only the scan row is kept, for replay (D-092): no product,
    version or review item, with or without a barcode, so nothing reaches /review.
    """
    statement = vision.get("allergen_statement")
    scan_id = _persist(STORE and STORE.record_unlisted_scan, device_id=device_id, latency_ms=_ms(t0),
                       front_key=keys.get("front"), back_key=keys.get("back"), trace=tr,
                       resolved_via="barcode" if barcode else "no_barcode")
    extracted = {"ingredients": [], "ingredients_status": vision.get("ingredients_status"),
                 "front_claims": vision.get("front_claims", []), "allergen_statement": statement}
    if vision.get("pack_statements"):
        extracted["pack_statements"] = vision["pack_statements"]
    return _withhold(kind, {
        # D-060: first. No list read, so every avoided allergen is "couldn't confirm" (D-072).
        "allergens": allergen_block(avoid_codes, [], statement, reliable=False, who=who),
        "diet": diet_block(avoid_codes, [], reliable=False),
        "screen": result_screen.build(
            verdict=None, display=None, claim_check=None, extracted=extracted, reliability=reliability,
            profiles=people, allergen_confidence=0.0, allergen_reliable=False,
            has_barcode=barcode is not None, photos_sent=[r for _d, _m, r in images], kind=kind),
        "pack_kind": {k: kind[k] for k in ("code", "evidence", "review")},
        "scan_id": _str(scan_id),
        "request_id": tr["request_id"],
        "catalogue": {"source": "scan", "status": "not_saved", "reason": "not_food"},
        "product": vision.get("product"),
        "verdict": None,
        "display": None,
        "claim_check": None,
        "extracted": extracted,
        "reliability": reliability,
        "engine_version": ENGINE_VERSION,
    })


def _catalogue_kind(hit):
    """D-139: the kind stored on the version, or, for one stored before it, the category's (else food)."""
    if hit.get("pack_kind"):
        stored = hit.get("pack_kind_evidence") or {}
        return {"code": hit["pack_kind"], "evidence": stored.get("evidence") or [], "review": [],
                "licences": {}, "category": hit.get("category_code")}
    return pack_kind.decide({}, category=hit.get("category_code"))


def _checked_at(hit):
    """D-175: the version's last check, the newer of its publish (a person) and a photo match."""
    return max(d for d in (hit["verified_at"], hit.get("last_verified_at")) if d is not None)


def _pack_picture(hit):
    """D-182: the screen's pack picture, when the product has one: {"pack_picture": {...}} or {}."""
    pic = result_screen.pack_picture(hit.get("pack_picture"), lambda key: f"/pack-picture/{key}")
    return {"pack_picture": pic} if pic else {}


def _stored_veg_mark(hit):
    """D-198: the veg mark read when this version was scanned (raw_extraction), or None."""
    mark = hit.get("veg_mark")
    return mark if mark in ("veg", "non_veg") else None


def _catalogue_result(hit, avoid_codes, who, compare_regulators, profiles=(), screen_pack=None,
                      rechecked_on=None, now=None):
    """
    A result built from a reviewed catalogue version. The engine re-runs on the
    stored ingredient list, so the verdict always reflects the current rules and
    tables, not the ones in force when the pack was first reviewed.
    rechecked_on: D-175, this scan's photo matched the version for free (an ISO date).
    now: the time the 15 days are counted to (tests; a replay of the original scan).
    """
    ingredients = hit["ingredients"]
    raw = ", ".join(ingredients)
    verdict = engine.analyze(raw)
    kind = _catalogue_kind(hit)
    front_claims = hit["front_claims"] or []
    checked = _checked_at(hit)
    verified = checked.date().isoformat()
    team = hit["verified_at"].date().isoformat()
    photo = hit["last_verified_at"].date().isoformat() if hit.get("last_verified_at") else None
    # D-175: a food pack last checked over 15 days ago offers one photo of its list, unless this
    # scan just checked it, or D-073's avoid-list ask shows (it does the same job). One ask per
    # scan: the front (D-100) and table (D-168) offers wait for a later scan, also on the result
    # of the photo just sent for this check.
    now = now or dt.datetime.now(dt.timezone.utc if checked.tzinfo else None)
    due = (kind["code"] == "food" and not rechecked_on and not any(p["avoid"] for p in profiles)
           and now - checked > dt.timedelta(days=result_screen.RECHECK_AFTER_DAYS))
    wait = due or bool(rechecked_on)
    reliability = {
        "error": None, "ingredients_complete": True, "verdict_safe_to_display": True,
        "caveats": [], "source": "catalogue",
    }
    catalogue = {
        "source": "catalogue",
        "product_version_id": hit["product_version_id"],
        "last_verified": verified,
        # D-073: barcodes often survive reformulation. A profile with an
        # avoid list is asked for one back photo before relying on this.
        "allergen_recheck_suggested": bool(avoid_codes),
        # D-100: no front on file and none waiting for review; the app offers to add one.
        "front_wanted": bool(hit.get("front_wanted")) and not wait,
        # D-168: no nutrition table on file or waiting; the result offers one photo of it.
        "table_wanted": bool(hit.get("table_wanted")) and not wait,
        # D-175: who checked the label and when; a photo match is a machine check, kept apart.
        "team_verified": team,
        "photo_matched": photo,
        "recheck_due": due,
        "rechecked_on": rechecked_on,
    }
    display = rel.apply_display_rule(verdict, reliability)
    claim_check = _user_claim_check(claim_checker.check_claims(
        front_claims, raw, verdict, "read" if front_claims else "not_provided"), front_claims)
    extracted = {
        "ingredients": ingredients,
        "front_claims": front_claims,
        "allergen_statement": hit["allergen_statement"],
        "raw_text_sent_to_engine": raw,
    }
    return _withhold(kind, {
        # Reviewed data: read in full by a person, so the allergen gate is met.
        "allergens": allergen_block(avoid_codes, ingredients, hit["allergen_statement"], who=who,
                                    where="pack"),
        # D-198: the reviewed version's list and its stored veg mark ("on the pack we checked").
        "diet": diet_block(avoid_codes, ingredients, veg_mark=_stored_veg_mark(hit), where="pack",
                           product_name=hit["name"]),
        "screen": result_screen.build(
            verdict=verdict, display=display, claim_check=claim_check, extracted=extracted,
            reliability=reliability, profiles=profiles, allergen_confidence=1.0,
            allergen_reliable=True, catalogue=catalogue, screen_pack=screen_pack,
            nutrition=hit.get("nutrition"), kind=kind, veg_mark=_stored_veg_mark(hit), product_name=hit["name"],
            # D-139: no reading from the catalogue; the published name still says tablet or powder.
            nutra_input={"product": {"name": hit["name"], "variant": hit["variant"]}}) | _pack_picture(hit),
        "pack_kind": {k: kind[k] for k in ("code", "evidence", "review")},
        **_compare_input(kind, product={"name": hit["name"], "variant": hit["variant"]}),
        "catalogue": catalogue,
        "product": {"brand": hit["brand"], "name": hit["name"], "variant": hit["variant"],
                    "veg_mark": _stored_veg_mark(hit)},                 # D-198: kept for Compare
        "nutrition": nutrition.public(hit.get("nutrition")),
        "verdict": verdict,
        "display": display,
        "claim_check": claim_check,
        "extracted": extracted,
        "reliability": reliability,
        "disclosures": [result_screen.checked_disclosure(team, photo)] + rel.disclosures(reliability),
        "regulators": regulators.compare(verdict) if compare_regulators else None,
        "engine_version": ENGINE_VERSION,
    })


@app.get("/updates")
def updates(device_id: str):
    """
    D-070: packs this install sent for review, once decided. The app polls this
    on open ("we'll tell you when it's ready"); push notifications come later.
    """
    if review_routes.SERVICE is None:
        return {"updates": []}
    try:
        uid = str(uuid.UUID(device_id))
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "bad_device_id"})
    rows = review_routes.SERVICE.updates_for(uid)
    return {"updates": [
        {**r, "resolved_at": r["resolved_at"].isoformat(),
         "ready": r["resolution"] in ("published", "published_new_version", "no_change")}
        for r in rows]}


# D-109: the app shows the same sentence when both boxes are empty.
EMPTY_REPORT = "Tell us what the pack says, or what looks wrong. One of the two is enough."


def _has_text(value: Optional[str]) -> bool:
    """D-109: at least 3 characters after trimming, so "." or "ok" doesn't count."""
    return len((value or "").strip()) >= 3


@app.post("/report")
def report(req: ReportRequest):
    """D-076: "Report a mistake" on any result. Goes to the review queue.

    D-109: a report needs what the pack says or a note. A field choice alone
    ("Something else") leaves the reviewer nothing to act on.
    """
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable",
            "detail": "Reports need the database (INSIDELABEL_DB is not set).",
        })
    if not (req.scan_id or req.product_version_id):
        raise HTTPException(status_code=422, detail={
            "error": "no_subject", "detail": "Send the scan_id (or product_version_id) being reported.",
        })
    if not (_has_text(req.proposed_value) or _has_text(req.note)):
        raise HTTPException(status_code=422, detail={"error": "empty_report", "detail": EMPTY_REPORT})
    out = STORE.report(scan_id=req.scan_id, product_version_id=req.product_version_id,
                       device_id=req.device_id, field=req.field,
                       proposed_value=req.proposed_value, note=req.note)
    if out is None:
        raise HTTPException(status_code=404, detail={
            "error": "not_found", "detail": "No such scan or product version.",
        })
    return {"status": "received", **out}


# ---------------------------------------------------------------------------
# "Send it to us" (D-070)
# ---------------------------------------------------------------------------
_SEND_ERRORS = {
    "not_found": (404, "We couldn't find those scans from this phone."),
    "not_refused": (422, "Only scans we couldn't read can be sent."),
    "need_two_attempts": (422, "Try the photo twice first; then you can send it to us."),
    "no_photo": (422, "We don't have the photo for that scan any more."),
    "not_a_pack": (422, "Those photos don't show a food pack, so there's nothing for our team to read."),
    "no_barcode": (422, "Our catalogue is filed by barcode, so a pack without one can't be sent to our team."),
    "two_packs": (422, "Those photos show two different packs. Photograph the front and back of the same pack."),
}


# D-174: the table-only read's model call; None is a paid Gemini call. Tests set a recorded answer.
SENT_TABLE_CALL = None


def _read_sent_table(review_id):
    """
    D-174: after the reply, so the sender never waits: the table of a pack sent to us,
    from an earlier answer when one copied it (free), else one table-only read when the
    photos include the table. Stored for the reviewer; a failure is stored, never raised.
    """
    from insidelabel.review import table_read
    try:
        if review_routes.SERVICE is not None:
            table_read.read_for_item(review_routes.SERVICE, MEDIA, review_id, call=SENT_TABLE_CALL)
    except Exception:                                            # noqa: BLE001 - the item still works without it
        log.exception("table read for review item %s failed", review_id)


@app.post("/send-to-us")
def send_to_us(req: SendToUsRequest, request: Request, background: BackgroundTasks):
    """
    After two refused scans (D-070): "Send it to us - we'll check this pack and
    tell you when it's ready." Queues the photos for a reviewer; /updates
    reports back when the item is decided.
    """
    _rate_limit(request, "send_to_us", req.device_id, ratelimit.SEND_TEXT)
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable",
            "detail": "Sending needs the database (INSIDELABEL_DB is not set).",
        })
    try:
        device = str(uuid.UUID(req.device_id))
        scan_ids = list(dict.fromkeys(str(uuid.UUID(s)) for s in req.scan_ids))
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "bad_id", "detail": "device_id and scan_ids are UUIDs."})
    out = STORE.send_to_us(device_id=device, scan_ids=scan_ids)
    if "error" in out:
        status, text = _SEND_ERRORS[out["error"]]
        raise HTTPException(status_code=status, detail={"error": out["error"], "detail": text})
    if not out.get("duplicate"):
        background.add_task(_read_sent_table, out["review_id"])
    return {"status": "received", **out}


# ---------------------------------------------------------------------------
# Checking each photo as it's picked (D-104)
# ---------------------------------------------------------------------------
CHECK_MESSAGES = {
    "barcode_ok": "Barcode {code} read from the photo.",
    "no_barcode": "We couldn't find a barcode in this photo. Take it again close up and straight on, "
                  "with the whole barcode and its numbers in the frame.",
    "several_barcodes": "This photo shows more than one barcode. Take it again with only the pack's "
                        "barcode in the frame.",
    "back_ok": "Clear photo.",
    "front_ok": "Clear photo of the front.",
    "barcode_too": " Barcode {code} found on it too.",
}


def _photo_problem(role, code, message):
    """A photo the check turned down: the code and message as before, and D-170's short label."""
    return {"role": role, "ok": False, "problem": code, "message": message,
            "label": result_screen.problem(code, message)["label"], "barcode": None}


@app.post("/check-photo")
async def check_photo(
    request: Request,
    role: str = Form(..., description='"barcode", "back" or "front".'),
    photo: Optional[UploadFile] = File(None),
    device_id: Optional[str] = Form(None, examples=[""]),
    first_list: bool = Form(False, description="D-191: the scan's first ingredient-list photo; the free "
                                               "table hint looks only at this one (INSIDELABEL_TABLE_HINT)."),
):
    """
    D-104: the tick or cross the app shows on each photo as soon as it is picked.
    A barcode photo must show one retail barcode, read by zxing-cpp (never
    typed, never read by the model); a label photo must be a readable picture.
    No model call and nothing stored: this costs nothing but CPU.
    """
    _rate_limit(request, "check_photo", device_id, ratelimit.SCAN_TEXT)
    if role not in ("barcode", "back", "front"):
        raise HTTPException(status_code=422, detail={"error": "bad_role", "detail": 'role is "barcode", "back" or "front".'})
    img = await _read_image(photo, role)
    if img is None:
        raise HTTPException(status_code=422, detail={"error": "no_photo", "detail": "Send a photo."})
    data, mime, _role = img
    bad = photo_check.check(data, mime, role, min_size=role != "barcode")
    if bad:
        return _photo_problem(role, bad[0], bad[1])
    good, reasons = await run_in_threadpool(barcode_rules.read_from_photo, data)
    code = good[0] if len(good) == 1 else None
    if role == "barcode":
        if len(good) > 1:
            return _photo_problem(role, "several_barcodes", CHECK_MESSAGES["several_barcodes"])
        if code:
            return {"role": role, "ok": True, "problem": None,
                    "message": CHECK_MESSAGES["barcode_ok"].format(code=code), "barcode": code}
        if reasons:                               # a barcode, but not a retail pack's (a book, a carton…)
            return _photo_problem(role, reasons[0], barcode_rules.MESSAGES[reasons[0]])
        return _photo_problem(role, "no_barcode", CHECK_MESSAGES["no_barcode"])
    msg = CHECK_MESSAGES[f"{role}_ok"] + (CHECK_MESSAGES["barcode_too"].format(code=code) if code else "")
    out = {"role": role, "ok": True, "problem": None, "message": msg, "barcode": code}
    if role == "back" and first_list and table_hint.enabled():
        # D-191: a free local read; a nutrition table with no list word gets one question.
        hint = await run_in_threadpool(table_hint.check, data)
        log.info("table hint: fires=%s words=%s list_word=%s ms=%s", hint["fires"], len(hint["table_words"]),
                 hint["list_word"], hint["ms"])
        if hint["fires"]:
            out["hint"] = dict(result_screen.TABLE_HINT)
    return out


SIDE_WAIT_S = 20


@app.post("/side-photo")
async def side_photo(
    request: Request,
    photo: Optional[UploadFile] = File(None, description="A photo of the pack's side."),
    found: str = Form("[]", description="Regulation 4's statement ids the result already found, as JSON."),
    missing: str = Form("[]", description="The ids it didn't see, as JSON (the result's notices.side.missing)."),
    photos: int = Form(2, description="How many photos the result was read from so far."),
    sides: int = Form(0, description="How many side photos were added before this one."),
    scan_id: Optional[str] = Form(None, examples=[""], description="The scan whose result this adds to."),
    device_id: Optional[str] = Form(None, examples=[""]),
    photo_source: Optional[str] = Form(None, examples=[""], description='"camera" or "upload" (D-106).'),
):
    """
    D-201: "Photograph the side" on an infant result. Tins and boxes often print regulation 4's
    notices on a side, so a result that didn't see them can add one photo (at most two). Its
    text is read by Cloud Vision only (about 13 paise; Tesseract on the server, Rs 0, when
    Vision is off, D-093): no model call, not one of the day's photo scans, and only the missing
    statements are looked for (lenses/infant.side_found). The answer is the result's new notices
    block, in the server's words (D-091), and the statements found, for Compare. Stateless: the
    phone sends what its result found and missed. The photo is its own scan row ('side'),
    linked to the scan, for replay (D-092) and for /review beside the scan; it never changes a
    catalogue version or creates a review item (Sushil, accepting D-201).
    """
    _rate_limit(request, "side_photo", device_id, ratelimit.SCAN_TEXT)
    if not pack_kind.infant_to_users():
        raise HTTPException(status_code=404, detail={"error": "not_available", "detail": "Not available."})
    try:
        found_ids, missing_ids = json.loads(found or "[]"), json.loads(missing or "[]")
    except ValueError:
        found_ids = missing_ids = None
    if isinstance(found_ids, list) and isinstance(missing_ids, list):
        found_ids = [infant_lens.private_id(i) if isinstance(i, str) else i for i in found_ids]
        missing_ids = [infant_lens.private_id(i) if isinstance(i, str) else i for i in missing_ids]
    known = set(infant_lens.SIDE_IDS) | {r["id"] for r in infant_lens.RULES["statements"]}
    if (not isinstance(found_ids, list) or not isinstance(missing_ids, list) or not missing_ids
            or not all(isinstance(i, str) and i in known for i in found_ids + missing_ids)
            or set(found_ids) & set(missing_ids) or not 1 <= photos <= 9 or not 0 <= sides):
        raise HTTPException(status_code=422, detail={"error": "bad_notices",
                                                     "detail": "found and missing are lists of statement ids."})
    if sides >= result_screen.INFANT_SIDE_MAX:
        raise HTTPException(status_code=422, detail={"error": "side_limit",
                                                     "detail": "Two side photos have been added to this result."})
    if photo_source and photo_source.strip() not in ("camera", "upload"):
        raise HTTPException(status_code=422, detail={"error": "bad_photo_source",
                                                     "detail": 'photo_source is "camera" or "upload".'})
    img = await _read_image(photo, "side")
    if img is None:
        raise HTTPException(status_code=422, detail={"error": "no_photo", "detail": "Send a photo."})
    data, mime, _role = img
    bad = photo_check.check(data, mime, "back")
    if bad:
        raise HTTPException(status_code=415 if bad[0] == "not_an_image" else 422, detail={
            "error": bad[0], "role": "side", "detail": bad[1], "label": result_screen.PROBLEM_LABEL[bad[0]]})
    t0 = time.monotonic()
    read = ocr_check.start_back_read(data)
    try:
        await run_in_threadpool(read.done.wait, SIDE_WAIT_S)
        got = ocr_check.result_of(read, [])
    except Exception:                                                      # noqa: BLE001
        log.exception("side photo read failed")
        got = {"available": False, "reason": "error"}
    text = got.get("ocr_text") if got.get("available") else None
    new = infant_lens.side_found(text, missing_ids) if text else []
    rows = {r["id"]: r for r in infant_lens.RULES["statements"]}
    statements = [{"id": i, "text": rows[i]["text"], "found": i in found_ids or i in new,
                   "basis": rows[i]["fssai_basis"]} for i in rows if i in found_ids or i in missing_ids]
    no_milk = None
    if "no_milk" in found_ids or "no_milk" in missing_ids:
        no_milk = {"text": infant_lens.RULES["no_milk"]["text"], "basis": infant_lens.RULES["no_milk"]["fssai_basis"],
                   "found": "no_milk" in found_ids or "no_milk" in new}
    block = result_screen.infant_notices(statements, no_milk, photos=photos + (1 if text else 0),
                                         sides=sides + (1 if text else 0), last_found=new if text else None)
    if not text:
        block["lines"].append(result_screen.INFANT_SIDE["unread"])
    keys = _save_images([(data, mime, "back")])
    tr = {"request_id": trace.current_request_id(), "build": trace.BUILD, "data_version": trace.DATA_VERSION,
          "request": {"route": "side-photo", "parent_scan_id": scan_id, "found": found_ids, "missing": missing_ids,
                      "photos": photos, "sides": sides,
                      "photo_sources": {"side": photo_source.strip()} if photo_source else {}},
          "timings": {"total_ms": _ms(t0)},
          "ocr": {"side": {"reader": got.get("reader"), "text": text, "reason": got.get("reason"), "found": new}}}
    side_id = _persist(STORE.record_side_photo, parent_scan_id=scan_id, device_id=device_id,
                       latency_ms=_ms(t0), back_key=keys.get("back"), trace=tr) if STORE else None
    log.info("side photo: reader=%s found=%s of %s", got.get("reader"), new, missing_ids)
    return {"read": bool(text), "found": [{"id": i, "printed": next(m for m in (rows.get(i) or infant_lens.RULES["no_milk"])["match"]
                                                                    if infant_lens._has(infant_lens.norm(text), m))}
                                          for i in new],
            "notices": block, "photos": photos + (1 if text else 0), "sides": sides + (1 if text else 0),
            "scan_id": _str(side_id), "request_id": tr["request_id"]}


# ---------------------------------------------------------------------------
# Access, terms and feedback (D-105, D-102; no invite codes since D-184)
# ---------------------------------------------------------------------------
@app.get("/access")
def access(device_id: str = ""):
    """Agreed to the current rules (D-105)? The app's switches (D-171). The app asks on open."""
    agreed = bool(STORE and device_id and _persist(STORE.has_agreed, device_id, TERMS["version"]))
    return {"agreed": agreed, "terms_version": TERMS["version"], "live_shutter": _live_shutter()}


@app.get("/pack-picture/{key}")
def pack_picture(key: str):
    """
    D-182: a pack picture, the small reviewed copy of a pack's front. Only a key that is a
    picture being shown is served; every other stored photo stays private.
    """
    got = None
    if STORE and MEDIA and _persist(pictures.shown, STORE.conninfo, key):
        got = MEDIA.get(key)
    if got is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    data, mime = got
    # Keys are content hashes: the bytes behind one never change.
    return Response(data, media_type=mime, headers={"Cache-Control": "public, max-age=604800, immutable"})


@app.get("/terms")
def terms():
    """D-105: the "Before you start" text the app shows, with its version."""
    return TERMS


@app.post("/agree")
def agree(req: AgreeRequest, request: Request):
    """D-105: record that this install agreed to this version of the rules."""
    _rate_limit(request, "agree", req.device_id, ratelimit.PROBLEM_TEXT)
    try:
        device = str(uuid.UUID(req.device_id))
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "bad_device_id"})
    if req.terms_version != TERMS["version"]:
        raise HTTPException(status_code=409, detail={
            "error": "terms_changed", "terms_version": TERMS["version"],
            "detail": "The rules have changed. Please read them again."})
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable", "detail": "Agreements need the database (INSIDELABEL_DB is not set)."})
    STORE.agree(device, req.terms_version)
    return {"status": "agreed", "terms_version": TERMS["version"]}


@app.post("/feedback")
def feedback(req: FeedbackRequest, request: Request):
    """D-102 "Send feedback": a user's comment and optional 1-5 rating."""
    _rate_limit(request, "feedback", req.device_id, ratelimit.FEEDBACK_TEXT)
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable", "detail": "Feedback needs the database (INSIDELABEL_DB is not set)."})
    comment = (req.comment or "").strip()
    if not comment:
        raise HTTPException(status_code=422, detail={"error": "empty_feedback", "detail": "Write a few words first."})
    fid = STORE.save_feedback(device_id=req.device_id, comment=comment, rating=req.rating,
                              screen=req.screen, app_version=req.app_version)
    return {"status": "received", "feedback_id": fid}


@app.post("/forget")
def forget(req: ForgetRequest, request: Request):
    """
    D-129 "Delete my data" (DPDP Act s.12(3)). No agreement needed: anyone can
    erase. The database goes first; a
    photo whose file can't be deleted now keeps its unlinked scan row, so the
    30-day job deletes it later.
    """
    _rate_limit(request, "forget", req.device_id, ratelimit.FORGET_TEXT)
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable", "detail": "We couldn't reach our records. Try again in a minute."})
    out = STORE.forget(req.device_id)
    if not out["found"]:
        return {"status": "nothing_stored"}
    photos = 0
    for key in out.pop("photo_keys"):
        try:
            if MEDIA is not None and MEDIA.delete(key):
                photos += 1
            STORE.mark_photo_deleted(key)
        except Exception:                                      # noqa: BLE001 - the retention job retries
            log.exception("forget: photo delete failed")
    out = {k: v for k, v in out.items() if k != "found"} | {"photos": photos}
    log.info("forget: %s", out)                                   # counts only, never the id
    return {"status": "deleted", "deleted": out}


# ---------------------------------------------------------------------------
# Report a problem (D-092)
# ---------------------------------------------------------------------------
MAX_PROBLEM_BYTES = 100_000
# D-074 belt and braces: the app never sends these, and if one arrives it is dropped.
_NAME_KEYS = {"nickname", "name", "who", "nicknames"}


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if k.lower() not in _NAME_KEYS}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


@app.post("/problem")
def problem(req: ProblemRequest, request: Request):
    """
    The app went wrong: a user tapped "Report a problem", or the app crashed.
    Stores the phone's event trail against the scans it names, and holds those
    scans' photos past retention (D-080). tools/repro.py replays it.
    """
    _rate_limit(request, "problem", req.device_id, ratelimit.PROBLEM_TEXT)
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable",
            "detail": "Problem reports need the database (INSIDELABEL_DB is not set).",
        })
    if req.kind not in ("user", "auto"):
        raise HTTPException(status_code=422, detail={"error": "bad_kind", "detail": 'kind is "user" or "auto".'})
    client, events = _scrub(req.client), _scrub(req.events)
    if len(json.dumps(client)) + len(json.dumps(events)) > MAX_PROBLEM_BYTES:
        raise HTTPException(status_code=413, detail={
            "error": "report_too_large", "detail": f"client + events must be under {MAX_PROBLEM_BYTES} bytes.",
        })
    scan_id = None
    if req.scan_id:
        try:
            scan_id = str(uuid.UUID(req.scan_id))
        except ValueError:
            scan_id = None
    request_id = req.request_id if req.request_id and trace.accept_or_new(req.request_id) == req.request_id else None
    out = STORE.save_problem(
        kind=req.kind, device_id=req.device_id, scan_id=scan_id, request_id=request_id,
        comment=req.comment, app_version=req.app_version, build=trace.BUILD,
        data_version=trace.DATA_VERSION, client=client, events=events, signature=req.signature)
    return {"status": "received", **out}


# ---------------------------------------------------------------------------
MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


# D-119: how a part of the list is named in a photo-check message.
_PART_LABEL = {"back2": "back (part 2)", "back3": "back (part 3)"}


async def _read_image(upload, role):
    if upload is None:
        return None
    data = await upload.read()
    if not data:
        return None
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail={
            "error": "image_too_large",
            "detail": f"{role} image is {len(data)} bytes; limit is {MAX_IMAGE_BYTES}.",
        })
    mime = upload.content_type or "image/jpeg"
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail={
            "error": "unsupported_image_type",
            "detail": f"{role} image content_type {mime!r} is not supported.",
        })
    return (data, mime, role)


@app.post("/scan")
async def scan(
    request: Request,
    background: BackgroundTasks,
    back: Optional[UploadFile] = File(None, description="Back of pack - the ingredient list."),
    front: Optional[UploadFile] = File(None, description="Front of pack - marketing claims."),
    back2: Optional[UploadFile] = File(None, description="D-119: the ingredient list's second part, when it doesn't fit one photo."),
    back3: Optional[UploadFile] = File(None, description="D-119: the list's third part."),
    pairing_confirmed: bool = Form(False, description="User confirms both images show the same pack."),
    # Every text field carries an empty example: /docs otherwise pre-fills them
    # with the word "string", and avoid=string is refused as an unknown allergen
    # (422), while replay=string would be read as the model's answer. (Marking
    # fields include_in_schema=False has no effect inside a multipart form.)
    replay: Optional[str] = Form(None, examples=[""],
                                 description="Testing only: recorded model JSON, used instead of a model call. Needs INSIDELABEL_ALLOW_REPLAY=on (D-101). Leave empty."),
    avoid: Optional[str] = Form(None, examples=[""], description="Comma-separated allergen codes, e.g. 'milk,gluten'."),
    who: Optional[str] = Form(None, examples=[""],
                              description="Old clients only: a name for allergen text. The app sends none (D-074)."),
    compare_regulators: bool = Form(False, description="Also return EU and US status. Information only."),
    barcode: Optional[str] = Form(None, examples=[""], description="EAN/UPC digits from the pack, if the camera read one."),
    back_source: Optional[str] = Form(None, examples=[""],
                                      description='D-106: "camera" (taken in the app) or "upload" (gallery, computer); '
                                                  'D-171: "live" (the app\'s own shutter).'),
    front_source: Optional[str] = Form(None, examples=[""], description='D-106: as back_source.'),
    back2_source: Optional[str] = Form(None, examples=[""], description='D-106: as back_source, for back2.'),
    back3_source: Optional[str] = Form(None, examples=[""], description='D-106: as back_source, for back3.'),
    barcode_source: Optional[str] = Form(None, examples=[""],
                                         description='D-104: "camera" (live scanner) or "photo" (read by /check-photo).'),
    barcode_answer: Optional[str] = Form(None, examples=[""],
                                         description='D-146: "confirmed" (the digits matched the pack) or "rescanned" '
                                                     '(read after "Scan again").'),
    device_id: Optional[str] = Form(None, examples=[""], description="Anonymous install id (UUID). No personal data."),
    profiles: Optional[str] = Form(None, examples=[""],
                                   description='JSON [{"ref","age","avoid"}], up to 3. No names (D-074).'),
    accept_unconfirmed: bool = Form(False, description="D-118: 'use this one anyway' after a clearer-photo request."),
    back_kinds: Optional[str] = Form(None, examples=[""],
                                     description='D-174: what each back part shows, in order, comma separated: '
                                                 '"list" or "table" (D-171 sends the table last).'),
    table_only: bool = Form(False, description="D-168: the back photo is a published pack's nutrition table; "
                                               "only the table is read and added for review."),
    screen_pack: Optional[str] = Form(None, examples=[""],
                                      description='D-130: JSON {"ingredients", "allergen_statement"} from an earlier '
                                                  'result read from a screen; the answer says what differs on this pack.'),
    recheck: bool = Form(False, description="D-175: a photo of a published pack's ingredient list, to check it "
                                            "again. Compared with the published list for free first; read by the "
                                            "model only when it isn't clearly the same."),
    replay_front: Optional[str] = Form(None, examples=[""],
                                       description='Testing only, with replay: the front\'s own recorded answer from a '
                                                   'split read (D-193), or "-" when it wasn\'t joined. Leave empty.'),
):
    """
    barcode -> reviewed catalogue entry, else images -> Gemini -> engine -> claim check.

    The back of pack is the only required input: it carries the ingredient
    list, which is the only thing the engine can reason about. The front is
    optional and only enables the claim check.
    """
    t0 = time.monotonic()
    # Form tools (/docs included) can send an empty box as "". An empty replay is
    # not a model answer, and an empty avoid is not an avoid list.
    replay = replay if replay and replay.strip() else None
    # D-193: only beside a replay; a live scan never takes an answer from the form.
    replay_front = replay_front if replay is not None and replay_front and replay_front.strip() else None
    if replay is not None and not _replay_allowed():
        # D-101: refused before anything is read or stored, like a 429 (D-095).
        log.warning("replay refused: INSIDELABEL_ALLOW_REPLAY is off")
        raise HTTPException(status_code=403, detail={
            "error": "replay_disabled",
            "detail": "The replay field is for testing and is switched off on this server.",
        })
    # D-095: before any photo is read or model called. A barcode-only lookup
    # costs nothing and has its own budget.
    lookup_only = bool(barcode and barcode.strip()) and back is None and front is None and replay is None
    _rate_limit(request, "lookup" if lookup_only else "scan", device_id, ratelimit.SCAN_TEXT)
    avoid = avoid if avoid and avoid.strip() else None
    avoid_codes = parse_avoid(avoid)
    people = parse_profiles(profiles)
    if avoid is None:
        # D-060: the top-level allergen block covers every profile's avoid list.
        avoid_codes = list(dict.fromkeys(c for p in people for c in p["avoid"]))
    barcode = _clean_barcode(barcode)
    screen_pack = _parse_screen_pack(screen_pack)
    # D-104: where the barcode came from. The app offers only the live scanner
    # and a photo read by /check-photo; typed numbers aren't accepted from it.
    barcode_source = barcode_source if barcode_source and barcode_source.strip() else None
    if barcode_source not in (None, "camera", "photo"):
        raise HTTPException(status_code=422, detail={
            "error": "bad_barcode_source", "detail": 'barcode_source is "camera" or "photo".'})
    # D-146: what the user said about the digits, kept with the scan as supporting evidence
    # for a reviewer (never instead of D-143's check). Nothing is kept for a dropped code.
    barcode_answer = barcode_answer if barcode_answer and barcode_answer.strip() else None
    if barcode_answer not in (None, "confirmed", "rescanned"):
        raise HTTPException(status_code=422, detail={
            "error": "bad_barcode_answer", "detail": 'barcode_answer is "confirmed" or "rescanned".'})
    # D-168: a table photo is for a published pack that has no table yet: its barcode and
    # one back photo, nothing else. A replay without a store (repro, tools) has no hit.
    table_hit = None
    if table_only:
        if not barcode or back is None or front is not None or back2 is not None or back3 is not None:
            raise HTTPException(status_code=422, detail={
                "error": "bad_table_photo",
                "detail": "A nutrition table photo goes with the pack's barcode and nothing else."})
        table_hit = _persist(STORE.find_current, barcode) if STORE else None
        if STORE and not (table_hit and table_hit.get("table_wanted")):
            raise HTTPException(status_code=422, detail={
                "error": "table_not_wanted",
                "detail": "This pack's nutrition table is already on file or waiting to be checked."})

    images = []
    for upload, role in ((back, "back"), (back2, "back2"), (back3, "back3"), (front, "front")):
        img = await _read_image(upload, role)
        if img:
            images.append(img)
    roles = [r for _d, _m, r in images]
    if ("back2" in roles or "back3" in roles) and ("back" not in roles or ("back3" in roles and "back2" not in roles)):
        raise HTTPException(status_code=422, detail={
            "error": "parts_out_of_order",
            "detail": "Send the ingredient list's parts in order: back, then back2, then back3."})
    # D-106: where each photo came from, as the app says. An AI-made or edited
    # picture can only arrive as an upload, so reviewers see uploads marked.
    # Recorded, not proved: a client could claim "camera".
    photo_sources = {}
    for role, said in (("back", back_source), ("back2", back2_source), ("back3", back3_source),
                       ("front", front_source)):
        said = said.strip() if said and said.strip() else None
        if said is None:
            continue
        # D-171: "live" is the app's own shutter; "camera" the phone's camera app.
        if said not in ("camera", "live", "upload"):
            raise HTTPException(status_code=422, detail={
                "error": "bad_photo_source", "detail": f'{role}_source is "camera", "live" or "upload".'})
        if any(r == role for _d, _m, r in images):
            photo_sources[role] = said
    # D-174: which back part is the nutrition table, as the app says, so a person reading a
    # pack sent to us knows the photos hold its table. Recorded, like photo_sources.
    kinds = None
    if back_kinds and back_kinds.strip():
        kinds = [k.strip() for k in back_kinds.split(",")]
        n_back = sum(1 for _d, _m, r in images if r in ("back", "back2", "back3"))
        if len(kinds) != n_back or any(k not in ("list", "table") for k in kinds):
            raise HTTPException(status_code=422, detail={
                "error": "bad_back_kinds",
                "detail": 'back_kinds names each back part in order: "list" or "table", comma separated.'})
    # D-103: a file that can't be a readable label never costs a model read.
    # Replayed answers skip it: they were read from photos checked at the time.
    if replay is None:
        for data, mime, role in images:
            bad = photo_check.check(data, mime, _PART_LABEL.get(role, role))
            if bad:
                log.warning("photo refused: %s %s", role, bad[0])
                raise HTTPException(status_code=415 if bad[0] == "not_an_image" else 422, detail={
                    "error": bad[0], "role": role, "detail": bad[1],
                    "label": result_screen.PROBLEM_LABEL[bad[0]]})                 # D-170

    # D-119: a long list in parts becomes one back photo here; from now on
    # the scan is ordinary (one image for Gemini, Cloud Vision, storage, replay).
    parts = [(d, m) for d, m, r in images if r in ("back", "back2", "back3")]
    # D-201: how many photos this scan read, for an infant result's "on these 2 photos".
    n_photos = len(parts) + sum(1 for _d, _m, r in images if r == "front")
    if len(parts) > 1:
        try:
            joined = photo_join.join(parts)
        except photo_join.JoinError as e:
            raise HTTPException(status_code=415, detail={"error": "parts_unreadable", "detail": str(e)})
        images = [(joined[0], joined[1], "back")] + [x for x in images if x[2] == "front"]

    # D-092: everything needed to replay this scan, minus the photos (kept by
    # media) and the model's answer (added once we have it). `who` is left out:
    # an old client may put a name in it (D-074).
    tr = {
        "request_id": trace.current_request_id(), "build": trace.BUILD,
        "data_version": trace.DATA_VERSION, "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "request": {"barcode": barcode, "barcode_source": barcode_source, "barcode_answer": barcode_answer,
                    "photo_sources": photo_sources,
                    "avoid": avoid_codes if avoid is not None else None,
                    "profiles": people, "pairing_confirmed": pairing_confirmed,
                    "compare_regulators": compare_regulators,
                    "images": [r for _d, _m, r in images], "back_parts": max(1, len(parts)),
                    "back_kinds": kinds,
                    "replay": replay is not None,
                    "accept_unconfirmed": accept_unconfirmed, "screen_pack": screen_pack,
                    "table_only": table_only, "recheck": recheck},
        # D-193: how the label is read (model, thinking level, image detail, split), so a
        # replay and the speed numbers know which setting each scan was read with.
        "timings": {"read": gemini.read_settings()},
    }

    # D-024: a barcode alone is a catalogue lookup - no vision call, ~₹0.
    # Photos, when sent, are always read: that is how a reformulation under an
    # unchanged barcode gets noticed, and how the D-073 allergy re-check works.
    if barcode and not images and replay is None:
        hit = _persist(STORE.find_current, barcode) if STORE else None
        if hit is None:
            # D-146: nothing is stored for a code not in the catalogue; the app shows its
            # digits back to be checked against the pack before the ingredients photo.
            raise HTTPException(status_code=404, detail={
                "error": "not_in_catalogue",
                "detail": "We haven't checked this pack yet.",
                "hint": "Photograph the back of the pack (the ingredient list).",
                "barcode_check": result_screen.barcode_check(barcode),
            })
        result = _catalogue_result(hit, avoid_codes, who, compare_regulators, people, screen_pack)
        result["scan_id"] = _str(_persist(STORE.record_cache_hit, hit, device_id=device_id,
                                          latency_ms=_ms(t0), trace=tr))
        return result

    # D-100: the front alone, for a pack the catalogue already has. The answer
    # is still the reviewed record; the photo goes to a reviewer, who reads the
    # claims from it. No model call: a front on its own can't change a verdict.
    if barcode and replay is None and [r for _d, _m, r in images] == ["front"]:
        hit = _persist(STORE.find_current, barcode) if STORE else None
        if hit is None:
            raise HTTPException(status_code=422, detail={
                "error": "back_required",
                "detail": "We haven't checked this pack yet, so we need the ingredient list first.",
                "hint": "Photograph the back of the pack (the ingredient list).",
            })
        keys = _save_images(images)
        result = _catalogue_result(hit, avoid_codes, who, compare_regulators, people)
        saved = _persist(STORE.add_front, hit, front_key=keys.get("front"), device_id=device_id,
                         latency_ms=_ms(t0), trace=tr) if keys.get("front") else None
        result["scan_id"] = saved["scan_id"] if saved else None
        # Received means a reviewer has it, now or already; the app stops asking.
        result["catalogue"]["front_received"] = bool(saved)
        result["catalogue"]["front_wanted"] = not saved
        return result

    keys = _save_images(images)

    if not images and replay is None:
        raise HTTPException(status_code=422, detail={
            "error": "no_images",
            "detail": "Supply at least a back-of-pack image.",
        })

    # D-191 (Sushil, 2026-10-10): the same photos and choices as a scan this phone sent in the
    # last 24 hours that was refused get that scan's answer again, from its stored read (D-092):
    # no Gemini or Cloud Vision call, and not counted in the day's photo scans (D-148). Today's
    # rules run on it, so a clearer-photo ask already made goes to the result (one per pack).
    repeat_of, repeat_text = None, False
    if replay is None and STORE and device_id and keys.get("back") and not table_only:
        earlier = _same_photos(device_id, keys, tr["request"])
        if earlier:
            repeat_of = str(earlier["id"])
            replay = earlier["model_raw"]
            # D-192: the answer used is the earlier scan's, so its reader is this one's too.
            then_read = (earlier.get("timings") or {}).get("read")
            tr["timings"]["read"] = dict(then_read) if then_read else gemini.gemini_settings()
            tr["timings"]["read"].setdefault("reader", "gemini")
            joined = (earlier.get("timings") or {}).get("front_joined")
            if joined is not None:
                replay_front = earlier.get("model_raw_front") if joined else None
                replay_front = replay_front or gemini.SKIPPED_FRONT
            stored = ((earlier.get("ocr") or {}).get("back") or {})
            repeat_text = stored.get("reader") == "cloud_vision" and stored.get("text") is not None
            if repeat_text:
                cloud_vision.remember(next((d for d, _m, r in images if r == "back"), None), stored["text"])
            tr["request"]["repeat_of"] = repeat_of
            ratelimit.LIMITER.give_back("scan", device=str(uuid.UUID(str(device_id))),
                                        ip=ratelimit.client_ip(request))
            log.info("same photos as scan %s: answered from its stored read", repeat_of)

    # The model call and the OCR are blocking; on worker threads they don't freeze
    # every other request for 10-15 s. The independent read of the back photo
    # doesn't need the model's answer, so it starts now, alongside Gemini: Cloud
    # Vision, or Tesseract's passes when Vision refuses (scan-speed, 2026-10-01).
    # Every check below uses this one read. If the model fails, a Vision read
    # (~13 paise) was spent for nothing: rare, and cheaper than the wait.
    back_bytes = next((d for d, _m, r in images if r == "back"), None)
    # D-175: a re-check photo of a published pack is compared with the published list
    # for free first; only a photo that isn't clearly the same goes on to the paid read.
    recheck_check = None
    if recheck and barcode and back_bytes and not table_only and [r for _d, _m, r in images] == ["back"]:
        rc_hit = _persist(STORE.find_current, barcode) if STORE else None
        if rc_hit:
            free = await _free_recheck(rc_hit, back_bytes, tr, wait_all=replay is not None)
            back_read, recheck_check = free["read"], free["check"]
            if recheck_check["decision"] == "unchanged":
                saved = _persist(STORE.record_recheck, rc_hit, back_key=keys.get("back"), device_id=device_id,
                                 latency_ms=_ms(t0), trace=tr)
                at = saved["last_verified_at"] if saved else dt.datetime.now(dt.timezone.utc)
                if saved:
                    rc_hit = {**rc_hit, "last_verified_at": at}
                result = _catalogue_result(rc_hit, avoid_codes, who, compare_regulators, people, screen_pack,
                                           rechecked_on=at.date().isoformat())
                result["scan_id"] = saved and saved["scan_id"]
                result["catalogue"]["recheck"] = "unchanged"
                return result
    if recheck_check is None:
        # D-191: a repeat reads nothing again: its stored Cloud Vision text, or no second read
        # at all when the earlier scan had none in time (its answer didn't use one either).
        back_read = None if repeat_of and not repeat_text else ocr_check.start_back_read(back_bytes)
    # D-092: how long we waited on retries, so a slow scan can be told apart as
    # "the model was busy" (retries) or "the model was slow" (none).
    retries = tr["timings"].setdefault("vision_retries", [])

    def on_retry(attempt, delay, err):
        retries.append({"attempt": attempt, "wait_s": round(delay, 1), "error": type(err).__name__})
        log.warning("model retry %s after %s, waiting %.1fs", attempt, type(err).__name__, delay)

    # D-193: with INSIDELABEL_READ_SPLIT_FRONT=on the front is read in its own call, started
    # now; the result waits only for the back's. A replay of a split scan repeats it from the
    # recorded front answer (or "-": it wasn't joined).
    front_imgs = [x for x in images if x[2] == "front"]
    split = bool(front_imgs) and not table_only and (
        replay_front is not None if replay is not None else tr["timings"]["read"]["split_front"])
    front_read = None
    if split and replay_front != gemini.SKIPPED_FRONT:
        front_read = gemini.FrontRead(front_imgs, raw_response=replay_front)
        if replay is not None:
            await run_in_threadpool(front_read.done.wait)
    t_vision = time.monotonic()
    try:
        try:
            if split:
                vision, corrections = await run_in_threadpool(gemini.analyze_split, images, front_read,
                                                              raw_response=replay, on_attempt=on_retry)
            else:
                vision, corrections = await run_in_threadpool(gemini.analyze_images, images, raw_response=replay,
                                                              on_attempt=on_retry)
        except gemini.VisionError as e:
            _record_read(tr, getattr(e, "read", None))
            raise
    except gemini.VisionBlocked as e:
        # D-172: a guard stopped the answer (report #7: RECITATION on a Britannia pack), after
        # D-172's retries. Not the photo and not a 502: a refusal a person can read instead.
        return _blocked_refusal(e, tr, back_read=back_read, back_bytes=back_bytes,
                                t_vision=t_vision, t0=t0, keys=keys, images=images, barcode=barcode,
                                device_id=device_id, avoid_codes=avoid_codes, who=who, people=people)
    except gemini.VisionConfigError as e:
        # Our setup (key, credit, billing), not the label and not a busy moment.
        # The user is told it's unavailable; the developer gets an alarm.
        tr["timings"]["vision_ms"] = _ms(t_vision)
        _model_error(tr, e)
        status = getattr(e, "status", None) or "no_key"
        log.error("model setup problem: %s", e)
        _persist(STORE and STORE.record_failed_scan, "vision_failed", error_code=f"vision_config:{status}",
                 device_id=device_id, latency_ms=_ms(t0),
                 front_key=keys.get("front"), back_key=keys.get("back"), trace=tr)
        _setup_alarm(f"vision_config:{status}", str(e))
        raise HTTPException(status_code=503, detail={
            "error": "vision_not_configured",
            "detail": "The label reader isn't available right now.",
            "retryable": False,
        })
    except gemini.VisionUnavailable as e:
        tr["timings"]["vision_ms"] = _ms(t_vision)
        _model_error(tr, e)
        _persist(STORE and STORE.record_failed_scan, "vision_unavailable",
                 device_id=device_id, latency_ms=_ms(t0),
                 front_key=keys.get("front"), back_key=keys.get("back"), trace=tr)
        # 503 with Retry-After, not 502. The images were fine and the request
        # was fine; the upstream model was busy. A client should retry this,
        # and a user should not be told their photo failed.
        raise HTTPException(status_code=503, detail={
            "error": "vision_unavailable",
            "detail": str(e),
            "retryable": True,
            "hint": "Model overloaded upstream. Already retried with backoff; try again shortly.",
        })
    except gemini.VisionError as e:
        tr["timings"]["vision_ms"] = _ms(t_vision)
        tr["model_raw"] = getattr(e, "raw_text", None)
        _model_error(tr, e)
        _persist(STORE and STORE.record_failed_scan, "vision_failed",
                 device_id=device_id, latency_ms=_ms(t0),
                 front_key=keys.get("front"), back_key=keys.get("back"), trace=tr)
        raise HTTPException(status_code=502, detail={
            "error": "vision_failed", "detail": str(e), "retryable": False,
        })

    tr["timings"]["vision_ms"] = _ms(t_vision)
    tr["model_raw"] = vision.pop("_raw_text", None)
    # D-193: this scan's own token counts (never a shared global), stored in scans.timings:
    # under "gemini" for a Gemini read, as always, and under "claude" for a Claude read
    # (D-192), so each key holds only its own reader's tokens.
    usage = vision.pop("_usage", None)
    read = vision.pop("_read", None)
    _record_read(tr, read)
    if usage:
        tr["timings"]["claude" if (read or {}).get("reader") == "claude" else "gemini"] = usage
    joined = vision.pop("_front_joined", None)
    if split:
        tr["timings"]["front_joined"] = bool(joined)
        if joined:
            tr["model_raw_front"] = front_read.raw
            if front_read.usage:
                tr["timings"]["gemini_front"] = dict(front_read.usage)
        elif front_read is not None and front_read.error:
            tr["timings"]["front_error"] = front_read.error
        elif front_read is not None and replay is None and STORE:
            # Still reading: kept on this scan's row when it comes, for the reviewer and replay.
            background.add_task(_save_late_front, front_read, tr["request_id"])
    # D-103: a front photo that isn't a food pack is set aside before anything
    # uses it (claims, pairing, identity); the back still decides the scan.
    front_caveat = rel.drop_unusable_front(vision)
    if front_caveat:
        corrections.append("front photo is not a food pack: " + front_caveat["detail"])
    t_ocr = time.monotonic()
    if back_read is not None:
        tr["timings"]["ocr_parallel"] = True
        if replay is not None:
            # A replay (repro, tests) waits for the read, so it repeats the original.
            await run_in_threadpool(back_read.done.wait)
        # A live scan never waits for it (Sushil, 2026-10-01): what is read by now counts.

    # Independent OCR cross-check on the back of pack. This is the only check
    # in the pipeline that is not the model grading itself, and it is the only
    # one that has ever caught a silent omission.
    ocr_result = {"available": False, "reason": "no back image"}
    # D-168: a table photo has no ingredient list, and the table still needs its second reading.
    if back_bytes and (vision.get("ingredients") or table_only):
        ocr_result = ocr_check.result_of(back_read, vision["ingredients"])
        fixed, recovered = ocr_check.recover_from(ocr_result, vision["ingredients"])
        if recovered:
            corrections.append(
                "independent OCR found additive(s) the model omitted: "
                + ", ".join(f"INS {i}" for i in ocr_result["missing"])
                + " - recovered as: " + "; ".join(recovered)
            )
            vision["ingredients"] = fixed

    # Corroborate the identity anchors product_match rests on against an
    # independent reader. A brand the model reports on a face where OCR read
    # the text well and found no such string was invented, and must not be
    # allowed to unlock the claim check.
    front_bytes = next((d for d, _m, r in images if r == "front"), None)
    if ocr_result.get("available"):
        back_text = ocr_result.get("ocr_text")
    else:
        # No ingredient list, or no cross-check by the deadline: whatever text was read, or none.
        back_text = ocr_check.result_of(back_read, []).get("ocr_text") if back_read else None
    _dg, _idrep = ocr_check.check_identity_anchors(vision, front_bytes, back_bytes, back_text=back_text)
    vision["_identity_corroboration"] = _idrep
    if _dg and (vision.get("product_match") or {}).get("status") == "match":
        bad = [f"{f}:{v['brand']!r}" for f, v in _idrep.items()
               if v["status"] == ocr_check.NOT_FOUND]
        corrections.append(
            "product_match downgraded to indeterminate - independent OCR read "
            "the face but found no such brand: " + ", ".join(bad)
        )
        vision["product_match"]["status"] = "indeterminate"
        vision["product_match"]["uncorroborated"] = bad
        # The anchors were computed from identity fields this check just
        # showed to be fabricated. Leaving them under verified_anchors would
        # display evidence supporting a match on a run downgraded precisely
        # because that evidence is not on the pack.
        vision["product_match"]["invalidated_anchors"] = \
            vision["product_match"].pop("verified_anchors", [])
        vision["verified_anchors"] = []
    vision["_ocr_cross_check"] = ocr_result

    tr["timings"]["ocr_ms"] = _ms(t_ocr)
    # D-092/D-093: what the independent reader saw, so a replay reads the same
    # text instead of calling Google again (migration 007), and for Tesseract how
    # many passes counted, so a replay votes on the same ones. Only the back is read.
    if back_bytes:
        text = cloud_vision.cached(back_bytes)
        reader = "cloud_vision" if text is not None else ocr_result.get("reader")
        if reader:
            tr["ocr"] = {"back": {"reader": reader, "text": text}}
            if reader == "tesseract":
                tr["ocr"]["back"]["passes"] = ocr_result.get("passes")
            elif reader == "skipped":
                tr["ocr"]["back"]["passes"] = 0
                tr["timings"]["ocr"] = "skipped (deadline)"
        if back_read is not None and back_read.ms is not None:
            tr["timings"]["ocr_read_ms"] = back_read.ms
    if recheck_check is not None:
        # D-175: the free comparison's input and decision stay with the scan (D-092).
        tr.setdefault("ocr", {}).setdefault("back", {})["recheck"] = recheck_check
    # D-133: the nutrition table, kept only where the second reading of the same
    # photo and the table's own arithmetic agree (lenses/nutrition.py).
    panel = nutrition.check(vision.get("nutrition"), ocr_result.get("ocr_text"),
                            (vision.get("product") or {}).get("net_quantity"), reader=ocr_result.get("reader"))
    alarm = cloud_vision.take_alarm()
    if alarm:
        _setup_alarm(f"ocr_config:{alarm}", cloud_vision.alarm_text(alarm))
    if table_only:
        return await _table_answer(table_hit, panel, barcode, barcode_source, images, keys, ocr_result,
                                   vision, device_id, t0, tr)
    vision["_pairing_attested_by_user"] = pairing_confirmed
    proceed, reliability = rel.assess(vision)
    reliability["client_corrections"] = corrections
    if front_caveat:
        reliability.setdefault("caveats", []).append(front_caveat)
    reliability["ocr_cross_check"] = {
        k: v for k, v in ocr_result.items() if k != "ocr_text"
    }
    if ocr_result.get("missing"):
        # A refusal from rel.assess() carries no caveats list; OCR can still find
        # an additive on a photo the model refused (was a KeyError → HTTP 500).
        reliability.setdefault("caveats", []).append({
            "code": "model_omitted_additive",
            "detail": (
                "A second, independent OCR pass found "
                + ", ".join(f"INS {i}" for i in ocr_result["missing"])
                + " on the label that the vision model did not return. "
                "Recovered and included in the verdict."
            ),
        })

    if (not proceed and reliability.get("error") == "no_ingredient_list_found"
            and not reliability.get("from_screen")
            and vision.get("front_status") == "read" and vision.get("back_status") == "read"):
        # D-190 (item #85): an Ayurvedic pack prints a formula, not an "Ingredients:" list. A
        # complete read whose printed words say it isn't food gets the not-food result, not
        # "couldn't find the ingredient list" (which offers "Send it to us" for a pack that
        # can never be published as food).
        kind = pack_kind.decide(vision)
        if kind["code"] == "not_food":
            return _not_food_answer(kind, vision, reliability, barcode, images, keys, device_id, t0, tr,
                                    avoid_codes=avoid_codes, who=who, people=people)
    if not proceed:
        scan_id = _persist(STORE and STORE.record_failed_scan, "refused",
                           error_code=reliability.get("error"), device_id=device_id,
                           latency_ms=_ms(t0), front_key=keys.get("front"), back_key=keys.get("back"),
                           trace=tr)
        # D-191: no list, but the photo showed the nutrition table (Gemini read it), and it was
        # the only back photo: say so, and keep the photo as the table when it was read cleanly.
        table_seen = None
        if (reliability.get("error") == "no_ingredient_list_found" and len(parts) <= 1
                and (vision.get("nutrition") or {}).get("status") in ("read", "partial")):
            table_seen = {"keep": (panel or {}).get("status") == "read"}
        return JSONResponse(status_code=422, content={
            # A refused scan still answers the allergy question: "couldn't
            # confirm", never silence (D-037, D-072).
            "allergens": allergen_block(avoid_codes, [], None, reliable=False, who=who),
            "diet": diet_block(avoid_codes, [], reliable=False),
            "screen": result_screen.build(
                verdict=None, display=None, claim_check=None, extracted=None,
                reliability=reliability, profiles=people, allergen_confidence=0.0,
                allergen_reliable=False, has_barcode=barcode is not None,
                photos_sent=[r for _d, _m, r in images], table_only=table_seen, repeat=bool(repeat_of)),
            "scan_id": _str(scan_id),
            "request_id": tr["request_id"],
            "verdict": None,
            # A refusal because a photo isn't a pack, or the photos are two packs,
            # doesn't name a product: the name would come from the other photo.
            "product": (None if reliability.get("error") in (*result_screen.NOT_A_PACK, "product_mismatch")
                        else vision.get("product")),
            "reliability": reliability,
            "engine_version": ENGINE_VERSION,
        })

    # The engine takes label-shaped text, and its tokenizer already handles
    # commas and brackets. Rejoining is deliberate: it keeps a single parsing
    # path for /analyze and /scan, so the two endpoints can never disagree.
    raw = ", ".join(vision["ingredients"])
    try:
        guard_ingredients(raw)
    except HTTPException as e:
        # A read that yields nothing parseable is a refusal too; record it so it
        # can be replayed (D-092), then refuse as before.
        _persist(STORE and STORE.record_failed_scan, "refused",
                 error_code=e.detail.get("error"), device_id=device_id, latency_ms=_ms(t0),
                 front_key=keys.get("front"), back_key=keys.get("back"), trace=tr)
        raise
    verdict = engine.analyze(raw)
    # D-139, D-140: what kind of pack the printed words and licences say this is.
    # Food answers (and every answer recorded before prompt rule 11) come out as before.
    kind = pack_kind.decide(vision)
    if kind["code"] == "infant":
        # D-140 phase 3, in shadow: an infant food's own checks, stored with the reading
        # (raw_extraction) for reviewers; nothing of it is sent to the user.
        vision["_infant"] = infant_lens.check(vision, vision["ingredients"], ocr_result.get("ocr_text"))

    # D-118: a pack this scan would add to the catalogue, whose ingredient list
    # Cloud Vision can't confirm, gets one request for a clearer photo, before
    # the result, while it is still in hand. "Use this one anyway" goes on.
    # Only when Cloud Vision read the photo: no independent read, nothing to fail.
    ocr_text = ((tr.get("ocr") or {}).get("back") or {})
    # The OCR text of the back, from either reader (D-093): the second reading the
    # barcode rules below use, at no extra call.
    back_text = ocr_result.get("ocr_text")
    photos = [(r, d) for d, _m, r in images]
    if barcode is None and images:
        # D-144: sent without a barcode, but a scan photo shows one. It counts when
        # two reads agree or its digits are printed in the back's OCR text; the app
        # took it from /check-photo before, which has no OCR text (so only two reads).
        t_bc = time.monotonic()
        found = await run_in_threadpool(barcode_rules.photo_code, photos, back_text)
        tr["barcode_check"] = {**found, "source": "scan_photo"}
        tr["timings"]["barcode_check_ms"] = _ms(t_bc)
        if found["code"]:
            barcode, barcode_source = found["code"], "scan_photo"
    elif barcode and images:
        # D-143: the barcode sent against the scan's own photos and the OCR text. A code
        # nothing else shows goes to a reviewer to check before it is published; the
        # user's result doesn't change. Kept on the scan row (migration 021).
        t_bc = time.monotonic()
        tr["barcode_check"] = {**await run_in_threadpool(barcode_rules.confirm, barcode, photos, back_text),
                               "source": barcode_source}
        tr["timings"]["barcode_check_ms"] = _ms(t_bc)
    from_screen = bool(reliability.get("from_screen"))
    ask_again = False
    if (barcode and STORE and not accept_unconfirmed and not from_screen
            and ocr_text.get("reader") == "cloud_vision"
            and (ocr_text.get("text") or "").strip()):
        matters, check = cross_check(vision["ingredients"], vision.get("allergen_statement"), ocr_text["text"])
        if check is not None:
            if matters and device_id:
                # D-191: one clearer-photo request per pack per phone in 24 hours. A second photo
                # that still can't be confirmed goes to the result, as "Use this one anyway" does.
                earlier = _persist(STORE.recent_ask, device_id, barcode)
                if earlier:
                    check["already_asked"] = str(earlier)
                    matters = False
            ask_again = matters and bool(_persist(STORE.adds_version, barcode, vision["ingredients"]))
            # Kept with the back's Cloud Vision read (scans.ocr), so repro.py shows it (D-092).
            ocr_text["independent_read"] = {**check, "asked": ask_again}
    if ask_again:
        reliability["error"] = "independent_read_failed"
        scan_id = _persist(STORE.record_failed_scan, "refused", error_code="independent_read_failed",
                           device_id=device_id, latency_ms=_ms(t0), front_key=keys.get("front"),
                           back_key=keys.get("back"), trace=tr)
        screen = result_screen.build(
            verdict=None, display=None, claim_check=None, extracted=None, reliability=reliability,
            profiles=people, allergen_confidence=0.0, allergen_reliable=False,
            has_barcode=True, photos_sent=[r for _d, _m, r in images], repeat=bool(repeat_of),
            parts_sent=max(1, len(parts)))
        screen["can_use_anyway"] = True
        return JSONResponse(status_code=422, content={
            "allergens": allergen_block(avoid_codes, [], None, reliable=False, who=who),
            "diet": diet_block(avoid_codes, [], reliable=False),
            "screen": screen, "scan_id": _str(scan_id), "request_id": tr["request_id"],
            "verdict": None, "product": vision.get("product"), "reliability": reliability,
            "engine_version": ENGINE_VERSION,
        })

    # D-072: allergen output needs a reliable scan AND a complete list AND
    # ingredient confidence >= 0.95. The general gate's reasoning about
    # self-reported confidence applies here too; this is an extra bar, not
    # the only one.
    allergen_confidence = (vision.get("confidence") or {}).get("ingredients", 0.0)
    allergen_reliable = (reliability.get("verdict_safe_to_display", False)
                         and reliability.get("ingredients_complete", False))
    allergens = allergen_block(
        avoid_codes,
        vision["ingredients"],
        vision.get("allergen_statement"),
        confidence=allergen_confidence,
        reliable=allergen_reliable,
        who=who,
    )

    if from_screen and allergens:
        allergens["source"] = "screen"   # D-130: the app's lines say so; this is for API readers
    claims_trusted = reliability.get("claims_permitted", True) and vision["front_status"] == "read"
    claim_check = claim_checker.check_claims(
        vision.get("front_claims", []), raw, verdict,
        # An unverified pairing suppresses the claim check the same way an
        # unread front does: in both cases we cannot say these claims
        # belong to this ingredient list.
        vision["front_status"] if reliability.get("claims_permitted", True)
        else "pairing_unverified",
    )

    pack = None
    if from_screen:
        # D-130: a screen is a lead, never the record (D-089): only the scan row,
        # whatever barcode came with it. When our catalogue has the pack (read
        # from a real one), its allergens are set beside the screen's.
        unlisted_id = _persist(STORE and STORE.record_screen_scan, device_id=device_id,
                               latency_ms=_ms(t0), front_key=keys.get("front"),
                               back_key=keys.get("back"), trace=tr)
        saved = None
        hit = _persist(STORE.find_current, barcode) if (STORE and barcode) else None
        if hit:
            pack = {"ingredients": hit["ingredients"], "allergen_statement": hit["allergen_statement"],
                    "verified_on": hit["verified_at"].date().isoformat()}
    elif barcode is None:
        # D-107: no barcode, no catalogue entry. The user gets the result; only
        # the scan row is kept, so it can be replayed (D-092).
        unlisted_id = _persist(STORE and STORE.record_unlisted_scan, device_id=device_id,
                               latency_ms=_ms(t0), front_key=keys.get("front"),
                               back_key=keys.get("back"), trace=tr)
        saved = None
    else:
        unlisted_id = None
        saved = _persist(
            STORE and STORE.save_scan, vision=vision, verdict=verdict, claim_check=claim_check,
            claims_trusted=claims_trusted, reliability=reliability, barcode=barcode,
            device_id=device_id, latency_ms=_ms(t0), model_name=vision.get("_model") or MODEL,
            prompt_version=PROMPT_VERSION, engine_version=ENGINE_VERSION,
            front_key=keys.get("front"), back_key=keys.get("back"), trace=tr, nutrition=panel,
            pack_kind=kind)

    display = rel.apply_display_rule(verdict, reliability)
    user_claims = _user_claim_check(claim_check, vision.get("front_claims", []))
    extracted = {
        "ingredients": vision["ingredients"],
        "ingredients_status": vision["ingredients_status"],
        "front_claims": vision.get("front_claims", []),
        "front_claim_footnotes": vision.get("front_claim_footnotes", []),
        "allergen_statement": vision.get("allergen_statement"),
        "raw_text_sent_to_engine": raw,
    }
    if vision.get("pack_statements"):
        extracted["pack_statements"] = vision["pack_statements"]      # D-140: /compare re-decides the kind
    return _withhold(kind, {
        "allergens": allergens,           # D-060: always the first thing a client reads
        "diet": diet_block(avoid_codes, vision["ingredients"], veg_mark=(vision.get("product") or {}).get("veg_mark"),
                           confidence=allergen_confidence, reliable=allergen_reliable and not from_screen,
                           complete=reliability.get("ingredients_complete", True),
                           product_name=(vision.get("product") or {}).get("name")),
        # What the app renders, in order (D-060-D-066). Built from the fields below.
        "screen": result_screen.build(
            verdict=verdict, display=display, claim_check=user_claims, extracted=extracted,
            reliability=reliability, profiles=people, allergen_confidence=allergen_confidence,
            allergen_reliable=allergen_reliable, has_barcode=barcode is not None, pack=pack,
            screen_pack=None if from_screen else screen_pack, nutrition=panel,
            parts_sent=max(1, len(parts)), kind=kind,
            nutra_input={"vision": vision, "ocr_text": ocr_result.get("ocr_text"), "photos": n_photos},
            barcode_answer=barcode_answer, veg_mark=(vision.get("product") or {}).get("veg_mark"),
            product_name=(vision.get("product") or {}).get("name"),
            # D-167: a food pack with a barcode and no checked version yet, before its review.
            unchecked=bool(saved and saved["version_status"] == "pending_review"
                           and not saved.get("checked") and kind["code"] == "food")),
        "pack_kind": {k: kind[k] for k in ("code", "evidence", "review")},
        **_compare_input(kind, vision=vision, ocr_text=ocr_result.get("ocr_text"), photos=n_photos),
        "scan_id": saved["scan_id"] if saved else _str(unlisted_id),
        "catalogue": ({"source": "scan", "product_version_id": saved["product_version_id"],
                       "status": saved["version_status"], "queued_for_review": saved["queued"]}
                      if saved else
                      {"source": "screen", "status": "not_saved", "reason": "from_screen",
                       "pack_verified_on": pack and pack["verified_on"]} if from_screen
                      else {"source": "scan", "status": "not_saved", "reason": "no_barcode"} if barcode is None
                      else None),
        "product": vision.get("product"),
        "nutrition": nutrition.public(panel),
        "verdict": verdict,
        "display": display,
        "claim_check": user_claims,
        "extracted": extracted,
        "reliability": reliability,
        "disclosures": rel.disclosures(reliability),
        "regulators": regulators.compare(verdict) if compare_regulators else None,
        "engine_version": ENGINE_VERSION,
    })
