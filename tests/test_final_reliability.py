"""Synthetic in-memory mutations; original BIAI assessment PDFs remain unchanged."""
from dataclasses import replace
from decimal import Decimal

import pytest

from docuguard.analysis import approval_evidence, decide, evaluate_rules, extract_quote
from docuguard.config import sample_pdfs
from docuguard.data_loader import load_purchase_request
from docuguard.pdf_reader import DocumentText, PageText, read_pdf


def mutated_quote(old: str, new: str, sample_index: int = 0):
    path = sample_pdfs()[sample_index]
    original = read_pdf(path)
    assert old in original.full_text, f"Fixture text not found: {old}"
    changed = DocumentText(original.filename, tuple(
        PageText(p.page_number, p.text.replace(old, new)) for p in original.pages
    ))
    return changed, extract_quote(changed)


def checked(doc, quote):
    findings = evaluate_rules(quote, load_purchase_request())
    result = decide(doc.filename, quote, findings)
    for finding in findings:
        for evidence in finding.evidence:
            assert evidence.quote in doc.pages[evidence.page - 1].text
    return result


@pytest.mark.parametrize("replacement", [
    "Supplier TIN: N/A BIN: N/A",
    "Supplier TIN: pending BIN: pending",
    "Supplier TIN: not provided BIN: not provided",
])
def test_registration_placeholders_cannot_approve(replacement):
    doc, q = mutated_quote("Supplier TIN: 101458013391 BIN: 000170141-0101", replacement)
    result = checked(doc, q)
    assert result.decision == "Reject"
    assert any(x.rule == "R4 Missing TIN/BIN" for x in result.findings)


def test_odd_format_id_escalates_instead_of_guessing():
    doc, q = mutated_quote("Supplier TIN: 101458013391 BIN: 000170141-0101",
                            "Supplier TIN: ABCD BIN: 000170141-0101")
    assert checked(doc, q).decision == "Needs a person to check"


def test_conflicting_advance_10_and_40_rejects():
    doc, q = mutated_quote("10% advance payable with the purchase order.",
                            "10% advance payable with the purchase order; 40% advance before shipping.")
    result = checked(doc, q)
    assert q.advance_is_conflicting and q.advance_pct == Decimal("40")
    assert result.decision == "Reject"
    assert {f.rule for f in result.findings} >= {"R2 Advance >20%", "H3 Conflicting advance terms"}


def test_conflicting_advance_under_limit_needs_review():
    doc, q = mutated_quote("10% advance payable with the purchase order.",
                            "10% advance payable with the purchase order; 15% advance before shipping.")
    assert checked(doc, q).decision == "Needs a person to check"


def test_no_advance_and_positive_advance_conflict():
    doc, q = mutated_quote("10% advance payable with the purchase order.",
                            "No advance payment required. 10% advance payable with the purchase order.")
    assert checked(doc, q).decision == "Needs a person to check"


@pytest.mark.parametrize("replacement", [
    "2. Delivery. Delivery within 24 days of receiving the purchase order, but cannot occur before 60 days.",
    "2. Delivery. Delivery within 24 days or within 42 days of receiving the purchase order.",
])
def test_conflicting_delivery_no_longer_approves(replacement):
    doc, q = mutated_quote("2. Delivery. Delivery within 24 days of receiving the purchase order.", replacement)
    result = checked(doc, q)
    assert q.delivery_is_conflicting
    assert result.decision == "Needs a person to check"
    assert any(f.rule == "Delivery terms conflicting" for f in result.findings)


def test_clear_delivery_stays_approved():
    doc = read_pdf(sample_pdfs()[0])
    assert checked(doc, extract_quote(doc)).decision == "Approve"


def test_explicitly_waived_penalty_rejects():
    doc, q = mutated_quote("3. Delay. Late delivery penalty: 1% of order value for each full week of delay.",
                            "3. Delay. No late-delivery penalty will apply.")
    result = checked(doc, q)
    assert result.decision == "Reject"
    assert any(f.rule == "R3 Penalty explicitly absent" for f in result.findings)


