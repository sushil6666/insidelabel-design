"""
Inside Label - Gemini Flash vision client.

Calls the model with the prompt in prompt.py, parses strictly, and then
DISTRUSTS the result in the specific ways a vision model tends to be wrong.

The hardening is the point of this file. A vision model that says
`front_status: "read"` for an image you never sent, or `ingredients_status:
"read"` alongside an empty array, is not a rare failure - it is the normal
consequence of a schema that requires a value for every field. Every override
below is a case where the CLIENT knows something the model cannot, or where the
model contradicted itself.
"""

import base64
import json
import logging
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request

from insidelabel.extraction.providers import answer_shape
from insidelabel.extraction.providers.prompt import (
    GENERATION_CONFIG,
    MODEL,
    THINKING_LEVEL,
    VISION_PROMPT,
    VISION_RESPONSE_SCHEMA,
)

# D-193: each call fills the caller's own `usage` dict with real token counts
# instead of a guess at cost (image token counts vary with resolution, and
# thinking tokens are invisible until you look). It was a module global
# (LAST_USAGE), which two scans on the threadpool overwrote, and was never stored.
USAGE_KEYS = ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens")

log = logging.getLogger("insidelabel.reader")

# D-193 (Sushil, 2026-10-10): the read's settings, each a switch in
# /etc/insidelabel/settings.env and all off by default, until the advisor's gold-set
# run shows a setting faster with no loss in reading.
# Levels: Google's thinking table (ai.google.dev/gemini-api/docs/thinking, read
# 2026-10-10) lists gemini-3.6-flash with minimal, low, medium, high (default medium).
# Media resolution (ai.google.dev/gemini-api/docs/media-resolution): low 280, medium
# 560, high 1120 tokens per image on Gemini 3; unset is the API's default (1120).
THINKING_LEVELS = ("minimal", "low", "medium", "high")
MEDIA_RESOLUTIONS = ("low", "medium", "high")


# D-192 (Sushil, 2026-10-14): which model reads the label. One switch in
# /etc/insidelabel/settings.env, INSIDELABEL_READER=claude; unset or anything else is
# Gemini. Off until the gold set says Claude reads as well and Sushil says yes.
READERS = ("gemini", "claude")


def reader():
    """D-192: "claude" only for INSIDELABEL_READER=claude (any case, spaces trimmed), else "gemini"."""
    return "claude" if os.environ.get("INSIDELABEL_READER", "").strip().lower() == "claude" else "gemini"


def gemini_settings():
    """D-193: Gemini's read settings from the environment, whichever reader is switched on."""
    level = os.environ.get("INSIDELABEL_THINKING_LEVEL", "").strip().lower()
    media = os.environ.get("INSIDELABEL_MEDIA_RESOLUTION", "").strip().lower()
    return {"reader": "gemini", "model": MODEL,
            "thinking_level": level if level in THINKING_LEVELS else THINKING_LEVEL,
            "media_resolution": media if media in MEDIA_RESOLUTIONS else None,
            "split_front": os.environ.get("INSIDELABEL_READ_SPLIT_FRONT", "").strip().lower() == "on"}


def read_settings():
    """
    D-193: how this read is made, from the environment at call time: the reader (D-192),
    the model, INSIDELABEL_THINKING_LEVEL (unset: prompt.THINKING_LEVEL, "low"),
    INSIDELABEL_MEDIA_RESOLUTION (unset: None, the API's default) and
    INSIDELABEL_READ_SPLIT_FRONT=on (back and front in two calls at once). A value
    the API doesn't take is ignored, so a typo in settings.env reads as today.
    Stored with every scan (D-092) and every batch prediction.
    D-192: with the Claude reader the three D-193 switches are Gemini's only: thinking
    level and image detail are null and the split is off (one call, back and front
    together), so nobody reads them as applied.
    """
    if reader() == "claude":
        from insidelabel.extraction.providers import claude
        return {"reader": "claude", "model": claude.model(), "thinking_level": None,
                "media_resolution": None, "split_front": False}
    return gemini_settings()


def _fill_usage(usage, counts, settings, t0):
    """D-193: one call's tokens and settings into the caller's dict."""
    if usage is None:
        return
    usage.clear()
    usage.update({k: counts.get(k) for k in USAGE_KEYS})
    usage.update({"model": settings["model"], "thinking_level": settings["thinking_level"],
                  "media_resolution": settings["media_resolution"],
                  "ms": int((time.monotonic() - t0) * 1000)})

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Google is migrating Gemini credentials from the legacy AIza format to the new
# AQ. "Authentication Key" format, and AI Studio now issues only AQ. keys.
# Hand-rolled REST with an x-goog-api-key header is exactly the pattern that is
# widely reported to fail on AQ. keys with 401 ACCESS_TOKEN_TYPE_UNSUPPORTED,
# so the SDK is the default path here and raw REST is only a fallback for
# environments that cannot install it.
try:
    from google import genai
    from google.genai import types as genai_types
    _HAVE_SDK = True
except ImportError:                                              # pragma: no cover
    _HAVE_SDK = False

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

# D-103: Gemini must answer image_content (the schema requires it), but model
# answers recorded before it existed (tests, saved regressions, predictions/)
# don't have it, and still have to parse. Missing = unknown = no image rule.
# D-133: "nutrition" too. Answers recorded before it (every scan before D-133)
# have no table and must still parse and replay the same (D-092).
# D-139: "pack_statements" and "licences" too; without them a pack is ordinary food.
# D-139 phase 2: "composition" too (a supplement's amounts per tablet or serving).
OPTIONAL_KEYS = {"image_content", "nutrition", "pack_statements", "licences", "composition"}
REQUIRED_KEYS = set(VISION_RESPONSE_SCHEMA["required"]) - OPTIONAL_KEYS
_IMAGE_CONTENT = {"food_pack", "screen", "not_food", "not_provided"}
# D-108: words that state a difference between the two faces, in the model's evidence.
_DIFFERENCE_CUES = ("different", " vs ", " vs. ", "versus", "does not match", "doesn't match",
                    "do not match", "not the same", "another product", "unrelated", "two products",
                    "two different")

