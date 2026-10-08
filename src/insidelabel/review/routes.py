"""
Reviewer screen (D-028): the label photo next to what was read from it, and
the decision. Server-rendered; the one custom admin screen the plan allows.

Auth: HTTP Basic, one account per reviewer (D-097, `tools/reviewers.py`); the
name is recorded on every decision. The shared INSIDELABEL_REVIEW_TOKEN is only
accepted while no account exists, so the first one can be created without a
lockout. Failed logins are throttled per name and per address. Every form
carries a CSRF token derived from the reviewer's password hash (the token, in
bootstrap mode), because a browser re-sends Basic credentials on cross-site
requests; a password reset invalidates the forms issued before it.
"""

import difflib
import hashlib
import hmac
import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from insidelabel import barcode as barcode_rules
from insidelabel import pictures
from insidelabel import ratelimit
from insidelabel.core import engine
from insidelabel.lenses import infant as infant_lens
from insidelabel.lenses import nutrition
from insidelabel.db.categories import COMMON
from insidelabel.review import accounts, checker, table_read
from insidelabel.review.service import ReviewError, ReviewService

router = APIRouter(prefix="/review", include_in_schema=False)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
_basic = HTTPBasic(realm="InsideLabel review")
_NAME = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")

# Set by the app at startup (api/main.py); None means review is not configured.
SERVICE: ReviewService = None
MEDIA = None


def _token():
    return os.environ.get("INSIDELABEL_REVIEW_TOKEN", "")


def reviewer(request: Request, creds: HTTPBasicCredentials = Depends(_basic)):
    if SERVICE is None:
        raise HTTPException(status_code=503, detail={
            "error": "review_disabled",
            "detail": "Set INSIDELABEL_DB to enable the review screen."})
    name, ip = creds.username, ratelimit.client_ip(request)
    wait = ratelimit.LIMITER.wait("review_login_fail", name=name, ip=ip)
    if wait:
        raise HTTPException(status_code=429, headers={"Retry-After": str(int(wait) + 1)},
                            detail={"error": "too_many_attempts", "detail": "Too many wrong passwords. Wait a few minutes."})
    key = None
    if _NAME.match(name):
        if accounts.any_accounts(SERVICE.conninfo):
            key = accounts.check(SERVICE.conninfo, name, creds.password)
        else:
            # Bootstrap only: the shared token until the first account exists.
            token = _token()
            if not token:
                raise HTTPException(status_code=503, detail={
                    "error": "review_disabled",
                    "detail": "Create a reviewer account: python tools/reviewers.py add <name>"})
            if secrets.compare_digest(creds.password.encode(), token.encode()):
                key = token
    if key is None:
        ratelimit.LIMITER.hit("review_login_fail", name=name, ip=ip)
        raise HTTPException(status_code=401, detail={"error": "unauthorised"},
                            headers={"WWW-Authenticate": 'Basic realm="InsideLabel review"'})
    request.state.csrf_key = key
    return name


def _csrf(request, name):
    return hmac.new(request.state.csrf_key.encode(), f"csrf:{name}".encode(), hashlib.sha256).hexdigest()


async def _form(request, name):
    form = dict(await request.form())
    if not secrets.compare_digest(form.get("csrf", ""), _csrf(request, name)):
        raise HTTPException(status_code=403, detail={"error": "bad_csrf_token"})
    return form


def _page(request, template, name, **ctx):
    return templates.TemplateResponse(request, template, {"reviewer": name, "csrf": _csrf(request, name), **ctx})


# ---------------------------------------------------------------- queue

@router.get("")
def queue(request: Request, name: str = Depends(reviewer)):
    return _page(request, "queue.html", name,
                 summary=SERVICE.summary(),
                 mine=SERVICE.list_items("claimed", reviewer=name),
                 open_items=SERVICE.list_items("open"))


@router.post("/claim-next")
async def claim_next(request: Request, name: str = Depends(reviewer)):
    await _form(request, name)
    item_id = SERVICE.claim_next(name)
    return RedirectResponse(f"/review/item/{item_id}" if item_id else "/review?empty=1", status_code=303)


