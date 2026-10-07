"""
D-174: the nutrition table of a pack sent to us, read once from the photos we hold.

Item #71 (Sushil, 2026-10-07): Britannia 50 50 Maska Chaska's list and table were
photographed (D-171 steps), Gemini blocked the read (RECITATION, D-172), and the pack
went to a person ("Send it to us"). A send_to_us item had no table to show, so the pack
was published without one, and the next scan asked the user to photograph the table
again (D-168, item #72): a photo we already had.

In order, for one send_to_us item:
1. Free: an earlier model answer of the item's scans that copied the table (a scan refused
   for its list can still have read the table) is checked again by nutrition.check()
   against the Cloud Vision text stored with it. No new read.
2. Paid, once: the table-only prompt (table_prompt.py) on the item's stored back photo,
   checked against Cloud Vision's stored text of that photo, or a new reading of it.

The D-133 rules hold either way: a number is kept only where the second reading has it
and the table adds up; the reviewer ticks that every number shown matches the photo; the
table is published only through ReviewService.approve(). Every attempt is stored with
what it read and its error, failures included (D-092, D-172); none raises.
"""

import json

from insidelabel import trace
from insidelabel.extraction.providers import gemini, ocr_check
from insidelabel.extraction.providers.table_prompt import TABLE_PROMPT, TABLE_PROMPT_VERSION, TABLE_SCHEMA
from insidelabel.lenses import nutrition

OCR_WAIT_S = 60          # a reviewer or the background task waits; a user never does


def has_table_photo(request):
    """
    Did this scan's photos include the nutrition table? The app names each part's kind
    (D-174, `back_kinds`); a scan from before it counts as one when its list came in more
    than one part, since D-171 sends the table as the last part.
    """
    request = request or {}
    kinds = request.get("back_kinds")
    if kinds is not None:
        return "table" in kinds
    return (request.get("back_parts") or 1) >= 2


def wanted(sources):
    """Is there a table to read: any of the item's scans with a table photo still on file?"""
    return any(s["back_image_key"] and has_table_photo(s["request"]) for s in sources["scans"])


def _stored_text(scan):
    back = ((scan.get("ocr") or {}).get("back") or {})
    return (back.get("text") or None), back.get("reader")


def from_stored_answer(scan):
    """nutrition.check() on a scan's stored answer and its stored second reading, or None."""
    raw = scan.get("model_raw")
    if not raw or gemini.blocked_reason(raw):
        return None
    try:
        answer = json.loads(gemini._FENCE.sub("", raw))
    except (TypeError, ValueError):
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get("nutrition"), dict):
        return None
    text, reader = _stored_text(scan)
    if not text:
        return None
    return nutrition.check(answer["nutrition"], text, (answer.get("product") or {}).get("net_quantity"),
                           reader=reader)


def _second_reading(scan, photo):
    """Cloud Vision's stored text of the photo, else a new reading of it (Tesseract if Vision is off)."""
    text, reader = _stored_text(scan)
    if text:
        return text, reader
    read = ocr_check.start_back_read(photo)
    read.done.wait(OCR_WAIT_S)
    got = ocr_check.result_of(read, [])
    return got.get("ocr_text"), got.get("reader")


def _paid_call(prompt, images):
    """One table-only answer, with the label reader's retries (D-172: RECITATION twice more)."""
    for tries in range(1, gemini.RECITATION_RETRIES + 2):
        try:
            return gemini._with_retries(lambda: gemini.call_gemini_json(prompt, images, TABLE_SCHEMA))
        except gemini.VisionBlocked as e:
            if e.reason != "recitation" or tries > gemini.RECITATION_RETRIES:
                raise


def read_for_item(service, media, item_id, *, paid=True, call=None, requested_by=None):
    """
    Read a send_to_us item's table: a stored answer first, then (when `paid`) one
    table-only read. Returns the stored review_table_reads row, or None when there was
    nothing to try (not a send_to_us item, no table photo, or `paid` off and no stored
    answer). `call(prompt, images) -> text` defaults to a paid Gemini call; tests pass
    a recorded answer instead.
    """
    sources = service.table_sources(item_id)
    if sources is None or sources["item"]["kind"] != "send_to_us":
        return None
    for scan in sources["scans"]:
        panel = from_stored_answer(scan)
        if panel and panel.get("status") in nutrition.SHOWN:
            text, reader = _stored_text(scan)
            return service.save_table_read(item_id, source="stored_answer", scan_id=scan["id"],
                                           prompt_version=scan.get("prompt_version"),
                                           build=trace.BUILD, model_raw=scan["model_raw"], ocr_reader=reader,
                                           ocr_text=text, panel=panel, requested_by=requested_by)
    if not paid:
        return None
    scan = next((s for s in sources["scans"] if s["back_image_key"] and has_table_photo(s["request"])), None)
    if scan is None and requested_by:
        # A person asked: read the latest photo even when no part was marked as the table.
        scan = next((s for s in sources["scans"] if s["back_image_key"]), None)
    if scan is None:
        return None
    row = {"source": "table_read", "scan_id": scan["id"], "model": gemini.MODEL,
           "prompt_version": TABLE_PROMPT_VERSION, "build": trace.BUILD, "requested_by": requested_by}
    got = media.get(scan["back_image_key"]) if media else None
    if got is None:
        return service.save_table_read(item_id, **row, model_error="The photo is no longer stored.")
    photo, mime = got
    raw = None
    try:
        raw = (call or _paid_call)(TABLE_PROMPT, [(photo, mime, "back")])
        answer = json.loads(gemini._FENCE.sub("", raw or ""))
        if not isinstance(answer, dict):
            raise ValueError("not a JSON object")
    except gemini.VisionBlocked as e:
        return service.save_table_read(item_id, **row, model_raw=gemini.blocked_marker(e.reason),
                                       model_error=f"{type(e).__name__}: {e}"[:1000])
    except (gemini.VisionError, ValueError, TypeError) as e:
        return service.save_table_read(item_id, **row, model_raw=raw,
                                       model_error=f"{type(e).__name__}: {e}"[:1000])
    text, reader = _second_reading(scan, photo)
    panel = nutrition.check(answer.get("nutrition"), text, answer.get("net_quantity"), reader=reader)
    return service.save_table_read(item_id, **row, model_raw=raw, ocr_reader=reader, ocr_text=text, panel=panel)
