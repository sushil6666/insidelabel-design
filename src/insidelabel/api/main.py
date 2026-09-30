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
    GET  /access       invite-only? joined?   POST /join   a tester's code (D-102)
    POST /feedback     a tester's comment + optional rating (D-102)

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

import asyncio  # noqa: E402
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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from insidelabel import barcode as barcode_rules  # noqa: E402
from insidelabel import photo_check  # noqa: E402
from insidelabel import photo_join  # noqa: E402
from insidelabel import ratelimit  # noqa: E402
from insidelabel import trace  # noqa: E402
from insidelabel.core import engine, pack_kind  # noqa: E402
from insidelabel.claims import checker as claim_checker  # noqa: E402
from insidelabel.lenses import allergens as allergen_checker  # noqa: E402
from insidelabel.lenses import compare as shelf  # noqa: E402
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
    JoinRequest,
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


# D-102: the web beta is invite-only: ~50 named testers, one code each. On a
# server with INSIDELABEL_INVITE_ONLY=on a phone must join with a code before
# it can scan, send photos or give feedback. Tests set INVITE_ONLY directly.
INVITE_ONLY = None             # None: follow the environment, read per request


def _invite_only():
    if INVITE_ONLY is not None:
        return INVITE_ONLY
    return os.environ.get("INSIDELABEL_INVITE_ONLY", "off").lower() == "on"


# D-105: "Before you start", the rules every tester agrees to before a first
# scan. The text is data (wording-linted); a new version asks everyone again.
with open(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "terms.json"), encoding="utf-8") as _f:
    TERMS = {k: v for k, v in json.load(_f).items() if not k.startswith("_")}


def _require_invite(device_id):
    """
    Refuse a phone that hasn't joined (D-102) or hasn't agreed to the current
    "Before you start" (D-105), before anything is read or stored (like a 429,
    D-095; logged, not a scan row). Without a database nobody can be checked,
    so nobody gets in.
    """
    if not _invite_only():
        return
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable", "detail": "Invites need the database (INSIDELABEL_DB is not set)."})
    code = _persist(STORE.invite_of, device_id) if device_id else None
    if code is None:
        log.warning("no invite: device=%s", device_id)
        raise HTTPException(status_code=403, detail={
            "error": "invite_required",
            "detail": "This beta is by invitation. Open the link from your invite, or type its code."})
    if not _persist(STORE.has_agreed, device_id, TERMS["version"]):
        log.warning("terms not agreed: device=%s version=%s", device_id, TERMS["version"])
        raise HTTPException(status_code=403, detail={
            "error": "terms_required", "terms_version": TERMS["version"],
            "detail": "Please read and agree to the rules for the beta first."})


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
    raise HTTPException(status_code=429, headers={"Retry-After": str(seconds)}, detail={
        "error": "rate_limited",
        "detail": text.format(minutes=minutes, s="" if minutes == 1 else "s"),
        "retryable": True, "retry_after_s": seconds,
    })


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
if os.path.isdir(WEB_DIR):
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="app")

    # D-102: the public pages around the app - landing, privacy, about. Plain
    # HTML in web/site/, linted with the app's wording rules (tests/test_web.py).
    SITE_DIR = os.path.join(WEB_DIR, "site")
    _SITE_PAGES = {"/": "index.html", "/privacy": "privacy.html", "/about": "about.html",
                   "/how": "how.html", "/site.css": "site.css"}      # D-127: what result words mean

    def _site_page(path):
        name = _SITE_PAGES[path]
        full = os.path.join(SITE_DIR, name)
        if not os.path.exists(full):
            return RedirectResponse("/app/")
        return FileResponse(full)

    for _path in _SITE_PAGES:
        app.add_api_route(_path, (lambda p: (lambda: _site_page(p)))(_path), methods=["GET"],
                          include_in_schema=False)


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
                "hint": "An empty list scores 100/100 CLEAN. Refused rather than returned.",
            },
        )
    if not engine.tokenize(raw):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_ingredient_tokens",
                "detail": "No ingredient tokens could be parsed from the input.",
                "hint": "An unparseable list scores 100/100 CLEAN. Refused rather than returned.",
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
    unknown = [c for c in codes if c not in allergen_checker.ALLERGENS]
    if unknown:
        raise HTTPException(status_code=422, detail={
            "error": "unknown_allergen",
            "detail": f"Unknown allergen code(s): {', '.join(unknown)}.",
            "hint": "Valid codes: " + ", ".join(allergen_checker.ALLERGENS) + ".",
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


def allergen_block(codes, ingredients, statement, confidence=1.0, reliable=True, who=None):
    """
    The first thing a client renders when the profile has an avoid list (D-060).
    Results are sorted strongest state first, so results[0] is the headline.
    """
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
                "text": r.parent_text(who) if who else r.parent_text(),
            }
            for r in rows
        ],
    }


