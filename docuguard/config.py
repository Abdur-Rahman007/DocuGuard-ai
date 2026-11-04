"""Project paths. Works regardless of the terminal's current directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "sample-data" / "engineer" / "task1-procurement"
PURCHASE_REQUEST_CSV = DATA_DIR / "purchase-request.csv"
COMPANY_RULES_MD = DATA_DIR / "company-rules.md"


def sample_pdfs() -> list[Path]:
    """Return supplier sample PDFs in a stable, deterministic order."""
    return sorted(DATA_DIR.glob("supplier-pack-*.pdf"))
