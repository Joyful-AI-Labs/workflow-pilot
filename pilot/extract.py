"""Turn an invoice PDF into an `Invoice`.

Three extractors behind one function:
- ClaudeExtractor: sends the PDF itself to Claude and gets a validated Invoice back (structured outputs).
  Used on Anthropic's API (ANTHROPIC_API_KEY set, no custom base URL).
- CompatExtractor: for Anthropic-compatible endpoints (ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN, e.g. z.ai GLM).
  Those usually lack PDF input and output_config, so it sends the PDF's text and asks for JSON, then validates it.
- MockExtractor: regex over the PDF text (pypdf). Only good enough for the sample invoices; exists so the demo
  runs with zero credentials and so tests are deterministic.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from pypdf import PdfReader

from . import config
from .models import Invoice, LineItem

PROMPT = (
    "Extract the supplier invoice in the attached PDF. Use the invoice's own numbers; do not recompute totals. "
    "Dates as YYYY-MM-DD. If a purchase order reference is printed (PO, P.O., Purchase Order), put it in po_number, "
    "else leave po_number empty. Set confidence below 0.7 if any required field is unreadable or ambiguous."
)


class ClaudeExtractor:
    def __init__(self, model: str = config.MODEL):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def extract(self, pdf_path: Path) -> Invoice:
        data = base64.standard_b64encode(pdf_path.read_bytes()).decode()
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4096,
            output_config={"effort": "low"},  # extraction is routine; low effort keeps it fast and cheap
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
            output_format=Invoice,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined to process this document")
        return response.parsed_output


class CompatExtractor:
    """Text-in / JSON-out extraction for Anthropic-compatible endpoints."""

    def __init__(self, model: str = config.MODEL):
        import anthropic

        self.client = anthropic.Anthropic()  # base_url / auth token come from ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN
        self.model = model
        self.schema = json.dumps(Invoice.model_json_schema(), indent=0)

    def extract(self, pdf_path: Path) -> Invoice:
        text = pdf_text(pdf_path)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system="You extract supplier invoices. Reply with a single JSON object and nothing else - no prose, no code fences.",
            messages=[{"role": "user", "content": f"{PROMPT}\n\nJSON schema:\n{self.schema}\n\nInvoice text:\n{text}"}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < 0:
            raise ValueError(f"model did not return JSON: {raw[:120]!r}")
        return Invoice.model_validate(json.loads(raw[start:end + 1]))


def pdf_text(pdf_path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)


class MockExtractor:
    """Regex extractor for the synthetic sample layout produced by samples/make_samples.py."""

    def extract(self, pdf_path: Path) -> Invoice:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)

        def grab(label: str, default: str = "") -> str:
            m = re.search(rf"{label}\s*[:#]?\s*(.+)", text)
            return m.group(1).strip() if m else default

        def money(label: str) -> float:
            m = re.search(rf"{label}\s*[:\s]*(?:SGD|S\$|\$)?\s*([\d,]+\.\d{{2}})", text)
            return float(m.group(1).replace(",", "")) if m else 0.0

        items: list[LineItem] = []
        for m in re.finditer(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+x\s+([\d,]+\.\d{2})\s+=\s+([\d,]+\.\d{2})$", text, re.M):
            items.append(LineItem(description=m.group(1).strip(), quantity=float(m.group(2)),
                                  unit_price=float(m.group(3).replace(",", "")), amount=float(m.group(4).replace(",", ""))))
        po = grab("PO Reference")
        return Invoice(
            vendor_name=grab("From"),
            invoice_number=grab("Invoice No"),
            invoice_date=grab("Date"),
            po_number="" if po.lower() in ("", "-", "n/a") else po,
            subtotal=money("Subtotal"),
            tax=money(r"GST \(9%\)"),
            total=money("TOTAL"),
            line_items=items,
            confidence=0.9 if items else 0.5,
        )


_extractor = None


def get_extractor():
    global _extractor
    if _extractor is None:
        if not config.has_api_key():
            _extractor = MockExtractor()
        elif config.PROVIDER == "anthropic":
            _extractor = ClaudeExtractor()
        else:
            _extractor = CompatExtractor()
    return _extractor


def extractor_name() -> str:
    if not config.has_api_key():
        return "mock (no API key)"
    return f"{config.PROVIDER}:{config.MODEL}" + (" (text mode)" if config.PROVIDER == "compat" else " (pdf + structured output)")


def extract(pdf_path: Path) -> Invoice:
    return get_extractor().extract(pdf_path)
