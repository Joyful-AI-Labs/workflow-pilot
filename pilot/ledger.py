"""Append approved invoices to a simple ledger CSV (same columns JoyfulAI uses for its own books)."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from . import config
from .models import Invoice, MatchResult

HEADER = ["date", "type", "category", "description", "counterparty", "amount", "currency", "amount_sgd", "account", "document", "notes"]


def append(invoice: Invoice, result: MatchResult, document: str, path: Path = config.LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        w.writerow([
            invoice.invoice_date or date.today().isoformat(), "expense", "supplier-invoice",
            f"Invoice {invoice.invoice_number}" + (f" against PO {result.po_number}" if result.po_number else ""),
            invoice.vendor_name, f"{-invoice.total:.2f}", invoice.currency,
            f"{-invoice.total:.2f}" if invoice.currency == "SGD" else "", "AP", document,
            "auto-matched" if result.decision == "matched" else "approved by reviewer",
        ])
