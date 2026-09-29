"""One end-to-end check in mock mode: the 20 samples must land as 16 matched / 3 review / 1 rejected.

Run: python -m pytest -q   (or: python tests/test_pipeline.py)
"""
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.pop("ANTHROPIC_API_KEY", None)          # force the mock extractor
os.environ["PILOT_DATA_DIR"] = tempfile.mkdtemp()  # keep test state out of ./data

from pilot import config, db, match, pipeline  # noqa: E402
from pilot.models import Invoice  # noqa: E402


def test_match_rules():
    pos = match.load_purchase_orders()
    po = pos[0]
    exact = Invoice(vendor_name=po.vendor_name, invoice_number="X", invoice_date="2026-09-01", po_number=po.po_number,
                    total=po.amount, line_items=[])
    assert match.match(exact, pos).decision == "matched"
    off = exact.model_copy(update={"total": round(po.amount * 1.05, 2)})
    assert match.match(off, pos).decision == "review"
    far = exact.model_copy(update={"total": round(po.amount * 1.5, 2)})
    assert match.match(far, pos).decision == "rejected"
    stranger = exact.model_copy(update={"vendor_name": "Nobody Knows Pte Ltd", "po_number": ""})
    assert match.match(stranger, pos).decision == "rejected"


def test_samples_end_to_end():
    db.reset()
    config.INBOX.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(config.SAMPLE_INVOICES.glob("*.pdf")):
        shutil.copy(pdf, config.INBOX / pdf.name)
        pipeline.process_file(config.INBOX / pdf.name)
    counts = Counter(r["status"] for r in db.state()["invoices"])
    assert counts == {"matched": 16, "review": 3, "rejected": 1}, counts
    assert config.LEDGER.exists() and sum(1 for _ in open(config.LEDGER, encoding="utf-8-sig")) == 17  # header + 16
    review_id = next(r["id"] for r in db.state()["invoices"] if r["status"] == "review")
    pipeline.approve(review_id)
    assert db.get_invoice(review_id)["status"] == "approved"


if __name__ == "__main__":
    test_match_rules(); test_samples_end_to_end(); print("ok")
