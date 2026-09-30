"""
barcode.py - is this the barcode of a retail pack? (D-103)

The barcode is the catalogue key (D-024): a wrong one files a pack under the
wrong product or asks a reviewer to publish nonsense. The app checks the check
digit, but the server never did, and a check digit alone isn't enough: on
2026-09-26 "12222333333333" passed it. That is a GTIN-14 with indicator 1 (a
carton or case), and the GTIN-13 inside starts with 2 (a shop's own in-store
code). Neither is printed on a pack a shopper picks up.

The rules are GS1's (data/barcode_rules.json, with the table numbers). No
patterns here: digits are checked with str methods, so this file can't turn
into a second number parser.

Barcodes are read from photos here too (D-104), with zxing-cpp: a classical
decoder, not a model, so it either reads the bars or reports nothing. The app
no longer lets anyone type a barcode.
"""

import io
import json
import os

_DATA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "barcode_rules.json"))
with open(_DATA, encoding="utf-8") as _f:
    RULES = json.load(_f)

# Shown to the user (wording lint: tests/test_input_validation.py).
MESSAGES = {
    "length": "A barcode has 8, 12, 13 or 14 digits. Check the number under the barcode.",
    "check_digit": "One of those digits doesn't look right. Check the number under the barcode.",
    "case_code": "That barcode is for a carton or case, not a single pack. Scan the barcode on the pack itself.",
    "store_code": "That looks like a shop's own label (for loose or weighed items), not the brand's barcode. "
                  "Scan the barcode printed on the pack, or photograph the ingredient list.",
    "not_a_product": "That barcode isn't for a food pack (it may be a book, magazine or coupon). "
                     "Scan the barcode on the food pack.",
    # D-144: two reads of one photo disagree, or the second finds nothing.
    "barcode_unsure": "We couldn't read that barcode clearly from the photo. Scan it with the camera "
                      "scanner instead, or take the photo again closer, with the barcode flat and in focus.",
}


