"""
table_prompt.py - D-174: read only the nutrition table from photos we already hold.

Item #71 (2026-10-07): a Britannia pack's list and table were photographed, Gemini blocked
the label read (RECITATION, D-172), and the pack went to a person, who published it
without its table because nothing had read it. The next scan asked the user for the table
again (D-168, item #72).

This prompt asks for the table alone, as numbers. The answer copies no running text, so
the recitation guard has little to stop. It is its own prompt with its own version: the
label reader's prompt stays frozen (D-081). Its rules are rule 10 of that prompt, taken
from it word for word so the two can't drift, and its answer is that prompt's `nutrition`
object, so nutrition.check() (D-133) judges it like any other table: a number is kept
only where Cloud Vision's text of the same photo has it and the table adds up.
"""

import hashlib

from insidelabel.extraction.providers.prompt import VISION_PROMPT, VISION_RESPONSE_SCHEMA

_START, _END = "10. THE NUTRITION TABLE", "\n11. "
RULE_10 = VISION_PROMPT[VISION_PROMPT.index(_START):VISION_PROMPT.index(_END)].rstrip()

TABLE_PROMPT = f"""\
You are reading photos of an Indian packaged food's label. Read only the nutrition
table and the net quantity. Ignore everything else on the label: do not copy the
ingredient list or any other text.

Return JSON with two fields:
  nutrition     the nutrition table, by the rules below
  net_quantity  the net quantity as printed ("75 g", "200 ml"), or null

{RULE_10}
"""

TABLE_SCHEMA = {
    "type": "object",
    "properties": {
        "nutrition": VISION_RESPONSE_SCHEMA["properties"]["nutrition"],
        "net_quantity": {"type": "string", "nullable": True},
    },
    "required": ["nutrition", "net_quantity"],
    "propertyOrdering": ["nutrition", "net_quantity"],
}

TABLE_PROMPT_VERSION = "table-" + hashlib.sha256(TABLE_PROMPT.encode()).hexdigest()[:12]
