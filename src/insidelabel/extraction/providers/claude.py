"""
Inside Label - Claude as a second label reader (D-192), behind INSIDELABEL_READER=claude.

Off by default: Gemini reads every label until the advisor's gold-set run shows Claude
reads Indian labels as well (ingredient F1 >= 0.95, INS F1 1.000, no verdict flip, no
allergen miss) and Sushil says yes. Why it exists: Gemini 3.6 Flash costs $0.75 / $3.75
per million tokens (doubling on 1 Jan 2027); claude-haiku-5-5 costs $0.10 / $0.50, and
has no RECITATION guard (D-172).

Only the read changes. The same prompt (prompt.py, PROMPT_VERSION unchanged), the same
photos in the same order, and an answer in the same shape (answer_shape.py), so
parse_vision_json(), harden(), the D-093 cross-check, D-191 and the rules run on it
exactly as on Gemini's. AI reads, rules judge (D-004) either way.

Errors map onto gemini.py's classes, so /scan treats a Claude failure as a Gemini one:
busy / rate limited / 5xx / timeout = VisionUnavailable (retried by _with_retries), our
setup = VisionConfigError (alarm), a refusal = VisionBlocked("refusal") (D-172's
refusal screen and replay marker).
"""

import base64
import os
import time

from insidelabel.extraction.providers import answer_shape, cloud_vision
from insidelabel.extraction.providers.gemini import (
    USAGE_KEYS,
    VisionBlocked,
    VisionConfigError,
    VisionError,
    VisionUnavailable,
)
from insidelabel.extraction.providers.prompt import VISION_PROMPT, VISION_RESPONSE_SCHEMA

try:
    import anthropic
    _HAVE_SDK = True
except ImportError:                                              # pragma: no cover
    _HAVE_SDK = False

DEFAULT_MODEL = "claude-haiku-5-5"

# Today's answers are about 1,100 tokens (D-193 records); room for the longest label
# without inviting a runaway answer. A cut-off answer fails to parse, as a cut-off
# Gemini answer does.
MAX_TOKENS = 16000

# The same bound as Gemini's SDK_TIMEOUT_MS. The SDK's own retries are off: gemini's
# _with_retries is the one retry loop, so both readers back off the same way.
TIMEOUT_S = 120

# Claude's image limits (Anthropic vision docs, read 2026-10-14): 10 MB per image as
# base64 (about 7.5 MB of file), 8000 px a side; Haiku 5.5 itself shrinks past 2576 px on
# the long edge, so shrinking to that loses nothing it would have seen. The app sends
# JPEGs of about 1600 px, which go as they are.
MAX_PHOTO_BYTES = 7_000_000
MAX_SIDE = 8000
LONG_EDGE = 2576

# The photo types Claude takes. HEIC/HEIF isn't one, and the server has no HEIC decoder
# to convert it, so such a scan is read by Gemini (gemini._read_text, "fallback_why": "heic").
MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Claude's statuses that are about a busy moment, not the request.
RETRYABLE_STATUS = {408, 409, 429}

CLAUDE_SCHEMA = answer_shape.to_claude_schema(VISION_RESPONSE_SCHEMA)


def model():
    """claude-haiku-5-5, or INSIDELABEL_CLAUDE_MODEL when set (a later model is one line)."""
    return os.environ.get("INSIDELABEL_CLAUDE_MODEL", "").strip() or DEFAULT_MODEL


def readable(images):
    """True when Claude takes every photo's type."""
    return all(mime in MIME_TYPES for _d, mime, _r in images)


def _photo(data, mime):
    small = cloud_vision.shrink(data, max_bytes=MAX_PHOTO_BYTES, long_edge=LONG_EDGE, max_side=MAX_SIDE)
    return small, (mime if small is data else "image/jpeg")


def build_request(images, model_name=None):
    """The Messages API request: the prompt, then the photos in the order sent (as Gemini's)."""
    content = [{"type": "text", "text": VISION_PROMPT}]
    for data, mime, _role in images:
        data, mime = _photo(data, mime)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mime, "data": base64.standard_b64encode(data).decode("ascii")}})
    return {
        "model": model_name or model(),
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": content}],
        # Thinking off, for speed (allowed on Haiku 5.5 at its default effort). Gemini's
        # INSIDELABEL_THINKING_LEVEL and INSIDELABEL_MEDIA_RESOLUTION don't apply here.
        "thinking": {"type": "disabled"},
        "output_config": {"format": {"type": "json_schema", "schema": CLAUDE_SCHEMA}},
    }


def _fill_usage(usage, msg, model_name, t0):
    """D-193's usage record, Claude's way: thinking_tokens is null (thinking is off)."""
    if usage is None:
        return
    u = getattr(msg, "usage", None)
    i, o = getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)
    usage.clear()
    usage.update({k: None for k in USAGE_KEYS})
    usage.update({"input_tokens": i, "output_tokens": o,
                  "total_tokens": (i or 0) + (o or 0) if i is not None or o is not None else None,
                  "model": model_name, "ms": int((time.monotonic() - t0) * 1000)})


def _client(api_key):
    return anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=TIMEOUT_S)


def _map_error(e):
    """An SDK exception as gemini.py's VisionError classes."""
    if isinstance(e, anthropic.APIConnectionError):                # includes APITimeoutError
        return VisionUnavailable(f"Claude unavailable: {type(e).__name__}: {e}")
    if isinstance(e, anthropic.APIStatusError):
        status = e.status_code
        if status in RETRYABLE_STATUS or status >= 500:            # 529 overloaded included
            return VisionUnavailable(f"Claude unavailable ({status}): {type(e).__name__}: {e}")
        # 400 bad request or credit too low, 401 key, 403 permission, 404 model, 413, 422.
        err = VisionConfigError(f"Claude setup problem ({status}): {type(e).__name__}: {e}")
        err.status = status
        return err
    return VisionError(f"Claude call failed: {type(e).__name__}: {e}")


def call_claude(images, api_key=None, usage=None, client=None):
    """
    One answer's text for the label photos. usage: the caller's dict, filled with this
    call's tokens (D-193). client: a stand-in for tests; None makes the real one.
    """
    t0 = time.monotonic()
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if client is None:
        if not api_key:
            raise VisionConfigError("ANTHROPIC_API_KEY is not set.")
        if not _HAVE_SDK:                                          # pragma: no cover
            raise VisionConfigError("The anthropic package is not installed.")
        client = _client(api_key)
    request = build_request(images)
    try:
        msg = client.messages.create(**request)
    except VisionError:
        raise
    except Exception as e:                                         # noqa: BLE001
        if _HAVE_SDK and isinstance(e, anthropic.AnthropicError):
            raise _map_error(e) from e
        raise VisionError(f"Claude call failed: {type(e).__name__}: {e}") from e
    _fill_usage(usage, msg, request["model"], t0)

    stop = getattr(msg, "stop_reason", None)
    if stop == "refusal":
        details = getattr(msg, "stop_details", None)
        raise VisionBlocked("refusal", f"Claude declined to answer: {getattr(details, 'category', None)}")
    text = "".join(getattr(b, "text", "") for b in (getattr(msg, "content", None) or [])
                   if getattr(b, "type", None) == "text")
    if not text:
        raise VisionError(f"Empty response. Stop reason: {stop}")
    # stop_reason "max_tokens": the cut-off text goes on and fails to parse, keeping the raw
    # answer with the error (D-092), as a cut-off Gemini answer does.
    return text