@app.get("/allergens")
def list_allergens():
    """Codes a client may put on an avoid list, with display labels."""
    return {
        "allergens": [
            {"code": a["code"], "label": a["label"],
             "fssai_mandatory": a.get("fssai_mandatory", True)}
            for a in allergen_checker.ALLERGENS.values()
        ]
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
    # D-140: the server itself never compares or ranks an infant food (nor, until
    # phase 2, a supplement), whatever the client sends. Refused if any of: the kind
    # the client reports, the kind the pack's printed statements give, or the kind
    # stored for that scan says it can't be compared.
    for p in req.packs:
        kinds = {p.kind or "food", pack_kind.decide({"pack_statements": [
            s for s in p.pack_statements if isinstance(s, dict) and isinstance(s.get("text"), str)]})["code"]}
        stored = _persist(STORE.kind_of_scan, p.id) if STORE else None
        if stored:
            kinds.add(stored)
        blocked = sorted(kinds - pack_kind.COMPARABLE)
        if blocked:
            raise HTTPException(status_code=422, detail={
                "error": "not_comparable", "reason": "infant_food" if "infant" in blocked else blocked[0],
                "pack": p.id,
                "detail": ("We don't compare or rank foods for infants." if "infant" in blocked
                           else "We compare ordinary foods only for now."),
            })
    codes = parse_avoid(req.avoid)
    packs = [shelf.Product(p.id, p.name, p.ingredients, reliable=p.reliable,
                           allergen_statement=p.allergen_statement, confidence=p.confidence)
             for p in req.packs]
    if len({p.id for p in packs}) != len(packs):
        raise HTTPException(status_code=422, detail={
            "error": "duplicate_pack", "detail": "Each pack needs a distinct id.",
        })
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


def _withhold(kind, result):
    """
    D-140: a kind in shadow (infant foods) gets no result from the server, whatever the
    client: no score, grade or band (verdict, display), no claim, nutrition or EU/US
    result. The allergen lines, the kind and the ingredient list stay (the screen block).
    The scan is still stored whole for reviewers (save_scan ran before this).
    """
    fields = pack_kind.WITHHOLD.get(kind["code"], ())
    if fields:
        for f in fields:
            result[f] = None
        result["withheld"] = {"fields": list(fields), "reason": pack_kind.WITHHOLD_REASON[kind["code"]]}
    # D-139: a supplement has no score, grade, band or NOVA count; its flags stay for reviewers.
    for field, keys in pack_kind.WITHHOLD_KEYS.get(kind["code"], {}).items():
        if isinstance(result.get(field), dict):
            result[field] = {k: (None if k in keys else v) for k, v in result[field].items()}
            result.setdefault("withheld", {"fields": [], "reason": pack_kind.WITHHOLD_REASON[kind["code"]]})
            result["withheld"]["fields"].append(field + "." + ",".join(keys))
    return result


def _catalogue_kind(hit):
    """D-139: the kind stored on the version, or, for one stored before it, the category's (else food)."""
    if hit.get("pack_kind"):
        stored = hit.get("pack_kind_evidence") or {}
        return {"code": hit["pack_kind"], "evidence": stored.get("evidence") or [], "review": [],
                "licences": {}, "category": hit.get("category_code")}
    return pack_kind.decide({}, category=hit.get("category_code"))


def _catalogue_result(hit, avoid_codes, who, compare_regulators, profiles=(), screen_pack=None):
    """
    A result built from a reviewed catalogue version. The engine re-runs on the
    stored ingredient list, so the verdict always reflects the current rules and
    tables, not the ones in force when the pack was first reviewed.
    """
    ingredients = hit["ingredients"]
    raw = ", ".join(ingredients)
    verdict = engine.analyze(raw)
    kind = _catalogue_kind(hit)
    front_claims = hit["front_claims"] or []
    verified = hit["verified_at"].date().isoformat()
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
        "front_wanted": bool(hit.get("front_wanted")),
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
        "allergens": allergen_block(avoid_codes, ingredients, hit["allergen_statement"], who=who),
        "screen": result_screen.build(
            verdict=verdict, display=display, claim_check=claim_check, extracted=extracted,
            reliability=reliability, profiles=profiles, allergen_confidence=1.0,
            allergen_reliable=True, catalogue=catalogue, screen_pack=screen_pack,
            nutrition=hit.get("nutrition"), kind=kind,
            # D-139: no reading from the catalogue; the published name still says tablet or powder.
            nutra_input={"product": {"name": hit["name"], "variant": hit["variant"]}}),
        "pack_kind": {k: kind[k] for k in ("code", "evidence", "review")},
        "catalogue": catalogue,
        "product": {"brand": hit["brand"], "name": hit["name"], "variant": hit["variant"]},
        "nutrition": nutrition.public(hit.get("nutrition")),
        "verdict": verdict,
        "display": display,
        "claim_check": claim_check,
        "extracted": extracted,
        "reliability": reliability,
        "disclosures": [
            f"Our team last checked this label on {verified}. Packs change; if yours "
            "looks different, scan the back of the pack.",
        ] + rel.disclosures(reliability),
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


@app.post("/send-to-us")
def send_to_us(req: SendToUsRequest, request: Request):
    """
    After two refused scans (D-070): "Send it to us - we'll check this pack and
    tell you when it's ready." Queues the photos for a reviewer; /updates
    reports back when the item is decided.
    """
    _rate_limit(request, "send_to_us", req.device_id, ratelimit.SEND_TEXT)
    _require_invite(req.device_id)
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
    "back_ok": "Clear photo. We'll read the ingredient list when you tap Check this pack.",
    "front_ok": "Clear photo of the front.",
    "barcode_too": " Barcode {code} found on it too.",
}


