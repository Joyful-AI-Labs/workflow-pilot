"""Generate 20 synthetic supplier invoices (PDF) and the purchase-order table they should be matched against.

Deterministic. Companies, people and numbers are invented. Re-run with `python samples/make_samples.py`.
Expected outcome when the pilot processes all 20: 16 matched, 3 review, 1 rejected.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "invoices"
CUSTOMER = "Northside Trading Pte. Ltd.\n12 Kallang Way, #04-01\nSingapore 349221"

VENDORS = {
    "Meridian Office Supplies Pte Ltd": ["A4 copier paper (box)", "Toner cartridge HP 26A", "Ballpoint pens (box of 50)", "Sticky notes 3x3 (pack)"],
    "Kallang Logistics Services Pte Ltd": ["Local delivery - van", "Warehouse handling fee", "Pallet wrap", "Express courier"],
    "Harbourfront IT Solutions Pte Ltd": ["Laptop Dell Latitude 5450", "USB-C docking station", "Monitor 27in", "On-site support hour"],
    "Tanjong Cleaning Co Pte Ltd": ["Office cleaning - weekly", "Carpet shampoo", "Sanitiser refill", "Pantry consumables"],
    "Bugis Print House Pte Ltd": ["Business cards (box)", "A3 poster print", "Brochure tri-fold (500)", "Banner 2m x 1m"],
    "Jurong Industrial Parts Pte Ltd": ["Steel bracket 40mm", "Hex bolt M8 (100)", "Bearing 6204", "Safety gloves (pair)"],
    "Orchard Catering Pte Ltd": ["Lunch bento (per pax)", "Coffee urn service", "Tea break set", "Bottled water (case)"],
    "Paya Lebar Facilities Pte Ltd": ["Aircon servicing (unit)", "Pest control visit", "Fire extinguisher check", "Light tube replacement"],
}


def money(x: float) -> str:
    return f"{x:,.2f}"


def build_invoice(pdf: Path, vendor: str, inv_no: str, inv_date: date, po_ref: str, items: list[tuple[str, int, float]]) -> float:
    c = canvas.Canvas(str(pdf), pagesize=A4)
    w, h = A4
    y = h - 25 * mm
    c.setFont("Helvetica-Bold", 20); c.drawString(20 * mm, y, "INVOICE"); y -= 12 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"From: {vendor}"); y -= 5 * mm
    c.drawString(20 * mm, y, "Invoice No: " + inv_no); y -= 5 * mm
    c.drawString(20 * mm, y, "Date: " + inv_date.isoformat()); y -= 5 * mm
    c.drawString(20 * mm, y, "PO Reference: " + (po_ref or "-")); y -= 10 * mm
    c.drawString(20 * mm, y, "Bill To:"); y -= 5 * mm
    for line in CUSTOMER.split("\n"):
        c.drawString(25 * mm, y, line); y -= 5 * mm
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 10); c.drawString(20 * mm, y, "Description"); c.drawString(120 * mm, y, "Qty x Unit = Amount"); y -= 6 * mm
    c.setFont("Helvetica", 10)
    subtotal = 0.0
    for desc, qty, unit in items:
        amt = round(qty * unit, 2); subtotal += amt
        c.drawString(20 * mm, y, f"{desc} {qty} x {money(unit)} = {money(amt)}"); y -= 5 * mm
    gst = round(subtotal * 0.09, 2); total = round(subtotal + gst, 2)
    y -= 5 * mm
    c.drawString(120 * mm, y, f"Subtotal: SGD {money(subtotal)}"); y -= 5 * mm
    c.drawString(120 * mm, y, f"GST (9%): SGD {money(gst)}"); y -= 5 * mm
    c.setFont("Helvetica-Bold", 11); c.drawString(120 * mm, y, f"TOTAL: SGD {money(total)}"); y -= 12 * mm
    c.setFont("Helvetica", 8); c.drawString(20 * mm, y, "Synthetic sample for the JoyfulAI Workflow Automation Pilot demo. Not a real company or transaction.")
    c.save()
    return total


def main() -> None:
    rng = random.Random(42)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.pdf"):
        old.unlink()
    vendors = list(VENDORS)
    pos: list[dict] = []
    start = date(2026, 9, 1)

    def pick_items(vendor: str) -> list[tuple[str, int, float]]:
        names = rng.sample(VENDORS[vendor], k=rng.randint(2, 3))
        return [(n, rng.randint(1, 12), round(rng.uniform(8, 480), 2)) for n in names]

    # 16 clean matches: invoice total == PO amount
    plan: list[dict] = []
    for i in range(16):
        v = vendors[i % len(vendors)]
        plan.append(dict(vendor=v, items=pick_items(v), po=True, tweak=None))
    # 3 review cases
    plan.append(dict(vendor=vendors[0], items=pick_items(vendors[0]), po=True, tweak="amount+6%"))            # price crept up
    plan.append(dict(vendor=vendors[1], items=pick_items(vendors[1]), po=True, tweak="vendor-variant"))        # "Kallang Logistics Svcs Pte. Ltd."
    plan.append(dict(vendor=vendors[2], items=pick_items(vendors[2]), po=False, tweak="no-po-amount+3%"))     # no PO quoted, slightly off
    # 1 rejection: unknown vendor
    plan.append(dict(vendor="Woodlands Unknown Supplies Pte Ltd", items=[("Mystery consulting fee", 1, 1250.00)], po=False, tweak="unknown-vendor"))

    for n, p in enumerate(plan, start=1):
        inv_no = f"INV-2026-{1000 + n}"
        inv_date = start + timedelta(days=rng.randint(0, 26))
        po_no = f"PO-26{n:03d}" if p["po"] or p["tweak"] == "no-po-amount+3%" else ""
        items = p["items"]
        vendor_on_invoice = p["vendor"]
        if p["tweak"] == "amount+6%":
            items = [(d, q, round(u * 1.06, 2)) for d, q, u in items]
        elif p["tweak"] == "vendor-variant":
            vendor_on_invoice = "Kallang Logistics Svcs Pte. Ltd."
        elif p["tweak"] == "no-po-amount+3%":
            items = [(d, q, round(u * 1.03, 2)) for d, q, u in items]
        pdf = OUT / f"{inv_no}_{vendor_on_invoice.split()[0].lower()}.pdf"
        total = build_invoice(pdf, vendor_on_invoice, inv_no, inv_date, po_no if p["po"] else "", items)
        if po_no and p["tweak"] != "unknown-vendor":
            base_items = p["items"]
            base_total = round(sum(round(q * u, 2) for _, q, u in base_items) * 1.09, 2)
            pos.append(dict(po_number=po_no, vendor_name=p["vendor"], amount=f"{base_total:.2f}", currency="SGD",
                            items="; ".join(d for d, _, _ in base_items), status="open"))
    # a couple of extra open POs that never get an invoice
    pos.append(dict(po_number="PO-26900", vendor_name=vendors[3], amount="412.36", currency="SGD", items="Office cleaning - weekly", status="open"))
    pos.append(dict(po_number="PO-26901", vendor_name=vendors[5], amount="1899.00", currency="SGD", items="Steel bracket 40mm; Bearing 6204", status="open"))

    with open(HERE / "purchase_orders.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["po_number", "vendor_name", "amount", "currency", "items", "status"])
        w.writeheader(); w.writerows(pos)
    print(f"wrote {len(plan)} invoices to {OUT} and {len(pos)} purchase orders")


if __name__ == "__main__":
    main()
