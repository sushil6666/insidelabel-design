"""
The review agents (D-117): Gemini drafts a catalogue record for a queue item,
the checker (review/checker.py) confirms it or sends it to a person.

In shadow mode, the default, a draft is stored and shown beside the item on
/review and nothing is published. Publishing switches on only after the
shadow measurement (D-117 point 4: 30 of Sushil's reviews, 95 % agreement),
and needs its own build step (undo, the agent-published list); until then
mode "publish" is refused.

Every draft is stored with Gemini's raw answer, the prompt version and the
build (D-092), including drafts that failed.
"""

import json

from insidelabel import trace
from insidelabel.extraction.providers import gemini
from insidelabel.review import checker
from insidelabel.review.draft_prompt import DRAFT_PROMPT, DRAFT_SCHEMA, PROMPT_VERSION

DRAFTER = "gemini"
MODES = ("shadow",)            # "publish" joins after the shadow measurement (D-117 point 4)


class DraftError(Exception):
    """The drafter's answer couldn't be used; stored as an 'error' draft."""


def context(data, categories):
    """What the drafter and the checker see for one queue item (ReviewService.get)."""
    q, v, p, scan = data["item"], data["version"] or {}, data["product"] or {}, data["scan"] or {}
    raw = v.get("raw_extraction") or {}
    ocr = ((scan.get("ocr") or {}).get("back") or {}).get("text") or ""
    return {
        "kind": q["kind"],
        "ocr_text": ocr,
        "raw": raw,
        "request": scan.get("request") or {},
        "categories": {code for code, _name, _depth in categories},
        "has_front": bool(data["images"].get("front")),
        "nutrition": v.get("nutrition"),                  # D-133: checked against ocr_text
        "barcode_check": scan.get("barcode_check"),       # D-143: the camera's code against the photos
        "reading": {
            "brand": p.get("brand"), "name": p.get("name"), "variant": p.get("variant"),
            "barcode": p.get("barcode") or (scan.get("request") or {}).get("barcode"),
            "ingredients": v.get("ingredients") or [],
            "allergen_statement": v.get("allergen_statement"),
            "front_claims": v.get("front_claims") or [],
            "extraction_notes": raw.get("extraction_notes") or [],
        },
    }


def prompt_text(ctx, categories):
    cats = "\n".join(f"{code} {name}" for code, name, _depth in categories)
    return (f"{DRAFT_PROMPT}\n\nOUR READER'S EXTRACTION (JSON):\n{json.dumps(ctx['reading'], ensure_ascii=False)}"
            f"\n\nCLOUD VISION TEXT OF THE BACK PHOTO:\n{ctx['ocr_text'] or '(none)'}"
            f"\n\nFSSAI FOOD CATEGORIES (APPENDIX A):\n{cats}\n")


def images_for(data, media):
    """(bytes, mime, role) for the back and front photos that are still on disk."""
    out = []
    for role in ("back", "front"):
        key = data["images"].get(role)
        got = media.get(key) if (media and key) else None
        if got:
            out.append((got[0], got[1], role))
    return out


def parse(text):
    try:
        d = json.loads(gemini._FENCE.sub("", text or ""))
    except (TypeError, ValueError) as e:
        raise DraftError(f"not JSON: {e}") from e
    if not isinstance(d, dict):
        raise DraftError("not a JSON object")
    missing = [k for k in DRAFT_SCHEMA["required"] if k not in d]
    if missing:
        raise DraftError(f"missing fields: {', '.join(missing)}")
    for k in ("ingredients", "front_claims", "changes", "doubts"):
        if not isinstance(d[k], list) or not all(isinstance(x, str) for x in d[k]):
            raise DraftError(f"{k} is not a list of strings")
    d["category"] = checker.category_code(d.get("category"))
    return d


def draft_item(service, media, item_id, mode="shadow", call=None):
    """
    Draft and check one queue item, store the draft, return its row dict.
    `call(prompt, images) -> text` defaults to a paid Gemini call; tests and
    replays pass a recorded answer instead.
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}: publishing isn't built yet; drafts run in shadow (D-117 point 4)")
    data = service.get(item_id)
    if data is None:
        raise ValueError(f"No queue item {item_id}.")
    categories = service.categories()
    ctx = context(data, categories)
    call = call or (lambda prompt, imgs: gemini._with_retries(
        lambda: gemini.call_gemini_json(prompt, imgs, DRAFT_SCHEMA)))
    raw_text, draft, checks, outcome, error = None, {}, [], "error", None
    try:
        raw_text = call(prompt_text(ctx, categories), images_for(data, media))
        draft = parse(raw_text)
        checks = checker.check(draft, ctx)
        outcome = checker.outcome(checks)
    except (DraftError, gemini.VisionError) as e:
        error = f"{type(e).__name__}: {e}"
    return service.save_draft(item_id, drafter=DRAFTER, model=gemini.MODEL, prompt_version=PROMPT_VERSION,
                              build=trace.BUILD, model_raw=raw_text, draft=draft, checks=checks,
                              outcome=outcome, error=error, mode=mode)


# ---------------------------------------------------------------- D-117 point 4

GATE = {"items": 30, "agreement": 0.95}


def _norm_line(x):
    return " ".join((x or "").lower().replace(" (", "(").replace("( ", "(").replace(" )", ")").split()).rstrip(".")


def compare(row):
    """One decided item: does the agent's draft agree with what the person decided?"""
    d = row["draft"] or {}
    if row["status"] == "rejected":
        # The agents agree with a rejection only by not confirming the item.
        return {"id": row["id"], "decision": "rejected", "agrees": row["outcome"] != "confirmed",
                "category": None, "ingredients": None, "claims": None,
                "confirmed_but_corrected": row["outcome"] == "confirmed", "by": row["drafted_by"]}
    cat = checker.category_code(d.get("category")) == (row["category"] or "")
    ing = [_norm_line(x) for x in d.get("ingredients") or []] == [_norm_line(x) for x in row["ingredients"] or []]
    clm = sorted(_norm_line(x) for x in d.get("front_claims") or []) == \
        sorted(_norm_line(x) for x in row["front_claims"] or [])
    return {"id": row["id"], "decision": "published", "agrees": cat and ing and clm,
            "category": cat, "ingredients": ing, "claims": clm,
            "confirmed_but_corrected": row["outcome"] == "confirmed" and not (cat and ing and clm),
            "by": row["drafted_by"]}


def measure(service):
    """The shadow report: agreement per measure, and whether publishing may switch on."""
    rows = [compare(r) for r in service.decided_with_drafts()]
    pub = [r for r in rows if r["decision"] == "published"]

    def rate(key):
        return (sum(1 for r in pub if r[key]) / len(pub)) if pub else None

    report = {
        "items": len(rows), "published": len(pub), "rejected": len(rows) - len(pub),
        "category": rate("category"), "ingredients": rate("ingredients"), "claims": rate("claims"),
        "confirmed_but_corrected": [r["id"] for r in rows if r["confirmed_but_corrected"]],
        "disagreements": [r for r in rows if not r["agrees"]],
        "by_final_drafter": {},
    }
    for r in pub:
        b = report["by_final_drafter"].setdefault(r["by"] or "unrecorded", {"items": 0, "agree": 0})
        b["items"] += 1
        b["agree"] += 1 if r["agrees"] else 0
    report["gate_passes"] = bool(
        report["items"] >= GATE["items"]
        and (report["category"] or 0) >= GATE["agreement"]
        and (report["ingredients"] or 0) >= GATE["agreement"]
        and not report["confirmed_but_corrected"])
    return report
