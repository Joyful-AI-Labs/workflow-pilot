"""Approval requests. SMTP when configured, otherwise the email is written to the event log so the demo shows it."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from .models import Invoice, MatchResult


def approval_email(invoice_id: int, invoice: Invoice, result: MatchResult, base_url: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"[Approval needed] Invoice {invoice.invoice_number} from {invoice.vendor_name} - {invoice.currency} {invoice.total:,.2f}"
    msg["From"] = os.getenv("SMTP_FROM", "pilot@example.com")
    msg["To"] = os.getenv("APPROVER_EMAIL", "approver@example.com")
    lines = [
        f"Invoice {invoice.invoice_number} ({invoice.invoice_date}) from {invoice.vendor_name}",
        f"Total: {invoice.currency} {invoice.total:,.2f}",
        f"Best purchase order: {result.po_number or 'none'}",
        "",
        "Why this needs you:",
        *[f"  - {r}" for r in result.reasons],
        "",
        f"Approve: {base_url}/api/invoices/{invoice_id}/approve",
        f"Reject:  {base_url}/api/invoices/{invoice_id}/reject",
    ]
    msg.set_content("\n".join(lines))
    return msg


def send(msg: EmailMessage) -> str:
    """Returns a one-line description of what happened, for the event log."""
    host = os.getenv("SMTP_HOST")
    if not host:
        return "approval email (not sent - no SMTP configured):\n" + msg.get_content()
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as s:
        s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
        s.send_message(msg)
    return f"approval email sent to {msg['To']}"