_FRONT_STATUS = {"read", "not_provided", "unreadable"}
_BACK_STATUS = {"read", "not_provided", "unreadable"}
_ING_STATUS = {"read", "partial", "not_found", "unreadable"}
_NUTRITION_STATUS = {"read", "partial", "not_found", "unreadable"}


class VisionError(RuntimeError):
    """Terminal. Retrying will not help - bad auth, bad schema, unparseable output."""
    retryable = False


class VisionUnavailable(VisionError):
    """
    Transient upstream failure: model overloaded, rate limited, gateway error.
    The request was fine; the service was not. Worth retrying, and worth telling
    the caller that so a user is not shown a label-reading failure for what is
    really a queue.
    """
    retryable = True


class VisionConfigError(VisionError):
    """
    Our setup, not the label and not a busy moment: no key, key rejected (401/
    403), prepaid credit used up (402), model not available to this key (404).
    Nothing a retry or the user can fix, so the API raises an alarm for the
    developer (a 'server' problem report) instead of a generic failure. Seen for
    real on 2026-09-25: "Your prepayment credits are depleted" (402).
    """
    retryable = False


class VisionBlocked(VisionError):
    """
    D-172: the model answered with nothing because one of Google's guards stopped it, named
    in the finish reason. Seen for real on 2026-10-07 (problem report #7, a Britannia pack):
    RECITATION, the guard against reciting published text, on a word-for-word transcription
    of a widely printed label. Not the photo and not our setup: a person can still read it.
    `reason` is the finish reason in lower case ("recitation", "safety", ...).
    """
    retryable = False

    def __init__(self, reason, message=None):
        self.reason = reason
        super().__init__(message or f"Gemini blocked its answer: finish reason {reason.upper()}")


# The finish reasons that mean a guard stopped the answer (google-genai types.FinishReason).
BLOCK_REASONS = {"RECITATION", "SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
# RECITATION is partly random: the same photos often pass on another try. Two more tries, at
# once, with the request unchanged: Gemini 3.x ignores temperature (prompt.py) and a seed
# isn't documented to work on 3.6, so the default sampling is what varies the answer.
RECITATION_RETRIES = 2


def _block_reason(candidates):
    """The guard that stopped an empty answer, upper case, or None."""
    for c in candidates or []:
        fr = c.get("finishReason") if isinstance(c, dict) else getattr(c, "finish_reason", None)
        name = getattr(fr, "name", None) or (str(fr).rsplit(".", 1)[-1] if fr is not None else None)
        if name and name.upper() in BLOCK_REASONS:
            return name.upper()
    return None


# D-172, D-092: a blocked answer is stored as this marker in scans.model_raw, so the scan
# replays to the same refusal. blocked_reason() is the one place that recognises it: every
# reader of model_raw either passes it back to /scan as a replay or asks this first.
def blocked_marker(reason):
    return json.dumps({"_blocked": reason.upper()})


def blocked_reason(text):
    """The lower-case reason when `text` is a D-172 blocked marker, else None."""
    if not text or "_blocked" not in text:
        return None
    try:
        obj = json.loads(text)
    except (TypeError, ValueError):
        return None
    if isinstance(obj, dict) and set(obj) == {"_blocked"} and isinstance(obj["_blocked"], str):
        return obj["_blocked"].lower()
    return None


CONFIG_STATUS = {401, 402, 403, 404}


def _config_problem(status, text):
    return status in CONFIG_STATUS or (status == 400 and "api key" in text.lower())


# Statuses where the request itself was acceptable and the service was not.
# 400/401/403/404 are excluded on purpose: retrying a malformed request or a
# rejected credential just burns the user's time and Google's quota.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

MAX_ATTEMPTS = 4
BASE_BACKOFF = 1.5      # seconds; doubles each attempt
MAX_BACKOFF = 20.0


def _status_of(exc):
    """Pull an HTTP status off an SDK exception without depending on its class."""
    for attr in ("code", "status_code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    m = re.search(r"\b(4\d{2}|5\d{2})\b", str(exc))
    return int(m.group(1)) if m else None


def _with_retries(fn, on_attempt=None):
    """
    Retry transient upstream failures with exponential backoff and jitter.

    Jitter matters more than it looks: without it, every client that got a 503
    from the same demand spike retries in lockstep and recreates the spike.
    """
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn()
        except VisionUnavailable as e:
            last = e
            if attempt == MAX_ATTEMPTS:
                break
            delay = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (attempt - 1)))
            delay *= 0.5 + random.random()          # 50-150% jitter
            if on_attempt:
                on_attempt(attempt, delay, e)
            time.sleep(delay)
    raise VisionUnavailable(
        f"Upstream unavailable after {MAX_ATTEMPTS} attempts. Last error: {last}"
    )


# ---------------------------------------------------------------------------
def build_request(images, settings=None):
    """
    images: list of (bytes, mime_type, role_hint) where role_hint is
            "front" | "back" | "unknown". The hint is NOT sent to the model -
            the prompt tells it to work roles out from content. The hint is
            kept client-side to check the model's answer against what we sent.
    """
    parts = [{"text": VISION_PROMPT}]
    for data, mime, _role in images:
        parts.append({
            "inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(data).decode("ascii"),
            }
        })

    config = dict(GENERATION_CONFIG)
    config["response_schema"] = VISION_RESPONSE_SCHEMA
    # D-193: only a switched setting is sent, so this fallback reads as before by default.
    settings = settings or read_settings()
    if settings["thinking_level"] != THINKING_LEVEL:
        config["thinkingConfig"] = {"thinkingLevel": settings["thinking_level"].upper()}
    if settings["media_resolution"]:
        config["mediaResolution"] = "MEDIA_RESOLUTION_" + settings["media_resolution"].upper()

    return {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": config,
    }


# A vision call with two images can legitimately take 20-40s. Without a bound
# it can also take forever: the SDK path had no timeout, so a hung connection
# looked identical to a slow model, and a batch run would sit on one label
# indefinitely with no output.
SDK_TIMEOUT_MS = 120_000


def call_gemini_sdk(images, api_key=None, usage=None, settings=None):
    """Preferred path. The SDK handles both AIza and AQ. credential types."""
    return call_gemini_json(VISION_PROMPT, images, VISION_RESPONSE_SCHEMA, api_key=api_key,
                            usage=usage, settings=settings)


