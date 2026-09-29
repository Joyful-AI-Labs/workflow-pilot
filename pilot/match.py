"""Match an extracted invoice against open purchase orders.

Rules (in order):
1. Vendor must be similar (normalised name similarity >= VENDOR_THRESHOLD), or the invoice must quote a PO number we know.
2. Amount within AMOUNT_TOLERANCE of the PO -> matched (auto-approve).
3. Amount within REVIEW_TOLERANCE, or PO quoted but vendor name differs, or line items barely overlap -> review (human).
4. Otherwise -> rejected.
"""
from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

from . import config
from .models import Invoice, MatchResult, PurchaseOrder

_SUFFIXES = re.compile(r"\b(pte|ltd|limited|inc|llc|co|company|corp|corporation|sdn|bhd)\b\.?")


def normalise(name: str) -> str:
    name = name.lower()
    name = _SUFFIXES.sub(" ", name)
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    return " ".join(name.split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def item_overlap(invoice: Invoice, po: PurchaseOrder) -> float:
    inv = set().union(*[_tokens(i.description) for i in invoice.line_items]) if invoice.line_items else set()
    ref = _tokens(po.items)
    if not inv or not ref:
        return 1.0  # nothing to compare: don't penalise
    return len(inv & ref) / len(ref)


def load_purchase_orders(path: Path = config.PO_FILE) -> list[PurchaseOrder]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [PurchaseOrder(**{k: (float(v) if k == "amount" else v) for k, v in row.items()}) for row in csv.DictReader(f)]


def match(invoice: Invoice, pos: list[PurchaseOrder]) -> MatchResult:
    open_pos = [p for p in pos if p.status == "open"]
    quoted = next((p for p in open_pos if invoice.po_number and p.po_number.lower() == invoice.po_number.lower()), None)

    scored = sorted(((similarity(invoice.vendor_name, p.vendor_name), p) for p in open_pos), key=lambda t: -t[0])
    candidates = [(s, p) for s, p in scored if s >= config.VENDOR_THRESHOLD]
    if quoted and quoted not in [p for _, p in candidates]:
        candidates.insert(0, (similarity(invoice.vendor_name, quoted.vendor_name), quoted))

    if not candidates:
        best = scored[0][0] if scored else 0
        return MatchResult(decision="rejected", vendor_similarity=round(best, 2),
                           reasons=[f"no open purchase order for vendor '{invoice.vendor_name}' (best name similarity {best:.0%})"])

    # pick the candidate whose amount is closest to the invoice total
    def amount_diff(p: PurchaseOrder) -> float:
        return abs(invoice.total - p.amount) / p.amount if p.amount else 1.0

    sim, po = min(candidates, key=lambda t: amount_diff(t[1]))
    diff = amount_diff(po)
    overlap = item_overlap(invoice, po)
    reasons: list[str] = [f"vendor matches {po.vendor_name} ({sim:.0%})", f"amount {invoice.currency} {invoice.total:,.2f} vs PO {po.amount:,.2f} ({diff:.1%} off)"]
    if invoice.po_number:
        reasons.append(f"invoice quotes PO {invoice.po_number}" + ("" if quoted else " (unknown PO number)"))

    result = MatchResult(po_number=po.po_number, vendor_similarity=round(sim, 2), amount_difference=round(diff, 4),
                         item_overlap=round(overlap, 2), reasons=reasons, decision="review")

    if diff > config.REVIEW_TOLERANCE:
        result.decision = "rejected"
        result.reasons.append(f"amount differs by more than {config.REVIEW_TOLERANCE:.0%}")
    elif diff <= config.AMOUNT_TOLERANCE and sim >= 0.95 and overlap >= 0.3 and invoice.confidence >= 0.7 and (not invoice.po_number or quoted):
        result.decision = "matched"
        result.reasons.append("within tolerance: auto-approved")
    else:
        if diff > config.AMOUNT_TOLERANCE:
            result.reasons.append("amount outside auto-approve tolerance")
        if sim < 0.95:
            result.reasons.append("vendor name differs from PO")
        if overlap < 0.3:
            result.reasons.append(f"line items overlap only {overlap:.0%} with PO")
        if invoice.confidence < 0.7:
            result.reasons.append(f"extraction confidence low ({invoice.confidence:.0%})")
        if invoice.po_number and not quoted:
            result.reasons.append("quoted PO number not found")
        result.reasons.append("needs a human decision")
    return result
