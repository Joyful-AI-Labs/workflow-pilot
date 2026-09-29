import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("PILOT_DATA_DIR", ROOT / "data"))
INBOX = DATA / "inbox"
PROCESSED = DATA / "processed"
LEDGER = DATA / "ledger.csv"
DB_PATH = DATA / "pilot.db"
PO_FILE = Path(os.getenv("PILOT_PO_FILE", ROOT / "samples" / "purchase_orders.csv"))
SAMPLE_INVOICES = ROOT / "samples" / "invoices"

BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
# "anthropic" = Anthropic's own API (PDF document input + structured outputs).
# "compat"    = an Anthropic-compatible endpoint (e.g. z.ai GLM coding plan): plain text in, JSON out.
PROVIDER = "anthropic" if not BASE_URL or "anthropic.com" in BASE_URL else "compat"
MODEL = os.getenv("PILOT_MODEL", "claude-opus-5" if PROVIDER == "anthropic" else "glm-4.6")
AMOUNT_TOLERANCE = float(os.getenv("PILOT_AMOUNT_TOLERANCE", "0.01"))
REVIEW_TOLERANCE = 0.15  # beyond this the invoice is rejected even if the vendor matches
VENDOR_THRESHOLD = 0.8

APPROVER_EMAIL = os.getenv("APPROVER_EMAIL", "")


def has_api_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