def call_gemini_json(prompt_text, images, schema, api_key=None, usage=None, settings=None):
    """
    One JSON answer from Gemini for a prompt and some photos, with the same
    client, timeout and error mapping as the label reader: a busy model raises
    VisionUnavailable (retry it), a key or credit problem VisionConfigError
    (a setup alarm, not a retry). The review drafter (D-117) uses it too.
    usage: a dict of the caller's, filled with this call's tokens and settings (D-193).
    settings: read_settings()'s answer; None reads it now.
    """
    settings = settings or read_settings()
    t0 = time.monotonic()
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise VisionConfigError("GEMINI_API_KEY is not set.")

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=SDK_TIMEOUT_MS),
        )
    except Exception:                                            # noqa: BLE001
        # Older SDK versions may not accept http_options; an unbounded client
        # is worse than none, but better than not running at all.
        client = genai.Client(api_key=api_key)
    parts = [genai_types.Part.from_text(text=prompt_text)]
    for data, mime, _role in images:
        parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime))

    try:
        cfg_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema,
        }
        # No tools are ever passed, so automatic function calling has nothing to do;
        # switching it off also stops the SDK's warning in every server log line.
        try:
            cfg_kwargs["automatic_function_calling"] = genai_types.AutomaticFunctionCallingConfig(disable=True)
        except Exception:                                        # noqa: BLE001 - older SDKs
            pass
        # D-193: the image detail setting, only when switched on.
        if settings["media_resolution"]:
            cfg_kwargs["media_resolution"] = getattr(
                genai_types.MediaResolution, "MEDIA_RESOLUTION_" + settings["media_resolution"].upper())
        # thinking_level is 3.x-only; older SDKs and models reject it.
        try:
            cfg = genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level=settings["thinking_level"]),
                **cfg_kwargs)
        except Exception:                                        # noqa: BLE001
            cfg = genai_types.GenerateContentConfig(**cfg_kwargs)

        resp = client.models.generate_content(model=MODEL, contents=parts, config=cfg)
    except Exception as e:                                       # noqa: BLE001
        status = _status_of(e)
        if status in RETRYABLE_STATUS:
            raise VisionUnavailable(
                f"Gemini unavailable ({status}): {type(e).__name__}: {e}"
            ) from e
        if _config_problem(status, str(e)):
            err = VisionConfigError(f"Gemini setup problem ({status}): {type(e).__name__}: {e}")
            err.status = status
            raise err from e
        raise VisionError(f"Gemini call failed: {type(e).__name__}: {e}") from e

    um = getattr(resp, "usage_metadata", None)
    _fill_usage(usage, {
        "input_tokens": getattr(um, "prompt_token_count", None),
        "output_tokens": getattr(um, "candidates_token_count", None),
        "thinking_tokens": getattr(um, "thoughts_token_count", None),
        "total_tokens": getattr(um, "total_token_count", None),
    }, settings, t0)

    if not getattr(resp, "text", None):
        candidates = getattr(resp, "candidates", None)
        blocked = _block_reason(candidates)
        if blocked:
            raise VisionBlocked(blocked.lower(), f"Empty response. Finish reason: {candidates}")
        raise VisionError(f"Empty response. Finish reason: {candidates}")
    return resp.text


def call_gemini_rest(images, api_key=None, timeout=90, usage=None, settings=None):
    """
    Fallback only. Known to fail on AQ.-format keys with
    401 ACCESS_TOKEN_TYPE_UNSUPPORTED. Kept for environments where the SDK
    cannot be installed; if you get a 401 here, that is the reason.
    """
    settings = settings or read_settings()
    t0 = time.monotonic()
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise VisionConfigError("GEMINI_API_KEY is not set.")

    body = json.dumps(build_request(images, settings)).encode("utf-8")
    url = f"{API_BASE}/{MODEL}:generateContent"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code in RETRYABLE_STATUS:
            raise VisionUnavailable(f"Gemini unavailable ({e.code}): {detail}") from e
        if e.code == 401:
            raise VisionConfigError(
                "401 from the REST endpoint. If your key starts with 'AQ.', this "
                "is the known incompatibility between the new Authentication Key "
                "format and raw REST auth - install google-genai and use "
                f"call_gemini_sdk() instead. Server said: {detail}"
            ) from e
        if _config_problem(e.code, detail):
            err = VisionConfigError(f"Gemini setup problem ({e.code}): {detail}")
            err.status = e.code
            raise err from e
        raise VisionError(f"HTTP {e.code}: {detail}") from e

    um = (payload.get("usageMetadata") if isinstance(payload, dict) else None) or {}
    _fill_usage(usage, {"input_tokens": um.get("promptTokenCount"), "output_tokens": um.get("candidatesTokenCount"),
                        "thinking_tokens": um.get("thoughtsTokenCount"), "total_tokens": um.get("totalTokenCount")},
                settings, t0)
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        blocked = _block_reason(payload.get("candidates") if isinstance(payload, dict) else None)
        if blocked:
            raise VisionBlocked(blocked.lower(), f"Empty response. Finish reason: {blocked}") from e
        raise VisionError(f"Unexpected response envelope: {payload}") from e
    return text


# ---------------------------------------------------------------------------
def parse_vision_json(text):
    """Strict parse. Tolerates code fences only; everything else is an error."""
    cleaned = _FENCE.sub("", text).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise VisionError(f"Model did not return parseable JSON: {e}") from e
    if not isinstance(obj, dict):
        raise VisionError("Model returned JSON that is not an object.")
    # D-192: a Claude answer leaves out the fields it has nothing for (answer_shape.py);
    # they come back as Gemini's empty value. A Gemini answer comes out unchanged, so
    # this runs on every answer and a replay needs no reader.
    answer_shape.fill_back(obj)
    missing = REQUIRED_KEYS - set(obj)
    if missing:
        raise VisionError(f"Model omitted required keys: {sorted(missing)}")
    return obj


def _split_declaration(raw):
    """
    Split an ingredient declaration on TOP-LEVEL commas, keeping bracketed
    sub-lists attached to their parent. This is the split the model is asked to
    perform; doing it here too means a disagreement is detectable, and gives us
    a correct array to fall back on.
    """
    out, buf, depth = [], [], 0
    for ch in raw:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip().rstrip(".").strip()
    if tail:
        out.append(tail)
    return [e for e in (x.strip() for x in out) if e]


