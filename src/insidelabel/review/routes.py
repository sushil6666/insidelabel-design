"""
Reviewer screen (D-028): the label photo next to what was read from it, and
the decision. Server-rendered; the one custom admin screen the plan allows.

Auth: HTTP Basic. Username = reviewer name (recorded on every decision),
password = INSIDELABEL_REVIEW_TOKEN. Every form carries a CSRF token derived
from the reviewer and the secret, because a browser re-sends Basic credentials
on cross-site requests.
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

from insidelabel.core import engine
from insidelabel.db.categories import COMMON
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


def reviewer(creds: HTTPBasicCredentials = Depends(_basic)):
    token = _token()
    if SERVICE is None or not token:
        raise HTTPException(status_code=503, detail={
            "error": "review_disabled",
            "detail": "Set INSIDELABEL_DB and INSIDELABEL_REVIEW_TOKEN to enable the review screen."})
    ok = secrets.compare_digest(creds.password.encode(), token.encode())
    if not ok or not _NAME.match(creds.username):
        raise HTTPException(status_code=401, detail={"error": "unauthorised"},
                            headers={"WWW-Authenticate": 'Basic realm="InsideLabel review"'})
    return creds.username


def _csrf(name):
    return hmac.new(_token().encode(), f"csrf:{name}".encode(), hashlib.sha256).hexdigest()


async def _form(request, name):
    form = dict(await request.form())
    if not secrets.compare_digest(form.get("csrf", ""), _csrf(name)):
        raise HTTPException(status_code=403, detail={"error": "bad_csrf_token"})
    return form


def _page(request, template, name, **ctx):
    return templates.TemplateResponse(request, template, {"reviewer": name, "csrf": _csrf(name), **ctx})


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
        "barcode": (p or {}).get("barcode") or "",
        "category": (p or {}).get("category_code") or "",
        "ingredients": "\n".join(ingredients),
        "allergen_statement": (v or {}).get("allergen_statement") or "",
        "front_claims": "\n".join((v or {}).get("front_claims") or []),
    }
    raw = (v or {}).get("raw_extraction") or {}
    verdict = engine.analyze(", ".join(ingredients)) if ingredients else None
    return _page(request, "item.html", name, d=data, form=form, error=error,
                 verdict=verdict, raw=raw, reliability=raw.get("_reliability") or {},
                 diff=_diff(data["current"]["ingredients"], ingredients) if data["current"] else None,
                 mine=data["item"]["status"] == "claimed" and data["item"]["claimed_by"] == name,
                 correction=corr, categories=SERVICE.categories(), common=COMMON)


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
            SERVICE.approve(item_id, name, form)
        elif action == "reject":
            SERVICE.reject(item_id, name, form.get("reason"))
        else:
            SERVICE.release(item_id, name)
    except ReviewError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/review/item/{item_id}?error={quote(str(e))}", status_code=303)
    return RedirectResponse("/review", status_code=303)


@router.post("/item/{item_id}/approve")
async def approve(request: Request, item_id: int, name: str = Depends(reviewer)):
    return await _decide(request, item_id, name, "approve")


@router.post("/item/{item_id}/reject")
async def reject(request: Request, item_id: int, name: str = Depends(reviewer)):
    return await _decide(request, item_id, name, "reject")


@router.post("/item/{item_id}/release")
async def release(request: Request, item_id: int, name: str = Depends(reviewer)):
    return await _decide(request, item_id, name, "release")


# ---------------------------------------------------------------- photos

@router.get("/media/{key}")
def media(key: str, name: str = Depends(reviewer)):
    got = MEDIA.get(key) if MEDIA else None
    if got is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    data, mime = got
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})