def check_digit_ok(code):
    """GS1 mod-10 (General Specifications 7.9.1): weights 3,1,3… from the right, excluding the check digit."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(code[:-1])))
    return (10 - total % 10) % 10 == int(code[-1])


def _prefix_reason(code, table):
    for reason in ("store_code", "not_a_product"):
        if any(code.startswith(p) for p in table[reason]):
            return reason
    return None


def check(raw):
    """
    (normalised code, None) for a retail pack's barcode, else (None, reason).
    A GTIN-14 with indicator 0 comes back as the GTIN-13 inside it; everything
    else is returned as given, so existing catalogue keys don't change.
    """
    code = "".join(ch for ch in str(raw or "") if not ch.isspace() and ch != "-")
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return None, "length"
    if not check_digit_ok(code):
        return None, "check_digit"
    if len(code) == 14:
        if code[0] != "0":
            return None, "case_code"            # Table 2-17: 1-8 groupings, 9 variable measure
        code = code[1:]
    if len(code) == 8:
        reason = _prefix_reason(code, RULES["gtin8_prefixes"])
    else:
        # D-104: one key per pack. The phone camera reports a UPC-A as 12
        # digits, the photo reader as 13 with a leading 0; both become 13.
        code = code.zfill(13)
        reason = _prefix_reason(code, RULES["gtin13_prefixes"])
    return (None, reason) if reason else (code, None)


def codes_in_text(text):
    """
    The retail barcodes printed as digits in a text (an OCR read of a label),
    normalised by check(), in the order found. The digits under the bars are
    printed in groups ("8 901499 008343"), so digit groups separated only by
    spaces or line breaks are joined, trying every run of consecutive groups.
    Any other character ends a run. str methods only, like the rest of this file.
    """
    runs, groups, digits = [], [], ""
    for ch in (text or "") + "\x00":
        if ch.isdigit():
            digits += ch
            continue
        if digits:
            groups.append(digits)
            digits = ""
        if not ch.isspace():
            if groups:
                runs.append(groups)
            groups = []
    found = []
    for groups in runs:
        for i in range(len(groups)):
            joined = ""
            for g in groups[i:]:
                joined += g
                if len(joined) > 14:
                    break
                code, reason = check(joined) if len(joined) in (8, 12, 13, 14) else (None, None)
                if code and code not in found:
                    found.append(code)
    return found


def confirm(code, photos, ocr_text=None):
    """
    D-143: does anything besides the barcode reader that sent `code` show it?
    photos: [(role, bytes)], the scan's own photos; ocr_text: the independent
    reader's text of the back (D-093). The camera scanner takes a code seen in
    two frames of one view, so one blur can give the same wrong code twice
    (product 42: 4901196008343 for 8901499008343).
      confirmed  a photo's read (read_from_photo, D-144) or the OCR text shows `code`
      mismatch   a photo reads another code and none reads `code`
      not_shown  nothing shows `code` (the OCR text's own codes are listed, not
                 trusted: a licence number can hold a 13-digit run that passes)
    """
    read = {}
    for role, data in photos:
        codes, _why = read_from_photo(data, ocr_text=ocr_text if role == "back" else None)
        if codes:
            read[role] = codes
    ocr = codes_in_text(ocr_text) if ocr_text else []
    shown = {c for codes in read.values() for c in codes}
    status = "confirmed" if code in shown or code in ocr else ("mismatch" if shown else "not_shown")
    return {"code": code, "status": status, "photo_codes": read, "ocr_codes": ocr}


def unconfirmed(check):
    """
    D-143: a scan's barcode_check that a reviewer must look at: the code came
    from the camera scanner and no photo or OCR text shows it. Only camera
    reads are held (Sushil, 2026-09-30); a code read from a photo has its own
    rule (D-144: two reads agree, or its digits are in the OCR text). The app always says which (D-104),
    so a request that doesn't say (an API client, a test) is recorded, not held.
    """
    if not check or check.get("status") == "confirmed" or check.get("source") != "camera":
        return None
    return check


def check_text(check):
    """What the reviewer is told about an unconfirmed barcode."""
    source = {"camera": "the camera scanner"}.get(check.get("source"), "the app")
    if check["status"] == "mismatch":
        read = sorted({c for codes in (check.get("photo_codes") or {}).values() for c in codes})
        return (f"Barcode {check['code']} came from {source}, but the photos read {', '.join(read)}. "
                "Read the digits printed under the bars on the photo.")
    ocr = check.get("ocr_codes") or []
    return (f"Barcode {check['code']} came from {source} alone: no photo and no OCR text shows it"
            + (f" (the OCR text has {', '.join(ocr)})" if ocr else "") + ".")


def upce_to_upca(code):
    """An 8-digit UPC-E (number system, 6 digits, check) as its 12-digit UPC-A (GS1 GenSpecs 5.2.2.4.2)."""
    if len(code) != 8 or not code.isdigit():
        return code
    ns, d, check = code[0], code[1:7], code[7]
    d1, d2, d3, d4, d5, d6 = d
    if d6 in "012":
        body = d1 + d2 + d6 + "0000" + d3 + d4 + d5
    elif d6 == "3":
        body = d1 + d2 + d3 + "00000" + d4 + d5
    elif d6 == "4":
        body = d1 + d2 + d3 + d4 + "00000" + d5
    else:
        body = d1 + d2 + d3 + d4 + d5 + "0000" + d6
    return ns + body + check


# D-144: the second read's scale. Half size refused correct codes on the server
# (2 of 6, 2026-09-30), three-quarter size 1 of 6: a thin bar at a smaller scale
# is lost. The OCR text (below) is what saves those, where there is one.
SECOND_READ = 0.75


def read_from_photo(data, two_reads=True, ocr_text=None):
    """
    Every retail barcode zxing-cpp finds in the photo: ([codes that pass
    check()], [reasons for ones that don't]). ([], []) when none is found or
    the photo can't be decoded here (HEIC).

    D-144 (replacing D-141): a code counts when two reads agree, the photo as
    before (up to 2400 px) and once more at SECOND_READ, or when its digits are
    printed in this photo's OCR text (the D-093 second reading, which /scan has
    and /check-photo doesn't; no extra call). A check digit catches one wrong
    digit, not several: a small, blurry photo read as 0961676012608 for
    8901058018608 and passed check(). A code neither confirms is
    "barcode_unsure", never a guess. The second read runs only when the first
    found a code the OCR text doesn't already show. two_reads=False is the
    rule before, kept for tools/barcode_reads.py to measure against.
    """
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.draft("L", (2400, 2400))                # JPEG: decode near the size needed, fast
        im = im.convert("L")
        im.thumbnail((2400, 2400))
        good, bad = _read_once(im)
        if good and two_reads:
            printed = codes_in_text(ocr_text) if ocr_text else []
            again = []
            if any(c not in printed for c in good):
                again, _ = _read_once(im.resize((round(im.width * SECOND_READ), round(im.height * SECOND_READ)),
                                                Image.BILINEAR))
            unsure = [c for c in good if c not in again and c not in printed]
            good = [c for c in good if c in again or c in printed]
            bad = ["barcode_unsure"] * bool(unsure) + bad
    except Exception:                              # noqa: BLE001 - undecodable image or no library: nothing read
        return [], []
    return good, bad


def _read_once(im):
    """One zxing-cpp pass over a greyscale image: (codes that pass check(), reasons for ones that don't)."""
    import zxingcpp
    formats = [zxingcpp.BarcodeFormat.EAN13, zxingcpp.BarcodeFormat.EAN8,
               zxingcpp.BarcodeFormat.UPCA, zxingcpp.BarcodeFormat.UPCE]
    good, bad = [], []
    for r in zxingcpp.read_barcodes(im, formats=formats):
        raw = r.text
        if r.format == zxingcpp.BarcodeFormat.UPCE:
            raw = upce_to_upca(raw)
        code, reason = check(raw)
        if code and code not in good:
            good.append(code)
        elif reason:
            bad.append(reason)
    return good, bad


def photo_code(photos, ocr_text=None):
    """
    D-144: the one barcode a scan's own photos show, for a scan sent without one.
    photos: [(role, bytes)]; ocr_text: the back photo's OCR text. A code counts by
    read_from_photo()'s rule (the OCR text only for the back, the photo it read).
    {"code": the code or None, "status": found | none | unsure | several,
     "photo_codes": {role: [codes]}, "unsure": [roles]}.
    """
    read, unsure = {}, []
    for role, data in photos:
        codes, why = read_from_photo(data, ocr_text=ocr_text if role == "back" else None)
        if codes:
            read[role] = codes
        if "barcode_unsure" in why:
            unsure.append(role)
    shown = sorted({c for codes in read.values() for c in codes})
    status = "found" if len(shown) == 1 else "several" if shown else "unsure" if unsure else "none"
    return {"code": shown[0] if len(shown) == 1 else None, "status": status, "photo_codes": read,
            "unsure": unsure}