@app.post("/check-photo")
async def check_photo(
    request: Request,
    role: str = Form(..., description='"barcode", "back" or "front".'),
    photo: Optional[UploadFile] = File(None),
    device_id: Optional[str] = Form(None, examples=[""]),
):
    """
    D-104: the tick or cross the app shows on each photo as soon as it is picked.
    A barcode photo must show one retail barcode, read by zxing-cpp (never
    typed, never read by the model); a label photo must be a readable picture.
    No model call and nothing stored: this costs nothing but CPU.
    """
    _rate_limit(request, "check_photo", device_id, ratelimit.SCAN_TEXT)
    _require_invite(device_id)
    if role not in ("barcode", "back", "front"):
        raise HTTPException(status_code=422, detail={"error": "bad_role", "detail": 'role is "barcode", "back" or "front".'})
    img = await _read_image(photo, role)
    if img is None:
        raise HTTPException(status_code=422, detail={"error": "no_photo", "detail": "Send a photo."})
    data, mime, _role = img
    bad = photo_check.check(data, mime, role, min_size=role != "barcode")
    if bad:
        return {"role": role, "ok": False, "problem": bad[0], "message": bad[1], "barcode": None}
    good, reasons = await run_in_threadpool(barcode_rules.read_from_photo, data)
    code = good[0] if len(good) == 1 else None
    if role == "barcode":
        if len(good) > 1:
            return {"role": role, "ok": False, "problem": "several_barcodes",
                    "message": CHECK_MESSAGES["several_barcodes"], "barcode": None}
        if code:
            return {"role": role, "ok": True, "problem": None,
                    "message": CHECK_MESSAGES["barcode_ok"].format(code=code), "barcode": code}
        if reasons:                               # a barcode, but not a retail pack's (a book, a carton…)
            return {"role": role, "ok": False, "problem": reasons[0],
                    "message": barcode_rules.MESSAGES[reasons[0]], "barcode": None}
        return {"role": role, "ok": False, "problem": "no_barcode",
                "message": CHECK_MESSAGES["no_barcode"], "barcode": None}
    msg = CHECK_MESSAGES[f"{role}_ok"] + (CHECK_MESSAGES["barcode_too"].format(code=code) if code else "")
    return {"role": role, "ok": True, "problem": None, "message": msg, "barcode": code}


