"""The pilot's one workflow: extract -> match -> route -> record."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import config, db, extract, ledger, match, notify
from .models import Invoice, MatchResult

BASE_URL = "http://localhost:8000"


def process_file(path: Path, invoice_id: int | None = None) -> int:
    if invoice_id is None:
        invoice_id = db.add_invoice(path.name)
    db.log(f"new invoice received: {path.name}", invoice_id)
    try:
        db.set_status(invoice_id, "extracting")
        db.log(f"extracting fields ({extract.extractor_name()})", invoice_id)
        invoice = extract.extract(path)
        db.set_status(invoice_id, "matching", invoice=invoice)
        db.log(f"extracted: {invoice.vendor_name} / {invoice.invoice_number} / {invoice.currency} {invoice.total:,.2f}"
               + (f" / PO {invoice.po_number}" if invoice.po_number else ""), invoice_id)

        result = match.match(invoice, match.load_purchase_orders())
        for reason in result.reasons:
            db.log(reason, invoice_id)
        route(invoice_id, invoice, result, path.name)
    except Exception as e:  # keep the queue moving; the row shows the error
        db.set_status(invoice_id, "error")
        db.log(f"error: {e}", invoice_id, level="error")
    finally:
        config.PROCESSED.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.parent == config.INBOX:
            shutil.move(str(path), config.PROCESSED / path.name)
    return invoice_id


def route(invoice_id: int, invoice: Invoice, result: MatchResult, document: str) -> None:
    if result.decision == "matched":
        db.set_status(invoice_id, "matched", result=result)
        ledger.append(invoice, result, document)
        db.log(f"posted to ledger against PO {result.po_number}", invoice_id)
    elif result.decision == "review":
        db.set_status(invoice_id, "review", result=result)
        db.log(notify.send(notify.approval_email(invoice_id, invoice, result, BASE_URL)), invoice_id, level="warn")
    else:
        db.set_status(invoice_id, "rejected", result=result)
        db.log("returned to sender: " + result.reasons[-1], invoice_id, level="error")


def approve(invoice_id: int) -> None:
    row = db.get_invoice(invoice_id)
    if not row or row["status"] != "review":
        raise ValueError("invoice is not waiting for review")
    invoice, result = Invoice(**row["invoice"]), MatchResult(**row["match"])
    db.set_status(invoice_id, "approved")
    ledger.append(invoice, result, row["file"])
    db.log(f"approved by reviewer; posted to ledger against PO {result.po_number or 'n/a'}", invoice_id)


def reject(invoice_id: int) -> None:
    row = db.get_invoice(invoice_id)
    if not row or row["status"] != "review":
        raise ValueError("invoice is not waiting for review")
    db.set_status(invoice_id, "rejected")
    db.log("rejected by reviewer; returned to sender", invoice_id, level="error")
