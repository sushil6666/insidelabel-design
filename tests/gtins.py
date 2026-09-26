"""Unique, valid test barcodes (GS1 check digit, India prefix 890). D-107: only barcoded packs enter the catalogue."""
import uuid


def gtin():
    body = "890" + str(uuid.uuid4().int)[:9]
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)