# ---------------------------------------------------------------------------
# Invite-only beta (D-102): join, access, feedback
# ---------------------------------------------------------------------------
_JOIN_ERRORS = {
    "bad_code": (404, "That code doesn't match an invite. Check it against your message."),
    "revoked": (410, "That invite has been closed. Ask the person who sent it."),
    "code_full": (409, "That code is already in use on three devices. Ask for it to be reset."),
}


@app.get("/access")
def access(device_id: str = ""):
    """Invite needed? Joined? Agreed to the current rules (D-105)? The app asks on open."""
    joined = bool(STORE and device_id and _persist(STORE.invite_of, device_id))
    agreed = bool(STORE and device_id and _persist(STORE.has_agreed, device_id, TERMS["version"]))
    return {"invite_only": _invite_only(), "joined": joined, "agreed": agreed,
            "terms_version": TERMS["version"]}


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


@app.post("/join")
def join(req: JoinRequest, request: Request):
    """A tester's code, from their link or typed. One code serves up to three devices."""
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable", "detail": "Invites need the database (INSIDELABEL_DB is not set)."})
    try:
        device = str(uuid.UUID(req.device_id))
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "bad_device_id"})
    ip = ratelimit.client_ip(request)
    wait = ratelimit.LIMITER.wait("join_fail", device=device, ip=ip)
    if wait:
        raise HTTPException(status_code=429, headers={"Retry-After": str(int(wait) + 1)}, detail={
            "error": "rate_limited", "detail": ratelimit.JOIN_TEXT, "retryable": True,
            "retry_after_s": int(wait) + 1})
    out = STORE.join_invite(req.code, device)
    if "error" in out:
        ratelimit.LIMITER.hit("join_fail", device=device, ip=ip)       # only failures count
        status, text = _JOIN_ERRORS[out["error"]]
        raise HTTPException(status_code=status, detail={"error": out["error"], "detail": text})
    return {"status": "joined"}


