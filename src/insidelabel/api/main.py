"""
Inside Label — API (v0.1)

    POST /analyze      raw ingredient text  -> layered verdict (engine verbatim)
    POST /claim-check  text + front claims  -> verdict + claim contradictions
    POST /allergen-check  ingredients + avoid list -> five-state allergen result
    POST /compare      2-4 scanned packs    -> best pick of these, with reasons
    GET  /regulators/{ins}                  -> India vs EU vs US, information only
    GET  /health

    POST /scan         one or two images   -> verdict + identity + claim check
                       (+ barcode: a reviewed catalogue entry skips the vision call)
    POST /report       "Report a mistake" on a scan (D-076)

THE GUARD THAT MATTERS
----------------------
engine.analyze("") returns score 100, grade A, binary "clean". That is correct
behaviour for the engine — no flagged ingredients means no penalties — but it
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
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from insidelabel import ratelimit  # noqa: E402
from insidelabel import trace  # noqa: E402
from insidelabel.core import engine  # noqa: E402
from insidelabel.claims import checker as claim_checker  # noqa: E402
from insidelabel.lenses import allergens as allergen_checker  # noqa: E402
from insidelabel.lenses import compare as shelf  # noqa: E402
from insidelabel.lenses import regulators  # noqa: E402
from insidelabel.lenses import screen as result_screen  # noqa: E402
from insidelabel.reliability import gates as rel  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402
from insidelabel.extraction.providers import gemini  # noqa: E402
from insidelabel.extraction.providers import ocr_check  # noqa: E402
from insidelabel.extraction.providers.prompt import MODEL, VISION_PROMPT  # noqa: E402
from insidelabel.extraction.schemas import (  # noqa: E402
    AllergenCheckRequest,
    AnalyzeRequest,
    CompareRequest,
    ProblemRequest,
    ReportRequest,
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
    except Exception:  # noqa: BLE001 — any storage failure, logged with traceback
        log.exception("scan persistence failed")
        return None

app = FastAPI(
    title="Inside Label API",
    version="0.1.0",
    description=(
        "Ingredient-list analysis. The engine states ingredient facts only — "
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
    except Exception as exc:  # noqa: BLE001 — the last line of defence; logged and stored
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

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/")


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
# India vs EU vs US (D-086) — information only
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
_BARCODE = re.compile(r"^\d{8}$|^\d{12,14}$")      # EAN-8, UPC-A, EAN-13, GTIN-14


def _clean_barcode(barcode):
    if barcode is None or not barcode.strip():
        return None
    b = re.sub(r"[\s-]", "", barcode)
    if not _BARCODE.match(b):
        raise HTTPException(status_code=422, detail={
            "error": "bad_barcode",
            "detail": "barcode must be 8, 12, 13 or 14 digits (EAN/UPC).",
        })
    return b


def _ms(t0):
    return int((time.monotonic() - t0) * 1000)


def _str(v):
    return str(v) if v is not None else None


def _catalogue_result(hit, avoid_codes, who, compare_regulators, profiles=()):
    """
    A result built from a reviewed catalogue version. The engine re-runs on the
    stored ingredient list, so the verdict always reflects the current rules and
    tables, not the ones in force when the pack was first reviewed.
    """
    ingredients = hit["ingredients"]
    raw = ", ".join(ingredients)
    verdict = engine.analyze(raw)
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
    return {
        # Reviewed data: read in full by a person, so the allergen gate is met.
        "allergens": allergen_block(avoid_codes, ingredients, hit["allergen_statement"], who=who),
        "screen": result_screen.build(
            verdict=verdict, display=display, claim_check=claim_check, extracted=extracted,
            reliability=reliability, profiles=profiles, allergen_confidence=1.0,
            allergen_reliable=True, catalogue=catalogue),
        "catalogue": catalogue,
        "product": {"brand": hit["brand"], "name": hit["name"], "variant": hit["variant"]},
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
    }


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


@app.post("/report")
def report(req: ReportRequest):
    """D-076: "Report a mistake" on any result. Goes to the review queue."""
    if STORE is None:
        raise HTTPException(status_code=503, detail={
            "error": "storage_unavailable",
            "detail": "Reports need the database (INSIDELABEL_DB is not set).",
        })
    if not (req.scan_id or req.product_version_id):
        raise HTTPException(status_code=422, detail={
            "error": "no_subject", "detail": "Send the scan_id (or product_version_id) being reported.",
        })
    out = STORE.report(scan_id=req.scan_id, product_version_id=req.product_version_id,
                       device_id=req.device_id, field=req.field,
                       proposed_value=req.proposed_value, note=req.note)
    if out is None:
        raise HTTPException(status_code=404, detail={
            "error": "not_found", "detail": "No such scan or product version.",
        })
    return {"status": "received", **out}


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
    back: Optional[UploadFile] = File(None, description="Back of pack — the ingredient list."),
    front: Optional[UploadFile] = File(None, description="Front of pack — marketing claims."),
    pairing_confirmed: bool = Form(False, description="User confirms both images show the same pack."),
    # Every text field carries an empty example: /docs otherwise pre-fills them
    # with the word "string", and avoid=string is refused as an unknown allergen
    # (422), while replay=string would be read as the model's answer. (Marking
    # fields include_in_schema=False has no effect inside a multipart form.)
    replay: Optional[str] = Form(None, examples=[""],
                                 description="Testing only: recorded model JSON, used instead of a model call. Leave empty."),
    avoid: Optional[str] = Form(None, examples=[""], description="Comma-separated allergen codes, e.g. 'milk,gluten'."),
    who: Optional[str] = Form(None, examples=[""],
                              description="Old clients only: a name for allergen text. The app sends none (D-074)."),
    compare_regulators: bool = Form(False, description="Also return EU and US status. Information only."),
    barcode: Optional[str] = Form(None, examples=[""], description="EAN/UPC digits from the pack, if the camera read one."),
    device_id: Optional[str] = Form(None, examples=[""], description="Anonymous install id (UUID). No personal data."),
    profiles: Optional[str] = Form(None, examples=[""],
                                   description='JSON [{"ref","age","avoid"}], up to 3. No names (D-074).'),
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

    images = []
    for upload, role in ((back, "back"), (front, "front")):
        img = await _read_image(upload, role)
        if img:
            images.append(img)

    # D-092: everything needed to replay this scan, minus the photos (kept by
    # media) and the model's answer (added once we have it). `who` is left out:
    # an old client may put a name in it (D-074).
    tr = {
        "request_id": trace.current_request_id(), "build": trace.BUILD,
        "data_version": trace.DATA_VERSION, "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "request": {"barcode": barcode, "avoid": avoid_codes if avoid is not None else None,
                    "profiles": people, "pairing_confirmed": pairing_confirmed,
                    "compare_regulators": compare_regulators,
                    "images": [r for _d, _m, r in images], "replay": replay is not None},
        "timings": {},
    }

    # D-024: a barcode alone is a catalogue lookup — no vision call, ~₹0.
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
        result = _catalogue_result(hit, avoid_codes, who, compare_regulators, people)
        result["scan_id"] = _str(_persist(STORE.record_cache_hit, hit, device_id=device_id,
                                          latency_ms=_ms(t0), trace=tr))
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
                + " — recovered as: " + "; ".join(recovered)
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
            "product_match downgraded to indeterminate — independent OCR read "
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
    alarm = cloud_vision.take_alarm()
    if alarm:
        _setup_alarm(f"ocr_config:{alarm}", "Cloud Vision refused the call; scans fall back to Tesseract "
                     f"(~20 s slower) until fixed. Status: {alarm}. See the server log for Google's message.")
    vision["_pairing_attested_by_user"] = pairing_confirmed
    proceed, reliability = rel.assess(vision)
    reliability["client_corrections"] = corrections
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
                allergen_reliable=False),
            "scan_id": _str(scan_id),
            "request_id": tr["request_id"],
            "verdict": None,
            "product": vision.get("product"),
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

    claims_trusted = reliability.get("claims_permitted", True) and vision["front_status"] == "read"
    claim_check = claim_checker.check_claims(
        vision.get("front_claims", []), raw, verdict,
        # An unverified pairing suppresses the claim check the same way an
        # unread front does: in both cases we cannot say these claims
        # belong to this ingredient list.
        vision["front_status"] if reliability.get("claims_permitted", True)
        else "pairing_unverified",
    )

    saved = _persist(
        STORE and STORE.save_scan, vision=vision, verdict=verdict, claim_check=claim_check,
        claims_trusted=claims_trusted, reliability=reliability, barcode=barcode,
        device_id=device_id, latency_ms=_ms(t0), model_name=vision.get("_model") or MODEL,
        prompt_version=PROMPT_VERSION, engine_version=ENGINE_VERSION,
        front_key=keys.get("front"), back_key=keys.get("back"), trace=tr)

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
    return {
        "allergens": allergens,           # D-060: always the first thing a client reads
        # What the app renders, in order (D-060-D-066). Built from the fields below.
        "screen": result_screen.build(
            verdict=verdict, display=display, claim_check=user_claims, extracted=extracted,
            reliability=reliability, profiles=people, allergen_confidence=allergen_confidence,
            allergen_reliable=allergen_reliable),
        "scan_id": saved["scan_id"] if saved else None,
        "catalogue": ({"source": "scan", "product_version_id": saved["product_version_id"],
                       "status": saved["version_status"], "queued_for_review": saved["queued"]}
                      if saved else None),
        "product": vision.get("product"),
        "verdict": verdict,
        "display": display,
        "claim_check": user_claims,
        "extracted": extracted,
        "reliability": reliability,
        "disclosures": rel.disclosures(reliability),
        "regulators": regulators.compare(verdict) if compare_regulators else None,
        "engine_version": ENGINE_VERSION,
    }