def _key(s):
    return " ".join(s.strip().rstrip(".").upper().split())


def _entries_missing_from_array(raw, array):
    """
    Entries present in the printed text but absent from the array.

    Containment, not equality. The guard exists to catch DROPPED content, and
    text sitting inside a larger array entry has not been dropped.

    Why this matters, from a real label: Patanjali Doodh prints
    "... Natural, Nature identical & Artificial Flavours (Milk & Vanilla), ..."
    There is a genuine top-level comma after "Natural", so _split_declaration
    yields two fragments - but the commas there separate ADJECTIVES describing
    one flavouring, not two ingredients. The model returned it correctly as a
    single entry; an equality check found neither fragment, declared two
    entries missing, and replaced an 11-entry array with a 12-entry one.

    A guard that overrides a correct answer is worse than no guard. Top-level
    commas do not reliably separate ingredients on Indian labels, so the split
    is treated as a lower bound on content, never as an authority on grouping.
    """
    joined = " ".join(_key(e) for e in array)
    return [e for e in _split_declaration(raw) if _key(e) not in joined]


# Manufacturer strings that identify a corporate group rather than a product.
# "The Coca-Cola Company" appears on the legal footer of Limca, Sprite, Thums
# Up and Maaza alike, so matching on it proves nothing about whether two faces
# came from the same pack.
_GROUP_LEVEL_MFR = (
    "the coca-cola company", "coca-cola company", "pepsico", "pepsico inc",
    "nestle s.a.", "unilever", "hindustan unilever", "mondelez international",
    "itc limited", "britannia industries", "parle products",
)


def _clean(x):
    return " ".join((x or "").strip().lower().split())


def _verified_anchors(v):
    """
    Identity anchors the code can check for itself, comparing the two faces.

    Only equality of a specific identifier counts. A shared product category,
    a shared parent company, or the fact that two images were uploaded together
    are not anchors - they are true of many different products at once.
    """
    fi, bi = v.get("front_identity") or {}, v.get("back_identity") or {}
    ing = {_clean(x) for x in (v.get("ingredients") or [])}

    anchors = []
    for field in ("brand", "name"):
        a, b = _clean(fi.get(field)), _clean(bi.get(field))
        if not (a and b and (a == b or a in b or b in a)):
            continue
        # A product NAME that is also an ingredient is not an identity anchor.
        #
        # Observed: the model returned product name "Carbonated Water" -- the
        # first ingredient -- for a pack whose back shows no product name at
        # all. OCR corroboration does NOT catch this, because that string IS on
        # the back label; it is there as an ingredient rather than as a name.
        # Corroboration answers "does this text appear on the face", which is a
        # weaker question than "is this the product's name".
        #
        # Scoped to name on purpose: brand names rarely collide with ingredient
        # names, descriptive product names collide constantly.
        if field == "name" and any(a == i or a in i for i in ing):
            anchors.append(f"(rejected) name {a!r} is also an ingredient, not an identifier")
            continue
        anchors.append(f"{field} matches on both faces: {a!r}")
    fm, bm = _clean(fi.get("manufacturer")), _clean(bi.get("manufacturer"))
    if fm and bm and fm == bm:
        if fm in _GROUP_LEVEL_MFR:
            anchors.append(f"(rejected) manufacturer {fm!r} is a corporate group, not a product identifier")
        else:
            anchors.append(f"manufacturer matches on both faces: {fm!r}")
    return [a for a in anchors if not a.startswith("(rejected)")]


# Front-of-pack text that is never a marketing claim, however it is phrased.
# The prompt already excludes these; the model returns them anyway, so the
# filter lives here. Prompt rules have not proved reliable in this pipeline -
# code-side enforcement has.
_NON_CLAIM_PATTERNS = [
    re.compile(r"^\s*(net\s+(qty|quantity|wt|weight)|mrp|m\.r\.p)", re.I),
    re.compile(r"^\s*(fssai|lic\.?\s*no|licence|license)", re.I),
    re.compile(r"^\s*(batch|mfg|exp|best\s+before|use\s+by)", re.I),
    re.compile(r"^[\d\s.,]+\s*(ml|l|g|kg|gm|litre|liter)\.?$", re.I),
    re.compile(r"^\s*(veg|non-?veg)\s*$", re.I),
    re.compile(r"^\s*serving\s+suggestion", re.I),
    # Prices. A retailer sticker is not manufacturer text at all, and a bare
    # amount carries no claim to check. Observed reaching front_claims as
    # ["₹100", "₹90"] from a discount sticker on a photographed bottle.
    re.compile(r"^[\s]*(?:rs\.?|inr|₹|\$|€|£)?[\s]*[\d,]+(?:\.\d+)?[\s]*/?-?[\s]*$", re.I),
    re.compile(r"(?:^|\s)(?:rs\.?|inr|₹)\s*[\d,]+", re.I),
    re.compile(r"\b(incl\.?\s+of\s+all\s+taxes|inclusive\s+of\s+all\s+taxes)\b", re.I),
    re.compile(r"\b(see\s+neck|see\s+cap|see\s+bottom|date\s+of\s+manufacture)\b", re.I),
    re.compile(r"^\s*made\s+in\s+\w+\.?\s*$", re.I),
    re.compile(r"\bstore\s+in\s+a\s+cool\b", re.I),
]

# A claim is an assertion, and an assertion needs words. Anything with no
# letters at all - prices, codes, bare numbers - cannot be a marketing claim
# whatever else it is. This is the backstop for price formats the patterns
# above do not anticipate.
_HAS_LETTERS = re.compile(r"[a-zA-Z]")


def _filter_front_claims(v):
    """
    Drop product identity and mandatory label text from front_claims.

    Observed: the model returned ["Lime 'N' Lemon"] as a claim, which is the
    product's own name. Harmless against the current four claim rules, but a
    claim extractor that includes the product name will generate noise on any
    pack that carries real claims, and each false claim is something the app
    would quote back to a user as a marketing assertion.

    Deliberately conservative: only EXACT matches against the product's own
    identity strings are dropped. A longer claim that happens to contain the
    brand ("Limca Zero Sugar") is a real claim and is kept.
    """
    ident = set()
    for src in (v.get("product") or {}, v.get("front_identity") or {}):
        for key in ("brand", "name", "variant"):
            val = _clean(src.get(key))
            if val:
                ident.add(val)

    kept, dropped = [], []
    for c in v.get("front_claims") or []:
        n = _clean(c)
        if not n:
            continue
        if (n in ident
                or not _HAS_LETTERS.search(c)
                or any(p.search(c) for p in _NON_CLAIM_PATTERNS)):
            dropped.append(c)
        else:
            kept.append(c)
    return kept, dropped


