"""Load the original purchase request and rules from the supplied sample pack."""
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .config import COMPANY_RULES_MD, PURCHASE_REQUEST_CSV


@dataclass(frozen=True)
class PurchaseItem:
    pr_number: str
    code: str
    description: str
    unit: str
    requested_quantity: int
    maximum_unit_price_bdt: Decimal


def load_purchase_request(path: str | Path = PURCHASE_REQUEST_CSV) -> dict[str, PurchaseItem]:
    """Use utf-8-sig because the supplied CSV includes a UTF-8 BOM."""
    items: dict[str, PurchaseItem] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = {
            "PR number", "Item", "Description", "Unit",
            "Quantity requested", "Maximum unit price (BDT)",
        }
        if not reader.fieldnames or not columns.issubset(set(reader.fieldnames)):
            raise ValueError("Purchase request CSV does not have the expected columns")

        for row in reader:
            try:
                code = row["Item"].strip().upper()
                qty = int(row["Quantity requested"].replace(",", "").strip())
                price = Decimal(row["Maximum unit price (BDT)"].replace(",", "").strip())
                if not code or qty <= 0 or not price.is_finite() or price < 0:
                    raise ValueError("Invalid purchase request entry")
                if code in items:
                    raise ValueError(f"Duplicate purchase request item: {code}")
                items[code] = PurchaseItem(
                    pr_number=row["PR number"].strip(),
                    code=code,
                    description=row["Description"].strip(),
                    unit=row["Unit"].strip(),
                    requested_quantity=qty,
                    maximum_unit_price_bdt=price,
                )
            except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
                raise ValueError(f"Invalid row in purchase request: {row}") from exc
    if not items:
        raise ValueError("Purchase request CSV is empty")
    return items


def load_company_rules(path: str | Path = COMPANY_RULES_MD) -> str:
    """Read rules as source data. Do not turn them into decisions yet."""
    text = Path(path).read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("Company rules are empty")
    return text
