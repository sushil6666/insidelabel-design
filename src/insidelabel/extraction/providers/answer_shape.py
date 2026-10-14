"""
Inside Label - one answer shape for two label readers (D-192).

The label's answer is defined once, as VISION_RESPONSE_SCHEMA in prompt.py, in the
dialect Gemini's response_schema takes. Claude's structured output takes a stricter
JSON Schema: every object needs additionalProperties false, and a schema may have at
most 16 fields with a union type and at most 24 optional fields (Anthropic's
structured-outputs page, read 2026-10-14). Today's schema has 23 `nullable` strings,
so ["string", "null"] for each is refused as "too complex".

So the converter makes a nullable field a plain field that is *not required*: Claude
leaves it out when nothing is printed, and fill_back() puts it back with exactly the
empty value Gemini's answer has for it (null, [] or "", whichever the schema says;
Sushil 2026-10-14; today all 23 are nullable strings, so null). The rest of the pipeline sees one shape.

Both functions walk the real schema, so a field added to prompt.py is carried to the
Claude read with no second edit here; tests/test_claude_reader.py fails if a new field
would take the schema past Claude's limits, before any scan does.
"""

from insidelabel.extraction.providers.prompt import VISION_RESPONSE_SCHEMA

# Anthropic's structured-output complexity limits (per request, all schemas together).
MAX_OPTIONAL = 24
MAX_UNION = 16

# Gemini schema keys with no JSON Schema meaning for Claude.
_DROP = {"nullable", "propertyOrdering"}


def to_claude_schema(schema=VISION_RESPONSE_SCHEMA):
    """The JSON Schema Claude's output_config.format takes, for a Gemini response_schema."""
    out = {}
    for k, v in schema.items():
        if k in _DROP:
            continue
        if k == "type":
            out[k] = str(v).lower()
        elif k == "properties":
            out[k] = {name: to_claude_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out[k] = to_claude_schema(v)
        elif k == "required":
            continue                                   # rebuilt below, without the nullable fields
        else:
            out[k] = v
    if out.get("type") == "object":
        props = schema.get("properties") or {}
        out["required"] = [n for n in schema.get("required", []) if not (props.get(n) or {}).get("nullable")]
        out["additionalProperties"] = False
    return out


def _empty(schema):
    """The value Gemini's answer has for this field when nothing is printed."""
    if schema.get("nullable"):
        return None
    t = str(schema.get("type", "")).lower()
    return {"array": [], "string": ""}.get(t)


def fill_back(answer, schema=VISION_RESPONSE_SCHEMA):
    """
    Each field the schema names but the answer left out, back with its empty value, and
    each enum value in the schema's own spelling (Claude doesn't guarantee an enum's
    capitals). Only adds what is missing and only re-cases a value that matches, so a
    Gemini answer comes out unchanged. Works in place; returns the answer.
    """
    t = str(schema.get("type", "")).lower()
    if t == "object" and isinstance(answer, dict):
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        for name, sub in props.items():
            if name in answer:
                answer[name] = fill_back(answer[name], sub)
            elif name in required and sub.get("nullable"):
                # Only the fields to_claude_schema() made optional; a required field missing
                # from an old recorded answer stays missing, as it always has (D-092).
                answer[name] = _empty(sub)
    elif t == "array" and isinstance(answer, list) and "items" in schema:
        for i, item in enumerate(answer):
            answer[i] = fill_back(item, schema["items"])
    elif isinstance(answer, str) and "enum" in schema and answer not in schema["enum"]:
        for value in schema["enum"]:
            if isinstance(value, str) and value.lower() == answer.lower():
                return value
    return answer


def limits(claude_schema):
    """(optional fields, union-typed fields) in a converted schema, as Claude counts them."""
    optional = union = 0
    stack = [claude_schema]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("type"), list) or "anyOf" in node:
            union += 1
        props = node.get("properties") or {}
        optional += len([n for n in props if n not in set(node.get("required") or [])])
        stack.extend(props.values())
        if "items" in node:
            stack.append(node["items"])
    return optional, union