@pytest.mark.parametrize("replacement", [
    "3. Delay. Late delivery penalty: 0.5% of order value per month of delay.",
    "3. Delay. Late delivery penalty: 0.25% of order value per week of delay.",
    "3. Delay. Late delivery penalty: 1% of order value for each day of delay.",
])
def test_invalid_penalty_terms_cannot_approve(replacement):
    doc, q = mutated_quote("3. Delay. Late delivery penalty: 1% of order value for each full week of delay.", replacement)
    assert checked(doc, q).decision == "Needs a person to check"


def test_payment_terms_disagreement_needs_review():
    doc, q = mutated_quote("Balance payable within 45 days after delivery and",
                            "Balance payable within 45 days after delivery or within 90 days after delivery and")
    assert q.payment_is_ambiguous
    assert checked(doc, q).decision == "Needs a person to check"


def test_pr_reference_comes_from_csv_not_constant():
    doc = read_pdf(sample_pdfs()[0])
    q = extract_quote(doc)
    items = load_purchase_request()
    updated = {k: replace(v, pr_number="PR-NEW-001") for k, v in items.items()}
    assert decide(doc.filename, replace(q, pr_number="PR-NEW-001"),
                  evaluate_rules(replace(q, pr_number="PR-NEW-001"), updated)).decision == "Approve"
    assert any(f.rule == "Document identity" for f in evaluate_rules(q, updated))


def test_every_approved_supplier_has_exact_source_support():
    for path in sample_pdfs()[:2]:
        doc = read_pdf(path)
        q = extract_quote(doc)
        assert checked(doc, q).decision == "Approve"
        excerpts = approval_evidence(q)
        assert len(excerpts) >= 7
        assert all(evidence.quote in doc.pages[evidence.page - 1].text for _, evidence in excerpts)
        assert {label for label, _ in excerpts} >= {"Payment terms", "Delivery commitment", "Late-delivery penalty", "Supplier TIN and BIN"}


def test_currency_threshold_has_two_decimals():
    doc = read_pdf(sample_pdfs()[2])
    q = extract_quote(doc)
    findings = evaluate_rules(q, load_purchase_request())
    price = next(f for f in findings if f.rule == "R1 Price >3%")
    assert "216.30" in price.reason
    assert "216.3000" not in price.reason


def test_summary_csv_includes_evidence_for_approved_and_rejected_files():
    import csv
    import io
    from docuguard.reporting import DECISION_COLUMNS, decision_rows, csv_bytes
    paths = sample_pdfs()
    purchase = load_purchase_request()
    results = [checked(path_doc := read_pdf(path), extract_quote(path_doc)) for path in paths]
    rows = decision_rows(results)
    assert len(rows) == 10
    assert rows[0]["Supporting PDF evidence"]
    assert "Payment" in rows[0]["Supporting PDF evidence"]
    assert "p1:" in rows[9]["Supporting PDF evidence"]
    csv_output = csv_bytes(rows, DECISION_COLUMNS)
    parsed = list(csv.DictReader(io.StringIO(csv_output.decode("utf-8-sig"))))
    assert len(parsed) == 10
    assert parsed[0]["Decision"] == "Approve"
    assert "Supporting PDF evidence" in parsed[0]


def test_detailed_audit_csv_has_all_issue_rows_and_verified_approvals():
    from docuguard.reporting import audit_rows
    results = []
    for path in sample_pdfs():
        doc = read_pdf(path)
        results.append(checked(doc, extract_quote(doc)))
    rows = audit_rows(results)
    assert len([r for r in rows if r["PDF"] == "supplier-pack-09.pdf"]) >= 2
    assert len([r for r in rows if r["PDF"] == "supplier-pack-10.pdf"]) >= 2
    assert any(r["Rule or verification"] == "Supplier TIN and BIN" and r["Decision"] == "Approve" for r in rows)
    assert all(r["Source page"] == 1 and r["Exact PDF excerpt"] for r in rows)