@app.post("/feedback")
def feedback(req: FeedbackRequest, request: Request):
    """D-102 "Send feedback": a tester's comment and optional 1-5 rating, stored against their code."""
    _rate_limit(request, "feedback", req.device_id, ratelimit.FEEDBACK_TEXT)
    _require_invite(req.device_id)
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
    D-129 "Delete my data" (DPDP Act s.12(3)). No invite or agreement needed: a
    tester whose code was revoked can still erase. The database goes first; a
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
                                      description='D-106: "camera" (taken in the app) or "upload" (gallery, computer).'),
    front_source: Optional[str] = Form(None, examples=[""], description='D-106: as back_source.'),
    back2_source: Optional[str] = Form(None, examples=[""], description='D-106: as back_source, for back2.'),
    back3_source: Optional[str] = Form(None, examples=[""], description='D-106: as back_source, for back3.'),
    barcode_source: Optional[str] = Form(None, examples=[""],
                                         description='D-104: "camera" (live scanner) or "photo" (read by /check-photo).'),
    device_id: Optional[str] = Form(None, examples=[""], description="Anonymous install id (UUID). No personal data."),
    profiles: Optional[str] = Form(None, examples=[""],
                                   description='JSON [{"ref","age","avoid"}], up to 3. No names (D-074).'),
    accept_unconfirmed: bool = Form(False, description="D-118: 'use this one anyway' after a clearer-photo request."),
    screen_pack: Optional[str] = Form(None, examples=[""],
                                      description='D-130: JSON {"ingredients", "allergen_statement"} from an earlier '
                                                  'result read from a screen; the answer says what differs on this pack.'),
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
    _require_invite(device_id)            # D-102, before any photo is read
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
        if said not in ("camera", "upload"):
            raise HTTPException(status_code=422, detail={
                "error": "bad_photo_source", "detail": f'{role}_source is "camera" or "upload".'})
        if any(r == role for _d, _m, r in images):
            photo_sources[role] = said
    # D-103: a file that can't be a readable label never costs a model read.
    # Replayed answers skip it: they were read from photos checked at the time.
    if replay is None:
        for data, mime, role in images:
            bad = photo_check.check(data, mime, _PART_LABEL.get(role, role))
            if bad:
                log.warning("photo refused: %s %s", role, bad[0])
                raise HTTPException(status_code=415 if bad[0] == "not_an_image" else 422, detail={
                    "error": bad[0], "role": role, "detail": bad[1]})

    # D-119: a long list in parts becomes one back photo here; from now on
    # the scan is ordinary (one image for Gemini, Cloud Vision, storage, replay).
    parts = [(d, m) for d, m, r in images if r in ("back", "back2", "back3")]
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
        "request": {"barcode": barcode, "barcode_source": barcode_source, "photo_sources": photo_sources,
                    "avoid": avoid_codes if avoid is not None else None,
                    "profiles": people, "pairing_confirmed": pairing_confirmed,
                    "compare_regulators": compare_regulators,
                    "images": [r for _d, _m, r in images], "back_parts": max(1, len(parts)),
                    "replay": replay is not None,
                    "accept_unconfirmed": accept_unconfirmed, "screen_pack": screen_pack},
        "timings": {},
    }

    # D-024: a barcode alone is a catalogue lookup - no vision call, ~₹0.
    # Photos, when sent, are always read: that is how a reformulation under an
    # unchanged barcode gets noticed, and how the D-073 allergy re-check works.
    if barcode and not images and replay is None:
        hit = _persist(STORE.find_current, barcode) if STORE else None
        if hit is None:
            raise HTTPException(status_code=404, detail={
                "error": "not_in_catalogue",
                "detail": "We haven't checked this pack yet.",
                "hint": "Photograph the back of the pack (the ingredient list).",
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

    # The model call and the OCR are blocking; on worker threads they don't freeze
    # every other request for 10-15 s. Cloud Vision doesn't need the model's
    # answer to read the photo, so it starts now, alongside Gemini; the cross-check
    # below then finds the text in its cache (D-093). If the model fails, that
    # read (~13 paise) was spent for nothing: rare, and cheaper than the wait.
    back_bytes = next((d for d, _m, r in images if r == "back"), None)
    ocr_prefetch = None
    if back_bytes and ocr_check.cloud_first():
        ocr_prefetch = asyncio.ensure_future(run_in_threadpool(cloud_vision.read_text, back_bytes))
    # D-092: how long we waited on retries, so a slow scan can be told apart as
    # "the model was busy" (retries) or "the model was slow" (none).
    retries = tr["timings"].setdefault("vision_retries", [])

    def on_retry(attempt, delay, err):
        retries.append({"attempt": attempt, "wait_s": round(delay, 1), "error": type(err).__name__})
        log.warning("model retry %s after %s, waiting %.1fs", attempt, type(err).__name__, delay)

    t_vision = time.monotonic()
    try:
        vision, corrections = await run_in_threadpool(gemini.analyze_images, images, raw_response=replay,
                                                      on_attempt=on_retry)
    except gemini.VisionConfigError as e:
        # Our setup (key, credit, billing), not the label and not a busy moment.
        # The user is told it's unavailable; the developer gets an alarm.
        tr["timings"]["vision_ms"] = _ms(t_vision)
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
        _persist(STORE and STORE.record_failed_scan, "vision_failed",
                 device_id=device_id, latency_ms=_ms(t0),
                 front_key=keys.get("front"), back_key=keys.get("back"), trace=tr)
        raise HTTPException(status_code=502, detail={
            "error": "vision_failed", "detail": str(e), "retryable": False,
        })

    tr["timings"]["vision_ms"] = _ms(t_vision)
    tr["model_raw"] = vision.pop("_raw_text", None)
    # D-103: a front photo that isn't a food pack is set aside before anything
    # uses it (claims, pairing, identity); the back still decides the scan.
    front_caveat = rel.drop_unusable_front(vision)
    if front_caveat:
        corrections.append("front photo is not a food pack: " + front_caveat["detail"])
    t_ocr = time.monotonic()
    if ocr_prefetch is not None:
        await ocr_prefetch                       # usually done already; never raises
        tr["timings"]["ocr_parallel"] = True

    # Independent OCR cross-check on the back of pack. This is the only check
    # in the pipeline that is not the model grading itself, and it is the only
    # one that has ever caught a silent omission.
    ocr_result = {"available": False, "reason": "no back image"}
    if back_bytes and vision.get("ingredients"):
        fixed, ocr_result, recovered = await run_in_threadpool(
            ocr_check.recover_entries, back_bytes, vision["ingredients"])
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
    _dg, _idrep = await run_in_threadpool(ocr_check.check_identity_anchors, vision, front_bytes, back_bytes)
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
    # text instead of calling Google again (migration 007). Only the back is read.
    if back_bytes:
        text = cloud_vision.cached(back_bytes)
        reader = "cloud_vision" if text is not None else ocr_result.get("reader")
        if reader:
            tr["ocr"] = {"back": {"reader": reader, "text": text}}
    # D-133: the nutrition table, kept only where the second reading of the same
    # photo and the table's own arithmetic agree (lenses/nutrition.py).
    panel = nutrition.check(vision.get("nutrition"), ocr_result.get("ocr_text"),
                            (vision.get("product") or {}).get("net_quantity"), reader=ocr_result.get("reader"))
    alarm = cloud_vision.take_alarm()
    if alarm:
        _setup_alarm(f"ocr_config:{alarm}", "Cloud Vision refused the call; scans fall back to Tesseract "
                     f"(~20 s slower) until fixed. Status: {alarm}. See the server log for Google's message.")
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

    if not proceed:
        scan_id = _persist(STORE and STORE.record_failed_scan, "refused",
                           error_code=reliability.get("error"), device_id=device_id,
                           latency_ms=_ms(t0), front_key=keys.get("front"), back_key=keys.get("back"),
                           trace=tr)
        return JSONResponse(status_code=422, content={
            # A refused scan still answers the allergy question: "couldn't
            # confirm", never silence (D-037, D-072).
            "allergens": allergen_block(avoid_codes, [], None, reliable=False, who=who),
            "screen": result_screen.build(
                verdict=None, display=None, claim_check=None, extracted=None,
                reliability=reliability, profiles=people, allergen_confidence=0.0,
                allergen_reliable=False, has_barcode=barcode is not None,
                photos_sent=[r for _d, _m, r in images]),
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

    # D-118: a pack this scan would add to the catalogue, whose ingredient list
    # Cloud Vision can't confirm, gets one request for a clearer photo, before
    # the result, while it is still in hand. "Use this one anyway" goes on.
    # Only when Cloud Vision read the photo: no independent read, nothing to fail.
    ocr_text = ((tr.get("ocr") or {}).get("back") or {})
    from_screen = bool(reliability.get("from_screen"))
    if (barcode and STORE and not accept_unconfirmed and not from_screen
            and ocr_text.get("reader") == "cloud_vision"
            and (ocr_text.get("text") or "").strip()
            and not review_checker.independent_read_confirmed(
                vision["ingredients"], ocr_text["text"], vision.get("allergen_statement"))
            and _persist(STORE.adds_version, barcode, vision["ingredients"])):
        reliability["error"] = "independent_read_failed"
        scan_id = _persist(STORE.record_failed_scan, "refused", error_code="independent_read_failed",
                           device_id=device_id, latency_ms=_ms(t0), front_key=keys.get("front"),
                           back_key=keys.get("back"), trace=tr)
        screen = result_screen.build(
            verdict=None, display=None, claim_check=None, extracted=None, reliability=reliability,
            profiles=people, allergen_confidence=0.0, allergen_reliable=False,
            has_barcode=True, photos_sent=[r for _d, _m, r in images])
        screen["can_use_anyway"] = True
        return JSONResponse(status_code=422, content={
            "allergens": allergen_block(avoid_codes, [], None, reliable=False, who=who),
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
        # What the app renders, in order (D-060-D-066). Built from the fields below.
        "screen": result_screen.build(
            verdict=verdict, display=display, claim_check=user_claims, extracted=extracted,
            reliability=reliability, profiles=people, allergen_confidence=allergen_confidence,
            allergen_reliable=allergen_reliable, has_barcode=barcode is not None, pack=pack,
            screen_pack=None if from_screen else screen_pack, nutrition=panel,
            parts_sent=max(1, len(parts)), kind=kind,
            nutra_input={"vision": vision, "ocr_text": ocr_result.get("ocr_text")}),
        "pack_kind": {k: kind[k] for k in ("code", "evidence", "review")},
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
