"""Evidence-first parsing and deterministic purchasing-rule assessment.

No text from a PDF is ever executed as an instruction. All monetary comparisons
use Decimal, and missing or unsupported fields cause human-review escalation.
This parser targets the ten BIAI example layouts (not arbitrary PDFs).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .local_ai import AIReview

from .data_loader import PurchaseItem
from .pdf_reader import DocumentText


D = Decimal
Severity = Literal["Reject", "Needs a person to check"]


@dataclass(frozen=True)
class Evidence:
    page: int
    quote: str


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    reason: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class QuoteDetails:
    supplier: str | None = None
    quotation_number: str | None = None
    pr_number: str | None = None
    item_code: str | None = None
    description: str | None = None
    quantity: int | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    line_amount: Decimal | None = None
    subtotal: Decimal | None = None
    vat_amount: Decimal | None = None
    total: Decimal | None = None
    tin: str | None = None
    bin: str | None = None
    advance_pct: Decimal | None = None
    advance_is_conflicting: bool = False
    payment_days: int | None = None
    payment_is_ambiguous: bool = False
    delivery_days: int | None = None
    delivery_is_conflicting: bool = False
    penalty_pct: Decimal | None = None
    penalty_is_waived: bool = False
    penalty_is_weekly: bool = False
    penalty_is_conflicting: bool = False
    validity_days: int | None = None
    vat_separately_shown: bool = False
    item_evidence: tuple[Evidence, ...] = ()
    clauses: dict[str, Evidence] = field(default_factory=dict)
    registration_evidence: tuple[Evidence, ...] = ()
    totals_evidence: tuple[Evidence, ...] = ()
    evidence_header: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Assessment:
    filename: str
    decision: Literal["Approve", "Reject", "Needs a person to check"]
    quote: QuoteDetails | None
    findings: tuple[Finding, ...]
    checks_performed: int
    error: str | None = None
    ai_review: AIReview | None = None


def money(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        result = D(raw.replace(",", "").strip())
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def _value(lines: list[str], name: str) -> str | None:
    """Read a labelled value occupying the following line in the sample PDFs."""
    for pos, line in enumerate(lines[:-1]):
        if line.lower() == name.lower():
            return lines[pos + 1].strip() or None
    return None


def _clause(raw: str, name: str) -> str | None:
    m = re.search(rf"(?ims)^\d+\.\s*{re.escape(name)}\.\s*.*?(?=^\d+\.\s|^For\s+|\Z)", raw)
    return m.group(0).strip() if m else None


def _ev(text: str | None, page: int = 1) -> tuple[Evidence, ...]:
    return (Evidence(page=page, quote=text),) if text else ()


def _registration_status(value: str | None) -> Literal["valid", "missing", "unclear"]:
    """Fail closed for placeholders; do not claim database validation of tax IDs.

    This is a structural format check only, not verification against a registry.
    """
    if value is None:
        return "missing"
    cleaned = value.strip().strip(".;,:")
    if not cleaned or re.fullmatch(
        r"(?i)n\s*/?\s*a|none|nil|pending|not\s+(?:provided|available|issued)|"
        r"unavailable|to\s+(?:follow|be\s+provided)|awaiting(?:\s+approval)?|"
        r"available\s+on\s+request",
        cleaned,
    ):
        return "missing"
    # BIAI sample tax IDs are numeric TINs and numeric-hyphenated BINs.
    # Unknown formats need human verification, never an automatic approval.
    if re.fullmatch(r"\d{8,15}(?:-\d{2,6})?", cleaned):
        return "valid"
    return "unclear"


def _days(amount: str, unit: str) -> int:
    return int(amount) * (7 if unit.lower().startswith("week") else 1)


def approval_evidence(quote: QuoteDetails) -> tuple[tuple[str, Evidence], ...]:
    """Exact source excerpts for successfully checked decisions (not a certification).

    UI/CSV callers must use this only after the full rule engine approves.
    """
    evidence: list[tuple[str, Evidence]] = []
    groups = [
        ("Item / quantity / price", quote.item_evidence),
        ("Supplier TIN and BIN", quote.registration_evidence),
        ("Payment terms", _ev(quote.clauses["Payment"].quote) if "Payment" in quote.clauses else ()),
        ("Delivery commitment", _ev(quote.clauses["Delivery"].quote) if "Delivery" in quote.clauses else ()),
        ("Late-delivery penalty", _ev(quote.clauses["Delay"].quote) if "Delay" in quote.clauses else ()),
        ("Quote validity", _ev(quote.clauses["Validity"].quote) if "Validity" in quote.clauses else ()),
        ("Subtotal, VAT and total", quote.totals_evidence),
    ]
    for label, excerpts in groups:
        for excerpt in excerpts:
            evidence.append((label, excerpt))
    return tuple(evidence)


def extract_quote(document: DocumentText) -> QuoteDetails:
    """Parse the supplied quotation's structured table and contract clauses.

    The document text is not transformed to invent evidence. Evidence snippets
    use unmodified chunks of extracted page text, preserving the printed words.
    """
    raw = document.full_text
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    supplier = lines[0] if lines else None
    header = _ev("\n".join(lines[:8]) if lines else None)
    quote_number = _value(lines, "Quotation no.")
    pr_number = _value(lines, "Reference")

    # Single-line item table as rendered by PyMuPDF in the BIAI samples.
    # Locate the 1-character item code rather than relying on fragile column widths.
    item_index = None
    for i in range(len(lines) - 5):
        if re.fullmatch(r"[A-E]", lines[i]) and lines[i+2].replace(",", "").isdigit():
            item_index = i
            break
    item_data: dict = {}
    if item_index is not None:
        cells = lines[item_index:item_index+6]
        item_data = dict(
            item_code=cells[0], description=cells[1],
            quantity=int(cells[2].replace(",", "")), unit=cells[3],
            unit_price=money(cells[4]), line_amount=money(cells[5]),
            item_evidence=_ev("\n".join(cells)),
        )

    subtotal = _value(lines, "Subtotal")
    vat = _value(lines, "VAT 15%")
    total = _value(lines, "Total") or _value(lines, "Total (all taxes included)")
    total_evidence = []
    for label in ("Subtotal", "VAT 15%", "Total", "Total (all taxes included)"):
        for pos in range(len(lines) - 1):
            if lines[pos] == label:
                total_evidence.append(Evidence(1, "\n".join(lines[pos:pos+2])))

    # Keep the complete values so N/A, pending and other placeholders cannot be
    # mistaken for verified registration numbers.
    reg_match = re.search(
        r"(?im)^Supplier\s+TIN:[ \t]*([^\r\n]*?)[ \t]+BIN:[ \t]*([^\r\n]*)$",
        raw,
    )
    reg_note = next((line for line in lines if "registration details" in line.lower()), None)
    registration_evidence = _ev(reg_match.group(0) if reg_match else reg_note)

    clauses = {name: Evidence(1, text) for name in ("Payment", "Delivery", "Delay", "Validity")
               if (text := _clause(raw, name))}
    payment = clauses.get("Payment")
    payment_text = payment.quote if payment else ""
    advance_rates: list[Decimal] = []
    for pattern in (
        r"\b(\d+(?:\.\d+)?)\s*%\s+(?:\w+\s+){0,2}advance\b",
        r"\badvance(?:\s+payment)?(?:\s+(?:of|is|at|:))?\s+(\d+(?:\.\d+)?)\s*%",
    ):
        advance_rates.extend(D(x) for x in re.findall(pattern, payment_text, re.I))
    no_advance = bool(re.search(r"\bno\s+advance\s+payment\b", payment_text, re.I))
    unique_advance_rates = set(advance_rates) | ({D(0)} if no_advance else set())
    advance_is_conflicting = len(unique_advance_rates) > 1
    # An explicit 40% advance must never be hidden by another 10% statement.
    advance_pct = max(unique_advance_rates) if unique_advance_rates else None
    range_due = re.search(r"(?:within|in)\s+(\d+)\s*(?:to|-)\s*(\d+)\s+days", payment_text, re.I)
    simple_due = re.findall(r"(?:within|in)\s+(\d+)\s+days\s+(?:after|of)\s+delivery", payment_text, re.I)
    payment_days = int(simple_due[0]) if simple_due and not range_due else None
    payment_is_ambiguous = bool(range_due or len(set(simple_due)) > 1 or re.search(r"as agreed|to be agreed|subject to", payment_text, re.I))

    delivery_text = clauses.get("Delivery").quote if "Delivery" in clauses else ""
    delivery_days = None
    promised = [_days(n, unit) for n, unit in re.findall(
        r"\bwithin\s+(\d+)\s+(days?|weeks?)\b", delivery_text, re.I,
    )]
    lower_bounds = [_days(n, unit) for n, unit in re.findall(
        r"\b(?:not\s+before|no\s+earlier\s+than|"
        r"cannot\s+(?:occur|be\s+made|take\s+place)\s+before|at\s+least)\s+"
        r"(\d+)\s+(days?|weeks?)\b", delivery_text, re.I,
    )]
    if promised:
        delivery_days = promised[0]
    delivery_is_conflicting = len(set(promised)) > 1 or bool(
        promised and any(bound > min(promised) for bound in lower_bounds)
    )

    delay_text = clauses.get("Delay").quote if "Delay" in clauses else ""
    penalty_rates = [D(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", delay_text)]
    penalty_pct = min(penalty_rates) if penalty_rates else None
    penalty_is_conflicting = len(set(penalty_rates)) > 1
    penalty_is_waived = bool(re.search(
        r"\b(?:no\s+(?:late[\s-]*delivery\s+)?penalty|"
        r"penalt(?:y|ies)\s+(?:is\s+|are\s+)?(?:waived|not\s+applicable)|"
        r"penalty\s+will\s+not\s+apply|no\s+liability\s+for\s+delay)\b",
        delay_text, re.I,
    ))
    penalty_is_weekly = bool(re.search(
        r"\b(?:per|each|every|for\s+each)\s+(?:full\s+)?week\b|\bweekly\b",
        delay_text, re.I,
    ))

    validity_text = clauses.get("Validity").quote if "Validity" in clauses else ""
    validity_match = re.search(r"\bvalid for\s+(\d+)\s+days\b", validity_text, re.I)
    validity_days = int(validity_match.group(1)) if validity_match else None
    return QuoteDetails(
        supplier=supplier, quotation_number=quote_number, pr_number=pr_number,
        subtotal=money(subtotal), vat_amount=money(vat), total=money(total),
        tin=reg_match.group(1).strip() if reg_match else None,
        bin=reg_match.group(2).strip() if reg_match else None,
        advance_pct=advance_pct, advance_is_conflicting=advance_is_conflicting,
        payment_days=payment_days, payment_is_ambiguous=payment_is_ambiguous,
        delivery_days=delivery_days, delivery_is_conflicting=delivery_is_conflicting,
        penalty_pct=penalty_pct, penalty_is_waived=penalty_is_waived,
        penalty_is_weekly=penalty_is_weekly,
        penalty_is_conflicting=penalty_is_conflicting, validity_days=validity_days,
        vat_separately_shown=bool(vat is not None and re.search(r"(?m)^VAT 15%$", raw)),
        clauses=clauses, registration_evidence=registration_evidence,
        totals_evidence=tuple(total_evidence), evidence_header=header,
        **item_data,
    )


def evaluate_rules(quote: QuoteDetails, purchase_items: dict[str, PurchaseItem]) -> tuple[Finding, ...]:
    """Apply company-rules.md as auditable deterministic checks.

    Reject overrides Review. Missing inputs never silently become an approval.
    """
    findings: list[Finding] = []

    def flag(rule: str, severity: Severity, reason: str, evidence: tuple[Evidence, ...]) -> None:
        findings.append(Finding(rule=rule, severity=severity, reason=reason, evidence=evidence))

    expected_prs = {item.pr_number for item in purchase_items.values()}
    if not quote.supplier or not quote.quotation_number or quote.pr_number not in expected_prs or len(expected_prs) != 1:
        flag("Document identity", "Needs a person to check", "Supplier, quotation ID, or purchase-request reference is missing/mismatched.", quote.evidence_header)

    item = purchase_items.get(quote.item_code or "")
    if item is None or quote.quantity is None or quote.unit_price is None or quote.line_amount is None:
        flag("Item extraction", "Needs a person to check", "Item code, quantity, unit price or line amount is missing/unknown.", quote.item_evidence or quote.evidence_header)
    else:
        if quote.description != item.description or not quote.unit or quote.unit.lower() != item.unit.lower():
            flag("Item match", "Needs a person to check", "Item description/unit differs from the purchase request.", quote.item_evidence)
        if quote.pr_number != item.pr_number:
            flag("Purchase request mismatch", "Needs a person to check", "Quoted PR reference does not match the requested item.", quote.evidence_header)
        maximum = item.maximum_unit_price_bdt
        if quote.unit_price > maximum*D("1.03"):
            flag("R1 Price >3%", "Reject", f"Unit price BDT {quote.unit_price:.2f} exceeds the >3% rejection threshold (BDT {maximum*D('1.03'):.2f}).", quote.item_evidence)
        elif quote.unit_price > maximum:
            flag("H1 Price up to 3%", "Needs a person to check", f"Unit price BDT {quote.unit_price} exceeds purchase-request maximum BDT {maximum} (by no more than 3%).", quote.item_evidence)
        if abs(D(quote.quantity) - D(item.requested_quantity)) > D(item.requested_quantity)*D("0.05"):
            flag("H2 Quantity", "Needs a person to check", f"Quoted {quote.quantity:,} units, requested {item.requested_quantity:,}; difference exceeds 5%.", quote.item_evidence)
        expected_line = D(quote.quantity)*quote.unit_price
        if quote.line_amount != expected_line:
            flag("H6 Line arithmetic", "Needs a person to check", f"Quoted line amount BDT {quote.line_amount} but quantity × unit price = BDT {expected_line}.", quote.item_evidence)

    payment_ev = _ev(quote.clauses["Payment"].quote) if "Payment" in quote.clauses else quote.evidence_header
    if quote.advance_is_conflicting:
        flag("H3 Conflicting advance terms", "Needs a person to check", "Multiple inconsistent advance-payment percentages appear in the contract.", payment_ev)
    if quote.advance_pct is None:
        flag("Payment advance unknown", "Needs a person to check", "Advance-payment percentage is not explicitly stated.", payment_ev)
    elif quote.advance_pct > D("20"):
        flag("R2 Advance >20%", "Reject", f"Advance payment {quote.advance_pct}% exceeds 20%.", payment_ev)
    if quote.payment_is_ambiguous or quote.payment_days is None:
        flag("H3 Payment terms unclear", "Needs a person to check", "Final payment due date is not a clear single number of days after delivery.", payment_ev)
    elif quote.payment_days < 30 or quote.payment_days > 60:
        flag("H3 Payment outside 30–60d", "Needs a person to check", f"Payment is due {quote.payment_days} days after delivery, outside 30–60 days.", payment_ev)

    if "Delay" not in quote.clauses:
        neighbor = tuple(quote.clauses[name] for name in ("Delivery", "Validity") if name in quote.clauses)
        flag("R3 Penalty clause missing", "Reject", "No late-delivery penalty clause found in the contract terms.", neighbor or quote.evidence_header)
    elif quote.penalty_is_waived:
        flag("R3 Penalty explicitly absent", "Reject", "Contract explicitly waives or excludes a late-delivery penalty.", _ev(quote.clauses["Delay"].quote))
    elif quote.penalty_pct is None:
        flag("R3 Penalty unverified", "Needs a person to check", "Delay clause exists but a numeric penalty rate cannot be verified.", _ev(quote.clauses["Delay"].quote))
    else:
        if quote.penalty_is_conflicting:
            flag("Penalty rate conflicting", "Needs a person to check", "Multiple inconsistent penalty rates appear in the delay clause.", _ev(quote.clauses["Delay"].quote))
        if not quote.penalty_is_weekly:
            flag("Penalty frequency unverified", "Needs a person to check", "Penalty is not clearly stated per week of delay.", _ev(quote.clauses["Delay"].quote))
        if quote.penalty_pct < D("0.5"):
            flag("Penalty below minimum", "Needs a person to check", f"Penalty {quote.penalty_pct}% is below the required 0.5% per week; a person must confirm the contractual remedy.", _ev(quote.clauses["Delay"].quote))

    tin_status = _registration_status(quote.tin)
    bin_status = _registration_status(quote.bin)
    if "missing" in (tin_status, bin_status):
        flag("R4 Missing TIN/BIN", "Reject", "Supplier TIN or BIN not provided.", quote.registration_evidence or quote.evidence_header)
    elif "unclear" in (tin_status, bin_status):
        flag("TIN/BIN format unverified", "Needs a person to check", "Supplier TIN/BIN contains a non-standard value; verify with a person.", quote.registration_evidence or quote.evidence_header)

    delivery_ev = _ev(quote.clauses["Delivery"].quote) if "Delivery" in quote.clauses else quote.evidence_header
    if quote.delivery_days is None:
        flag("Delivery date unknown", "Needs a person to check", "Delivery period after the purchase order could not be verified.", delivery_ev)
    if quote.delivery_is_conflicting:
        flag("Delivery terms conflicting", "Needs a person to check", "Conflicting delivery deadlines or lower bounds appear in the contract; no automatic approval.", delivery_ev)
    if quote.delivery_days is not None and quote.delivery_days > 45:
        flag("R5 Delivery >45d", "Reject", f"Delivery promised in {quote.delivery_days} days, later than 45 days after PO.", delivery_ev)
    elif quote.delivery_days is not None and 31 <= quote.delivery_days <= 45:
        flag("H4 Delivery 31–45d", "Needs a person to check", f"Delivery promised in {quote.delivery_days} days.", delivery_ev)

    if not quote.vat_separately_shown or quote.vat_amount is None or quote.subtotal is None:
        flag("H5 VAT not separately stated", "Needs a person to check", "Separate 15% VAT amount and subtotal are not shown.", quote.totals_evidence or quote.item_evidence)
    else:
        expected_vat = (quote.subtotal*D("0.15")).quantize(D("0.01"))
        if quote.vat_amount != expected_vat:
            flag("H6 VAT arithmetic", "Needs a person to check", f"VAT is BDT {quote.vat_amount}, expected 15% of subtotal = BDT {expected_vat}.", quote.totals_evidence)

    if quote.subtotal is not None and quote.line_amount is not None and quote.subtotal != quote.line_amount:
        flag("H6 Subtotal arithmetic", "Needs a person to check", f"Subtotal BDT {quote.subtotal} differs from line amount BDT {quote.line_amount}.", quote.totals_evidence + quote.item_evidence)
    if quote.total is None:
        flag("H6 Missing total", "Needs a person to check", "Document total is missing or unreadable.", quote.totals_evidence or quote.item_evidence)
    elif quote.subtotal is not None and quote.vat_amount is not None and quote.total != quote.subtotal + quote.vat_amount:
        flag("H6 Total arithmetic", "Needs a person to check", f"Total BDT {quote.total} does not match subtotal + VAT = BDT {quote.subtotal+quote.vat_amount}.", quote.totals_evidence)

    validity_ev = _ev(quote.clauses["Validity"].quote) if "Validity" in quote.clauses else quote.evidence_header
    if quote.validity_days is None:
        flag("Quotation validity unknown", "Needs a person to check", "Quotation validity is not clearly specified.", validity_ev)
    elif quote.validity_days < 30:
        flag("H7 Quotation validity <30d", "Needs a person to check", f"Quotation validity is {quote.validity_days} days, less than 30.", validity_ev)

    return tuple(findings)


def decide(filename: str, quote: QuoteDetails | None, findings: tuple[Finding, ...], error: str | None = None, ai_review: AIReview | None = None) -> Assessment:
    decision: Literal["Approve", "Reject", "Needs a person to check"]
    if error:
        decision = "Needs a person to check"
    elif any(f.severity == "Reject" for f in findings):
        decision = "Reject"
    elif findings or quote is None:
        decision = "Needs a person to check"
    else:
        decision = "Approve"
    return Assessment(filename, decision, quote, findings, checks_performed=11, error=error, ai_review=ai_review)