# ---------------------------------------------------------------- item

# D-146: the tester's answer to "Check these match the numbers under the barcode".
BARCODE_ANSWER = {
    "confirmed": "On the phone, the tester said the digits match the numbers under the barcode.",
    "rescanned": "On the phone, the tester scanned again before this code, then said its digits match the "
                 "numbers under the barcode.",
}

def _diff(old, new):
    """Line diff of two ingredient lists for a reformulation."""
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            rows += [("same", x) for x in old[i1:i2]]
        else:
            rows += [("removed", x) for x in old[i1:i2]] + [("added", x) for x in new[j1:j2]]
    return rows


@router.get("/item/{item_id}")
def item(request: Request, item_id: int, name: str = Depends(reviewer), error: str = None):
    data = SERVICE.get(item_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    v, p, corr = data["version"], data["product"], data["correction"]
    ingredients = (v or {}).get("ingredients") or []
    # Pre-fill the form with what was read; a correction's proposal is shown beside it.
    form = {
        "name": (p or {}).get("name") or "",
        "brand": (p or {}).get("brand") or "",
        "variant": (p or {}).get("variant") or "",
        # A pack sent to us has no product yet: the barcode the app read, if any.
        "barcode": (p or {}).get("barcode") or ((data["scan"] or {}).get("request") or {}).get("barcode") or "",
        "category": (p or {}).get("category_code") or "",
        "ingredients": "\n".join(ingredients),
        "allergen_statement": (v or {}).get("allergen_statement") or "",
        "front_claims": "\n".join((v or {}).get("front_claims") or []),
        "note": "",
        "drafted_by": name,
        "category_source": "reviewer",
    }
    # D-117: an agent draft, when there is one, fills the form in; its checks
    # are shown above it, so a review is a correction, not a blank form.
    draft = SERVICE.latest_draft(item_id)
    if draft and draft["outcome"] != "error" and data["item"]["status"] in ("open", "claimed"):
        dd = draft["draft"]
        form.update({
            "name": dd.get("name") or form["name"], "brand": dd.get("brand") or form["brand"],
            "variant": dd.get("variant") or "", "barcode": dd.get("barcode") or form["barcode"],
            "category": checker.category_code(dd.get("category")) or form["category"],
            "ingredients": "\n".join(dd.get("ingredients") or []) or form["ingredients"],
            "allergen_statement": dd.get("allergen_statement") or "",
            "front_claims": "\n".join(dd.get("front_claims") or []),
            "note": dd.get("note") or "", "drafted_by": "gemini",
            "category_source": dd.get("category_source") or "codex_descriptor",
        })
    raw = (v or {}).get("raw_extraction") or {}
    verdict = engine.analyze(", ".join(ingredients)) if ingredients else None
    # D-140 phase 3: an infant food's checks, in shadow: as stored with the reading, or
    # computed from it for a version read before they existed.
    infant = raw.get("_infant")
    if infant is None and (v or {}).get("pack_kind") == "infant" and raw.get("ingredients"):
        ocr = (((data["scan"] or {}).get("ocr") or {}).get("back") or {}).get("text")
        infant = infant_lens.check(raw, ingredients, ocr)
    # D-106: where the item's photos came from (camera or upload), as the app said.
    sources = ((data["scan"] or {}).get("request") or {}).get("photo_sources") or {}
    # D-143: a barcode only the camera scanner read, shown above the form with a tick box.
    unsure = barcode_rules.unconfirmed((data["scan"] or {}).get("barcode_check"))
    # D-146: what the tester said about the digits on the phone; supporting evidence only.
    answer = BARCODE_ANSWER.get(((data["scan"] or {}).get("request") or {}).get("barcode_answer"))
    # D-174: a pack sent to us: its table as read from its photos, and the last attempt.
    reads = SERVICE.table_reads(item_id) if data["item"]["kind"] == "send_to_us" else []
    sent_table = next((r["panel"] for r in reads
                       if (r["panel"] or {}).get("status") in nutrition.SHOWN), None)
    return _page(request, "item.html", name, d=data, form=form, error=error, sources=sources,
                 sent_table=sent_table, table_read=reads[0] if reads else None,
                 table_photo=any(table_read.has_table_photo(s["request"])
                                 for s in [data["scan"] or {}, *data["attempts"]] if s.get("back_image_key")),
                 verdict=verdict, raw=raw, reliability=raw.get("_reliability") or {},
                 diff=_diff(data["current"]["ingredients"], ingredients) if data["current"] else None,
                 mine=data["item"]["status"] == "claimed" and data["item"]["claimed_by"] == name,
                 correction=corr, categories=SERVICE.categories(), common=COMMON, draft=draft,
                 barcode_unsure=barcode_rules.check_text(unsure) if unsure else None, infant=infant,
                 barcode_answer=answer, **_picture_offer(data))


# ---------------------------------------------------------------- pack pictures (D-182)

def _picture_offer(data):
    """
    D-182: may this item's front photo become the pack picture? Only a shopper's, from an
    install that agreed to the terms saying so (pictures.TERMS_FROM). Reviewers' own photos
    go up on /review/pictures.
    """
    front = data["images"]["front"]
    if not front:
        return {"picture_offer": None}
    who = pictures.shopper_front(SERVICE.conninfo, front)
    pid = (data["version"] or {}).get("product_id")
    shown = pictures.current(SERVICE.conninfo, pid) if pid else None
    return {"picture_offer": {"ok": bool(who), "shown": shown,
                              "why": None if who else "the shopper agreed to terms older than the ones that say "
                                                      "a front photo may be shown to others, or the photo isn't a "
                                                      "shopper's. Upload your own on Pack pictures."}}


def _check_picture_crop(front, crop):
    """
    D-186: before anything is published, a drawn crop must fit the front photo, so a bad
    one is refused with nothing saved. No photo to check against is left to _make_picture.
    """
    got = MEDIA.get(front) if (crop is not None and front and MEDIA) else None
    if got:
        try:
            pictures.shrink(got[0], crop)
        except pictures.PictureError as e:
            raise ReviewError(f"Pack picture: {e}") from e


def _make_picture(item_id, front, name, crop=None):
    """After a publish: the ticked front photo (cropped as drawn, D-186) becomes the product's pack picture."""
    who = pictures.shopper_front(SERVICE.conninfo, front)
    got = MEDIA.get(front) if (who and MEDIA) else None
    data = SERVICE.get(item_id)
    pid = pictures.product_of(SERVICE.conninfo, version_id=data["item"]["product_version_id"]) if data else None
    if not (got and pid):
        raise ReviewError("Published, but the front photo couldn't be used as the pack picture.")
    pictures.add(SERVICE.conninfo, MEDIA, product_id=pid, data=got[0], source="shopper_photo",
                 approved_by=name, scan_id=who["scan_id"], taken_on=who["taken_on"], crop=crop)



@router.post("/item/{item_id}/claim")
async def claim(request: Request, item_id: int, name: str = Depends(reviewer)):
    await _form(request, name)
    if not SERVICE.claim(item_id, name):
        return RedirectResponse(f"/review/item/{item_id}?error=Someone+else+has+this+item",
                                status_code=303)
    return RedirectResponse(f"/review/item/{item_id}", status_code=303)


async def _decide(request, item_id, name, action):
    form = await _form(request, name)
    try:
        if action == "approve":
            # D-182: a person ticks both boxes; the review agent never sets these (it calls approve() itself).
            front = crop = None
            if form.get("pack_picture"):
                if not form.get("pack_alone"):
                    raise ReviewError("Pack picture: tick that the photo shows the pack alone, or untick it.")
                data = SERVICE.get(item_id)
                front = data and data["images"]["front"]
                # D-186: the ticks are about the cropped copy; a bad crop stops the publish too.
                try:
                    crop = pictures.crop_from_form(form)
                except pictures.PictureError as e:
                    raise ReviewError(f"Pack picture: {e}") from e
                _check_picture_crop(front, crop)
            SERVICE.approve(item_id, name, form)
            if front:
                try:
                    _make_picture(item_id, front, name, crop)
                except (ReviewError, pictures.PictureError) as e:
                    from urllib.parse import quote
                    return RedirectResponse(f"/review/pictures?error={quote(str(e))}", status_code=303)
        elif action == "reject":
            SERVICE.reject(item_id, name, form.get("reason"))
        else:
            SERVICE.release(item_id, name)
    except ReviewError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/review/item/{item_id}?error={quote(str(e))}", status_code=303)
    return RedirectResponse("/review", status_code=303)


@router.post("/item/{item_id}/read-table")
async def read_table(request: Request, item_id: int, name: str = Depends(reviewer)):
    """
    D-174: a person asks for a pack sent to us to have its nutrition table read from its
    photos (one paid read). Not when a usable read is already stored.
    """
    await _form(request, name)
    data = SERVICE.get(item_id)
    if data is None or data["item"]["kind"] != "send_to_us" or data["item"]["status"] not in ("open", "claimed"):
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if not any((r["panel"] or {}).get("status") in nutrition.SHOWN for r in SERVICE.table_reads(item_id)):
        await run_in_threadpool(table_read.read_for_item, SERVICE, MEDIA, item_id, requested_by=name)
    return RedirectResponse(f"/review/item/{item_id}", status_code=303)


@router.post("/item/{item_id}/approve")
async def approve(request: Request, item_id: int, name: str = Depends(reviewer)):
    return await _decide(request, item_id, name, "approve")


@router.post("/item/{item_id}/reject")
async def reject(request: Request, item_id: int, name: str = Depends(reviewer)):
    return await _decide(request, item_id, name, "reject")


@router.post("/item/{item_id}/release")
async def release(request: Request, item_id: int, name: str = Depends(reviewer)):
    return await _decide(request, item_id, name, "release")


@router.get("/pictures")
def picture_list(request: Request, name: str = Depends(reviewer), error: str = None, done: str = None):
    """D-182: the pack pictures being shown, and a form to upload one of your own."""
    return _page(request, "pictures.html", name, pictures=pictures.recent(SERVICE.conninfo),
                 error=error, done=done)


@router.post("/pictures")
async def picture_upload(request: Request, name: str = Depends(reviewer)):
    """D-182: a reviewer's own photo of a pack's front, for a product in the catalogue."""
    from urllib.parse import quote
    form = await _form(request, name)
    photo = form.get("photo")
    data = await photo.read() if hasattr(photo, "read") else b""
    code, reason = barcode_rules.check((form.get("barcode") or "").strip())
    try:
        if reason:
            raise ReviewError(f"Barcode: {barcode_rules.MESSAGES[reason]}")
        pid = pictures.product_of(SERVICE.conninfo, barcode=code)
        if not pid:
            raise ReviewError("No product in the catalogue has that barcode.")
        if not data:
            raise ReviewError("Choose a photo of the front of the pack.")
        if not (form.get("pack_alone") and form.get("same_product")):
            raise ReviewError("Tick both boxes: the photo shows the pack alone, and it is this product.")
        pictures.add(SERVICE.conninfo, MEDIA, product_id=pid, data=data, source="reviewer_upload",
                     approved_by=name, crop=pictures.crop_from_form(form))     # D-186: cropped as drawn
    except (ReviewError, pictures.PictureError) as e:
        return RedirectResponse(f"/review/pictures?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/review/pictures?done={quote(code)}", status_code=303)


@router.post("/pictures/{picture_id}/remove")
async def picture_remove(request: Request, picture_id: int, name: str = Depends(reviewer)):
    """D-182: stop showing a picture (the row stays, with who removed it)."""
    await _form(request, name)
    pictures.remove(SERVICE.conninfo, picture_id, name)
    return RedirectResponse("/review/pictures", status_code=303)


# ---------------------------------------------------------------- photos

@router.get("/media/{key}")
def media(key: str, name: str = Depends(reviewer)):
    got = MEDIA.get(key) if MEDIA else None
    if got is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    data, mime = got
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})