def harden(vision, sent_front, sent_back):
    """
    Correct the model's self-report against what the client actually knows,
    and against the model's own internal contradictions.

    Returns (vision, corrections) where corrections is a list of strings
    describing every override applied. Corrections are surfaced in the /scan
    response - a silent override is just a different kind of unearned
    confidence.
    """
    corrections = []
    v = dict(vision)

    # 1. Enum hygiene. An out-of-vocabulary status is treated as unreadable,
    #    never as "read".
    if v.get("front_status") not in _FRONT_STATUS:
        corrections.append(f"front_status {v.get('front_status')!r} invalid -> unreadable")
        v["front_status"] = "unreadable"
    if v.get("back_status") not in _BACK_STATUS:
        corrections.append(f"back_status {v.get('back_status')!r} invalid -> unreadable")
        v["back_status"] = "unreadable"
    if v.get("ingredients_status") not in _ING_STATUS:
        corrections.append(f"ingredients_status {v.get('ingredients_status')!r} invalid -> unreadable")
        v["ingredients_status"] = "unreadable"

    # 1b. What each image shows (D-103). Out-of-vocabulary is "unknown", which
    #     no rule acts on: a garbled answer must not refuse a real pack.
    if isinstance(v.get("image_content"), dict):
        ic = dict(v["image_content"])
        if sent_back != sent_front:
            # One image. The model isn't told which role we gave it (build_request
            # sends no hints), so it may describe "the image" under the other role:
            # measured 2026-09-26, a dbt screenshot sent as the back came back
            # {"back": "not_provided", "front": "not_food"}. Its description of
            # the only image is what counts, whichever key it used.
            role, other = ("back", "front") if sent_back else ("front", "back")
            said = [ic.get(k) for k in (role, other) if ic.get(k) in _IMAGE_CONTENT - {"not_provided"}]
            if said and ic.get(role) != said[0]:
                corrections.append(f"image_content for the only image read from {other}: {said[0]}")
                ic[role] = said[0]
        for role, sent in (("back", sent_back), ("front", sent_front)):
            if not sent:
                ic[role] = "not_provided"
            elif ic.get(role) not in _IMAGE_CONTENT - {"not_provided"}:
                corrections.append(f"image_content.{role} {ic.get(role)!r} invalid -> unknown")
                ic[role] = "unknown"
        v["image_content"] = ic

    # 1c. The nutrition table (D-133). The model only copies it; lenses/nutrition.py
    #     judges it. Here only its shape: an unknown status is "unreadable", never
    #     "read", and rows that aren't a list are no rows.
    if "nutrition" in v:
        n = v["nutrition"] if isinstance(v["nutrition"], dict) else {}
        n = dict(n)
        if n.get("status") not in _NUTRITION_STATUS:
            corrections.append(f"nutrition.status {n.get('status')!r} invalid -> unreadable")
            n["status"] = "unreadable"
        if not isinstance(n.get("rows"), list):
            n["rows"] = []
        v["nutrition"] = n

    # 1c'. The composition table (D-139). Copied only; lenses/nutra.py judges it.
    if "composition" in v:
        c = dict(v["composition"]) if isinstance(v["composition"], dict) else {}
        if c.get("status") not in _NUTRITION_STATUS:
            corrections.append(f"composition.status {c.get('status')!r} invalid -> unreadable")
            c["status"] = "unreadable"
        c["rows"] = [r for r in (c.get("rows") if isinstance(c.get("rows"), list) else [])
                     if isinstance(r, dict) and isinstance(r.get("name"), str) and r["name"].strip()]
        v["composition"] = c

    # 1d. Statements and licences (D-139). Copied text only; core/pack_kind.py
    #     judges them. Entries that aren't {text, face} are dropped, and a face
    #     that was never sent becomes the one that was: the words came from it.
    for key in ("pack_statements", "licences"):
        if key not in v:
            continue
        kept = []
        for e in v[key] if isinstance(v[key], list) else []:
            if not (isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"].strip()):
                continue
            face = e.get("face")
            if face not in ("front", "back") or (face == "front" and not sent_front) or (face == "back" and not sent_back):
                fixed = "back" if sent_back else "front"
                corrections.append(f"{key} face {face!r} -> {fixed}")
                face = fixed
            kept.append({"text": e["text"].strip(), "face": face})
        v[key] = kept

    # 2. The client knows how many images it sent. The model does not get to
    #    claim it read a face that was never transmitted.
    if not sent_front and v["front_status"] != "not_provided":
        corrections.append(f"no front image sent; front_status {v['front_status']} -> not_provided")
        v["front_status"] = "not_provided"
    if not sent_back and v["back_status"] != "not_provided":
        corrections.append(f"no back image sent; back_status {v['back_status']} -> not_provided")
        v["back_status"] = "not_provided"

    # 3. Claims cannot exist on a face that was not read. Dropping them is
    #    correct: a claim attributed to an unread front would be quoted back to
    #    the user as if it were printed on their pack.
    if v["front_status"] != "read" and v.get("front_claims"):
        corrections.append(
            f"discarded {len(v['front_claims'])} front_claims reported for a "
            f"front that was {v['front_status']}"
        )
        v["front_claims"] = []
        v["front_claim_footnotes"] = []

    # 3b. Cross-check the array against the printed lines and the model's own count.
    #
    #     History, because it matters for how much to trust this: over 10 runs
    #     of one clean label the model dropped "PRESERVATIVE (211)" from the
    #     array in 5. Asking for the declaration as one verbatim string was
    #     supposed to fix it; instead the string ALSO lost the item, in 5 of 5
    #     runs. The prose framing ("copy it as a sentence, to the final full
    #     stop") appears to have invited paraphrase, and paraphrase drops a
    #     short item wedged between two long bracketed ones.
    #
    #     So the source of truth is now layout, not prose: lines copied one at
    #     a time, plus a count the model must produce and reconcile. Copying a
    #     line is mechanical; summarising a line is not a thing you can do to
    #     one line at a time.
    #
    #     This is a HYPOTHESIS with a mechanism, not a proven fix. It is worth
    #     nothing until stability_check reports 211 present against gold over
    #     at least 10 runs. If it fails, the next move is not another prompt
    #     rewrite -- it is cropping the ingredient panel and sending that alone.
    lines = [l for l in (v.get("ingredient_lines") or []) if str(l).strip()]
    v["ingredient_lines"] = lines
    if lines:
        joined = " ".join(lines)
        # strip a leading INGREDIENTS: heading, which is not an ingredient
        joined = re.sub(r"(?i)^\s*ingredients\s*[:\-]\s*", "", joined.strip())
        from_lines = _split_declaration(joined)
        have = {_key(e) for e in (v.get("ingredients") or [])}
        missing = [e for e in from_lines if _key(e) not in have]
        if missing:
            corrections.append(
                f"array dropped {len(missing)} entry(s) present in "
                f"ingredient_lines: " + "; ".join(missing) + " - recovered from the lines"
            )
            v["ingredients"] = from_lines
    else:
        corrections.append("ingredient_lines empty; array could not be cross-checked")

    # The model's own count is NOT an independent check -- it counts what it
    # transcribed, not what is printed, so an omission stays consistent at
    # 5 == 5. Observed exactly that on a run that dropped a preservative.
    # Kept only because a mismatch still indicates a botched read; its silence
    # means nothing. Real omission detection lives in ocr_check.py. A mismatch it did
    # not resolve itself is a signal the read is incomplete, even when we have
    # nothing better to replace the array with.
    stated = v.get("ingredient_count")
    actual = len(v.get("ingredients") or [])
    if isinstance(stated, int) and stated > 0 and stated != actual:
        corrections.append(
            f"model counted {stated} ingredients but returned {actual}; "
            f"read is internally inconsistent"
        )
        v["_count_mismatch"] = {"stated": stated, "returned": actual}

    # 3c. Cross-face identity. The client overrides the model here whenever it
    #     can see a contradiction the model glossed over.
    #
    #     The failure this exists to stop: a Coca-Cola front and a Limca back
    #     produce a verdict built from Limca's ingredients, reported under
    #     Coca-Cola's name, with Coca-Cola's front claims tested against
    #     Limca's ingredient list. A false "claim contradicted" against a named
    #     brand is the most damaging output this system can emit, and nothing
    #     downstream would have caught it.
    pm = v.get("product_match") or {}
    status = pm.get("status")
    if status not in ("match", "mismatch", "indeterminate", "single_image"):
        corrections.append(f"product_match.status {status!r} invalid -> indeterminate")
        status = "indeterminate"

    n_faces = sum(1 for x in (sent_front, sent_back) if x)
    if n_faces < 2:
        if status != "single_image":
            corrections.append(f"only one face supplied; product_match {status} -> single_image")
        status = "single_image"
    else:
        fb = ((v.get("front_identity") or {}).get("brand") or "").strip().lower()
        bb = ((v.get("back_identity") or {}).get("brand") or "").strip().lower()

        # Do not force a product mismatch from model-only back-side brand text.
        # The back may show a parent company, manufacturer, or marketer rather
        # than the consumer-facing product brand.

        # "match" must rest on an anchor the CODE can verify, not on the
        # model's prose.
        anchors = _verified_anchors(v)
        v["verified_anchors"] = anchors

        accepted, rejected = [], []
        for e in pm.get("evidence") or []:
            low = e.lower()
            if any(w in low for w in ("brand", "product name", "name ", "fssai",
                                      "licence", "license", "manufactured by",
                                      "marketed by")):
                accepted.append(e)
            else:
                rejected.append(e)

        v["_evidence_rejected"] = rejected

        if rejected:
            corrections.append(
                "product_match evidence not counted (not an identity anchor): "
                + "; ".join(rejected)
            )

        if status == "match" and not anchors:
            corrections.append(
                "product_match status had no code-verifiable anchor "
                f"(model cited: {'; '.join(pm.get('evidence') or []) or 'nothing'})"
                " -> indeterminate"
            )
            status = "indeterminate"
        elif status == "mismatch":
            # D-108: a mismatch has no matching anchor by definition, so the rule
            # above used to turn every one into "indeterminate" (a Patanjali front
            # was then filed with a Maliban back). It is kept when nothing
            # checkable matches across the faces AND the model's own reason names
            # a difference: a real Limca bottle was once called "mismatch" on
            # evidence that described what matched.
            said = " ".join(pm.get("evidence") or []).lower()
            if anchors:
                corrections.append("product_match mismatch contradicted by a matching anchor "
                                   f"({'; '.join(anchors)}) -> indeterminate")
                status = "indeterminate"
            elif not any(cue in said for cue in _DIFFERENCE_CUES):
                corrections.append("product_match mismatch without a stated difference "
                                   f"(model cited: {'; '.join(pm.get('evidence') or []) or 'nothing'})"
                                   " -> indeterminate")
                status = "indeterminate"

    v["product_match"] = {
        "status": status,
        "evidence": pm.get("evidence") or [],
        "evidence_rejected": v.pop("_evidence_rejected", []),
        "verified_anchors": v.get("verified_anchors", []),
    }

    # Strip product identity and mandatory label text out of front_claims.
    kept_claims, dropped_claims = _filter_front_claims(v)
    if dropped_claims:
        corrections.append(
            f"dropped {len(dropped_claims)} non-claim(s) from front_claims: "
            + "; ".join(dropped_claims)
        )
    v["front_claims"] = kept_claims

    # 4. Self-contradiction: a status of "read" with nothing to show for it.
    ings = [i for i in (v.get("ingredients") or []) if str(i).strip()]
    v["ingredients"] = ings
    if v["ingredients_status"] in ("read", "partial") and not ings:
        corrections.append(
            f"ingredients_status was {v['ingredients_status']} but the array was "
            f"empty -> not_found"
        )
        v["ingredients_status"] = "not_found"

    # 5. Ingredients cannot come from a back that was not read.
    if v["back_status"] != "read" and v["ingredients_status"] in ("read", "partial"):
        corrections.append(
            f"back_status is {v['back_status']} but ingredients_status was "
            f"{v['ingredients_status']} -> unreadable"
        )
        v["ingredients_status"] = "unreadable"

    # 6. Confidence must be a number in range; anything else is treated as 0.0
    #    rather than assumed high.
    conf = v.get("confidence") or {}
    for k in ("ingredients", "front_claims", "product_identity"):
        try:
            c = float(conf.get(k))
            conf[k] = min(1.0, max(0.0, c))
        except (TypeError, ValueError):
            corrections.append(f"confidence.{k} invalid -> 0.0")
            conf[k] = 0.0
    v["confidence"] = conf

    return v, corrections


def analyze_images(images, api_key=None, raw_response=None, on_attempt=None):
    """
    Full path: call -> parse -> harden.

    raw_response lets you replay a recorded model response for testing without
    a network call or an API key.

    on_attempt(attempt, delay, error) is called before each backoff sleep, so a
    CLI can say what is happening instead of appearing to hang.
    """
    sent_front = any(r == "front" for _, _, r in images)
    sent_back = any(r == "back" for _, _, r in images)
    # An "unknown" role means the caller did not say; assume it could be either
    # so we do not wrongly force not_provided.
    if any(r == "unknown" for _, _, r in images):
        sent_front = sent_back = True

    usage, read = {}, {}
    try:
        text = _read_text(images, api_key, raw_response, on_attempt, usage, read)
    except VisionError as e:
        e.read = read                  # D-192: who tried, for the failed scan's timings
        raise
    # D-092: the raw answer is what makes a scan replayable, so it travels with
    # the result, and with the error when the answer can't be parsed.
    try:
        vision = parse_vision_json(text)
    except VisionError as e:
        e.raw_text = text
        e.read = read
        raise
    vision["_model"] = (usage or {}).get("model") or MODEL
    vision["_raw_text"] = text
    vision["_usage"] = dict(usage) if usage else None              # D-193; none on a replay
    vision["_read"] = read                                          # D-192: who read it
    return harden(vision, sent_front, sent_back)


def _read_text(images, api_key, raw_response, on_attempt, usage, read=None):
    """
    One answer's text: the recorded one on a replay, else a call with D-172's retries.
    read: the caller's dict, filled with who read it (D-192): {"reader": "claude"|"gemini"},
    plus {"fallback": "gemini", "fallback_why": "unavailable"|"heic"} when Claude was the
    reader switched on and Gemini read instead. Nothing on a replay.
    """
    if raw_response is not None:
        # D-172: a stored blocked answer replays to the same refusal; it is never parsed.
        reason = blocked_reason(raw_response)
        if reason:
            raise VisionBlocked(reason)
        return raw_response
    read = {} if read is None else read
    if reader() == "claude":
        return _read_with_claude(images, api_key, on_attempt, usage, read)
    read["reader"] = "gemini"
    return _read_with_gemini(images, api_key, on_attempt, usage)


def _read_with_claude(images, api_key, on_attempt, usage, read):
    """
    D-192: Claude reads, with the same retry helper as Gemini. A Claude read that is still
    busy after its retries is read once by Gemini when a Gemini key is set; so is a HEIC
    photo, which Claude doesn't take. A setup problem or a refusal never falls back: those
    are answers, not a busy moment. The scan is one read either way, counted once (the
    limiter counts the request, not the calls) and with one usage record: a failed Claude
    call records none.
    """
    from insidelabel.extraction.providers import claude
    read["reader"] = "claude"
    # api_key is a Gemini key (every caller's); Claude's comes from ANTHROPIC_API_KEY.
    gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not claude.readable(images) and gemini_key:
        read.update({"reader": "gemini", "fallback": "gemini", "fallback_why": "heic"})
        return _read_with_gemini(images, api_key, on_attempt, usage)
    try:
        return _with_retries(lambda: claude.call_claude(images, usage=usage), on_attempt=on_attempt)
    except VisionUnavailable:
        if not gemini_key:
            raise
        log.warning("Claude unavailable after its retries: reading with Gemini")
        read.update({"reader": "gemini", "fallback": "gemini", "fallback_why": "unavailable"})
        if usage is not None:
            usage.clear()
        return _read_with_gemini(images, api_key, on_attempt, usage)


def _read_with_gemini(images, api_key, on_attempt, usage):
    settings = gemini_settings()
    caller = (lambda: call_gemini_sdk(images, api_key, usage=usage, settings=settings)) if _HAVE_SDK else \
             (lambda: call_gemini_rest(images, api_key, usage=usage, settings=settings))
    for tries in range(1, RECITATION_RETRIES + 2):
        try:
            return _with_retries(caller, on_attempt=on_attempt)
        except VisionBlocked as e:
            # D-172: only RECITATION is worth another try; the others are about content.
            if e.reason != "recitation" or tries > RECITATION_RETRIES:
                raise
            if on_attempt:
                on_attempt(tries, 0.0, e)


# ---------------------------------------------------------------------------
# D-193 point 2: the back and the front in two calls at once
# ---------------------------------------------------------------------------
# INSIDELABEL_READ_SPLIT_FRONT=on. The result waits only for the back's call; the
# front's answer joins it when it is already in, and is otherwise kept for the
# reviewer and replay only. Same prompt (PROMPT_VERSION unchanged): it already reads
# "one or two photographs" and works each one's role out from its content.
SKIPPED_FRONT = "-"            # replay_front's value for "the front's answer wasn't joined"


class FrontRead:
    """The front photo's own call, started beside the back's, on a thread of its own."""

    def __init__(self, front_images, api_key=None, raw_response=None):
        self.raw, self.parsed, self.error, self.usage = None, None, None, {}
        self.done = threading.Event()
        self._args = (front_images, api_key, raw_response)
        threading.Thread(target=self._run, daemon=True, name="front-read").start()

    def _run(self):
        images, api_key, raw_response = self._args
        try:
            self.raw = _read_text(images, api_key, raw_response, None, self.usage)
            self.parsed = parse_vision_json(self.raw)
        except Exception as e:                                   # noqa: BLE001 - never costs the result
            self.error = f"{type(e).__name__}: {e}"[:500]
        finally:
            self.done.set()


def _brand_differs(back, front):
    a = _clean((back.get("back_identity") or {}).get("brand") or (back.get("product") or {}).get("brand"))
    b = _clean((front.get("front_identity") or {}).get("brand") or (front.get("product") or {}).get("brand"))
    return (a and b and not (a == b or a in b or b in a)) and (a, b)


def join_answers(back, front):
    """
    D-193: one answer in the single call's shape from the back's and the front's,
    before harden(), so every check after it runs as for one call. The back's call
    gives everything about the back; the front's gives its status, identity, claims
    and image content; the product's name fills its gaps from the front; pack
    statements and licences (D-139, D-190) come from both, each item keeping its
    face. product_match (D-108): neither call saw both faces, so code says it:
    "mismatch" only when both faces name a brand and they differ (stated as a
    difference, which harden() requires), else "match", which harden() keeps only
    with an anchor on both faces (_verified_anchors) and otherwise makes
    "indeterminate".
    """
    v = dict(back)
    ic = dict(back.get("image_content") or {})
    ic["front"] = (front.get("image_content") or {}).get("front", "not_provided")
    v["image_content"] = ic
    for k in ("front_status", "front_identity", "front_claims", "front_claim_footnotes"):
        v[k] = front.get(k, [] if k.startswith("front_claim") else None)
    product = dict(back.get("product") or {})
    for k, val in (front.get("product") or {}).items():
        if product.get(k) in (None, "") and val not in (None, ""):
            product[k] = val
    v["product"] = product
    for k in ("pack_statements", "licences"):
        both = list(back.get(k) or []) + list(front.get(k) or [])
        if both or k in back or k in front:
            v[k] = both
    differs = _brand_differs(back, front)
    v["product_match"] = (
        {"status": "mismatch", "evidence": [f"the front's brand {differs[1]!r} and the back's brand {differs[0]!r} are different"]}
        if differs else {"status": "match", "evidence": ["the brand and name read from each face"]})
    return v


def analyze_split(images, front_read, api_key=None, raw_response=None, on_attempt=None):
    """
    D-193: the back's call (or its recorded answer), joined with front_read's answer
    when it is already in. front_read: a FrontRead started by the caller, or None
    for "not joined" (a replay of a scan whose front came too late). Returns (vision,
    corrections) as analyze_images() does, with vision["_front_joined"].
    """
    back_images = [x for x in images if x[2] != "front"]
    usage, read = {}, {}
    try:
        text = _read_text(back_images, api_key, raw_response, on_attempt, usage, read)
    except VisionError as e:
        e.read = read                  # D-192: who tried, for the failed scan's timings
        raise
    try:
        back = parse_vision_json(text)
    except VisionError as e:
        e.raw_text = text
        e.read = read
        raise
    joined = front_read is not None and front_read.done.is_set() and front_read.parsed is not None
    vision = join_answers(back, front_read.parsed) if joined else back
    vision["_model"] = (usage or {}).get("model") or MODEL
    vision["_raw_text"] = text
    vision["_usage"] = dict(usage) if usage else None
    vision["_read"] = read
    vision["_front_joined"] = joined
    return harden(vision, sent_front=joined, sent_back=True)


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------
# Measured on a clean vector render of the Limca 2L label, 5 runs, temperature
# 0, identical prompt and images: PRESERVATIVE (211) appeared in 3 runs and
# vanished in 2. Score 76-88, grade A or B depending on the run. The model
# reported confidence 1.0 on every run, including both failures.
#
# So a single call is not a reading of the label; it is a sample from a
# distribution. And the model's own confidence carries no information about
# which sample you got. The only signal available is agreement across repeated
# reads.
#
# Union rather than majority vote, for ingredients specifically: the observed
# failure is DROPPING a printed additive, and no hallucinated additive has been
# seen yet. Under those conditions union maximises recall -- three runs recover
# a 60%-stable entry ~94% of the time, where a 2-of-3 majority recovers it only
# ~65%. Revisit this the moment the eval shows a hallucinated INS number, since
# union is exactly the wrong merge strategy against invention.
#
# Every merged entry carries its support count so the caller can tell a
# unanimous read from a 1-of-3 one, and so the UI can decline to show a verdict
# built on shaky ground.

def _norm_entry(e):
    return " ".join(e.strip().rstrip(".").upper().split())


def analyze_images_consensus(images, api_key=None, runs=3, on_attempt=None,
                             raw_responses=None):
    """
    Call the model `runs` times and merge. Returns (vision, meta).

    meta["support"]      entry -> how many runs contained it
    meta["unstable"]     entries seen in some runs but not all
    meta["unanimous"]    True when every run agreed exactly
    meta["runs"]         each individual result, for auditing

    raw_responses lets tests inject recorded outputs instead of calling out.
    """
    results = []
    if raw_responses is not None:
        for r in raw_responses:
            results.append(harden(parse_vision_json(r), True, True)[0])
    else:
        for _ in range(runs):
            v, _c = analyze_images(images, api_key=api_key, on_attempt=on_attempt)
            results.append(v)

    n = len(results)
    support, first_seen = {}, {}
    for v in results:
        for e in v.get("ingredients", []):
            k = _norm_entry(e)
            support[k] = support.get(k, 0) + 1
            first_seen.setdefault(k, e)

    # Preserve the ordering of the run with the most entries - label order
    # carries meaning (ingredients are listed by descending weight).
    richest = max(results, key=lambda v: len(v.get("ingredients", [])))
    ordered = [e for e in richest.get("ingredients", [])]
    have = {_norm_entry(e) for e in ordered}
    for k, orig in first_seen.items():
        if k not in have:
            ordered.append(orig)

    merged = dict(richest)
    merged["ingredients"] = ordered
    # Confidence is replaced with something measured rather than self-reported.
    merged["confidence"] = dict(merged.get("confidence", {}))
    merged["confidence"]["ingredients_agreement"] = (
        sum(1 for k in support if support[k] == n) / len(support) if support else 0.0
    )

    unstable = {k: c for k, c in support.items() if c < n}
    meta = {
        "runs": n,
        "support": support,
        "unstable": unstable,
        "unanimous": not unstable,
        "individual_runs": results,
    }
    return merged, meta
