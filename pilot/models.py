from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0
    amount: float = 0


class Invoice(BaseModel):
    """What we extract from a supplier invoice. Amounts are in the invoice currency."""

    vendor_name: str
    invoice_number: str
    invoice_date: str = Field(description="ISO date YYYY-MM-DD if present, else empty")
    po_number: str = Field(default="", description="Purchase order reference printed on the invoice, if any")
    currency: str = "SGD"
    subtotal: float = 0
    tax: float = 0
    total: float
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1, description="Extractor's confidence that the fields are right")


class PurchaseOrder(BaseModel):
    po_number: str
    vendor_name: str
    amount: float
    currency: str = "SGD"
    items: str = ""
    status: str = "open"


Decision = Literal["matched", "review", "rejected"]


class MatchResult(BaseModel):
    decision: Decision
    po_number: Optional[str] = None
    vendor_similarity: float = 0
    amount_difference: float = 0
    item_overlap: float = 0
    reasons: list[str] = Field(default_factory=list)
