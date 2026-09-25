"""
FSSAI food categories (Appendix A, Food Category System) in the `categories` table.

The list is data (`data/food_categories.json`, verified against the compendium);
this module only mirrors it into Postgres so `products.category_id` can point at
it. `migrate.apply()` calls sync() after the migrations, so every database —
including each test database — has the same list.

Rows are upserted by code and never deleted: a product may already point at one.
"""

import json
import os

from insidelabel.core.engine import DATA_DIR

# The review screen's shortlist (D-058: kids' biscuits first). Each hint is from
# the category's own description in Appendix A Part II, not from memory.
COMMON = [
    ("7.2.1", "Sweet biscuits, cookies, cakes, pies"),
    ("7.2.2", "Wafers, muffins, doughnuts, sweet buns"),
    ("7.1.2", "Plain (unsweetened) crackers"),
    ("15.1", "Chips, namkeen/bhujia, flavoured crackers, papad"),
    ("5.1.3", "Chocolate and chocolate confectionery"),
    ("14.1.4.1", "Colas and other sodas (carbonated flavoured drinks)"),
    ("6.3", "Breakfast cereals, oats, cornflakes, poha"),
]


def load(path=None):
    path = path or os.path.join(os.environ.get("INSIDELABEL_DATA", DATA_DIR), "food_categories.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["categories"]


def _parent(code):
    return code.rsplit(".", 1)[0] if "." in code else None


def sync(conn, categories=None):
    """Upsert every category, then set parent links. Returns the number of rows."""
    cats = categories or load()
    for c in cats:
        conn.execute("""INSERT INTO categories (code, name) VALUES (%s, %s)
                        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name""",
                     (c["code"], c["name"]))
    for c in cats:
        if _parent(c["code"]):
            conn.execute("""UPDATE categories SET parent_id = (SELECT id FROM categories WHERE code = %s)
                             WHERE code = %s""", (_parent(c["code"]), c["code"]))
    return len(cats)
