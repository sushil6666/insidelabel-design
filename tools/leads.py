#!/usr/bin/env python3
"""
Track products seen on marketplaces until their real label is in the catalogue (D-089).

A listing screenshot is a research lead, not a source. This tool records the
lead, keeps the screenshot privately in research/, and follows the lead until
the physical pack has been photographed, scanned and published through /review.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"

    # 1. you saw it on Flipkart
    python tools/leads.py add "Limca" --brand "Coca-Cola" --size "750 ml" \
        --platform Flipkart --url https://www.flipkart.com/... --shot ~/shots/limca.png

    # 2. you bought the pack        3. you scanned front + back (/scan with barcode)
    python tools/leads.py obtained 1
    python tools/leads.py link 1 --barcode 8901764012273      # or --version 42

    # 4. publish it on /review - the lead closes itself
    python tools/leads.py list                   # what's still needed
    python tools/leads.py export > leads.json    # provenance records
    python tools/leads.py abandon 7 "not sold offline"
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.db.leads import PLATFORMS, LeadError, Leads, store_screenshot  # noqa: E402

RESEARCH = os.path.join(ROOT, "research")
ORDER = ["needs_primary_source", "pack_obtained", "label_captured", "published", "abandoned"]


def provenance(lead):
    """The provenance record for one lead (D-089)."""
    return {
        "lead_id": lead["id"],
        "product": lead["product"],
        "brand": lead["brand"],
        "variant": lead["variant"],
        "net_quantity": lead["net_quantity"],
        "barcode": lead["barcode"],
        "source_type": lead["source_type"],
        "source_platform": lead["source_platform"],
        "source_url": lead["source_url"],
        "screenshot_sha256": lead["screenshot_sha256"],
        "captured_on": lead["captured_on"].isoformat(),
        "production_source": lead["production_source"],
        "evidence_status": lead["evidence_status"],
        "product_version_id": lead["product_version_id"],
    }


def show(lead):
    tail = f" → version #{lead['product_version_id']}" if lead["product_version_id"] else ""
    what = " · ".join(x for x in (lead["brand"], lead["product"], lead["variant"], lead["net_quantity"]) if x)
    src = lead["source_platform"] or lead["source_type"]
    print(f"#{lead['id']:<4} {lead['evidence_status']:<21} {what}  [{src}]{tail}"
          + (f"\n      {lead['status_note']}" if lead["status_note"] else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="record a product seen on a marketplace")
    a.add_argument("product")
    a.add_argument("--brand"); a.add_argument("--variant"); a.add_argument("--size", dest="net_quantity")
    a.add_argument("--barcode")
    a.add_argument("--platform", choices=PLATFORMS)
    a.add_argument("--type", dest="source_type", default="marketplace_reference",
                   choices=["marketplace_reference", "user_share", "store_visit", "open_data_reference"])
    a.add_argument("--url"); a.add_argument("--shot", help="screenshot file (kept privately in research/)")
    a.add_argument("--notes")
    a.add_argument("--by", default=os.environ.get("USER", "unknown"))

    lst = sub.add_parser("list", help="leads, grouped by status")
    lst.add_argument("--status", choices=ORDER)

    o = sub.add_parser("obtained", help="you have the physical pack")
    o.add_argument("id", type=int); o.add_argument("--note")

    ln = sub.add_parser("link", help="attach the version read from the pack")
    ln.add_argument("id", type=int)
    g = ln.add_mutually_exclusive_group(required=True)
    g.add_argument("--version", type=int); g.add_argument("--barcode")

    ab = sub.add_parser("abandon", help="stop chasing a lead, with a reason")
    ab.add_argument("id", type=int); ab.add_argument("reason")

    sub.add_parser("export", help="provenance records as JSON")

    args = ap.parse_args(argv)
    if not args.db:
        ap.error("set INSIDELABEL_DB or pass --db")
    leads = Leads(args.db)

    try:
        if args.cmd == "add":
            digest = store_screenshot(os.path.expanduser(args.shot), RESEARCH) if args.shot else None
            show(leads.add(product=args.product, brand=args.brand, variant=args.variant,
                           net_quantity=args.net_quantity, barcode=args.barcode,
                           source_type=args.source_type, source_platform=args.platform,
                           source_url=args.url, screenshot_sha256=digest, notes=args.notes,
                           noted_by=args.by))
        elif args.cmd == "list":
            rows = leads.list(args.status)
            for status in ORDER:
                group = [r for r in rows if r["evidence_status"] == status]
                if group:
                    print(f"\n{status} ({len(group)})")
                    for r in group:
                        show(r)
            if not rows:
                print("no leads")
        elif args.cmd == "obtained":
            show(leads.pack_obtained(args.id, args.note))
        elif args.cmd == "link":
            show(leads.link(args.id, product_version_id=args.version, barcode=args.barcode))
        elif args.cmd == "abandon":
            show(leads.abandon(args.id, args.reason))
        elif args.cmd == "export":
            print(json.dumps([provenance(r) for r in leads.list()], indent=2, ensure_ascii=False))
    except LeadError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
