"""Reference-label regression and explicit edge-case tests for Phase 2."""
from dataclasses import replace
from decimal import Decimal

import pytest

from docuguard.analysis import decide, evaluate_rules, extract_quote
from docuguard.config import sample_pdfs
from docuguard.data_loader import load_purchase_request
from docuguard.pdf_reader import read_pdf

REF = ["Approve", "Approve", "Reject", "Needs a person to check", "Reject", "Reject", "Needs a person to check", "Reject", "Needs a person to check", "Reject"]


def test_all_reference_decisions_from_real_supplied_files():
    purchase = load_purchase_request()
    for path, expected in zip(sample_pdfs(), REF):
        q = extract_quote(read_pdf(path))
        findings = evaluate_rules(q, purchase)
        actual = decide(path.name, q, findings)
        assert actual.decision == expected, (path.name, actual.decision, findings)


def test_supplier_09_detects_both_math_and_ambiguity():
    q = extract_quote(read_pdf(sample_pdfs()[8]))
    found = evaluate_rules(q, load_purchase_request())
    assert any(f.rule == "H6 Line arithmetic" for f in found)
    assert any(f.rule == "H3 Payment terms unclear" for f in found)
    assert all(f.evidence for f in found)


def test_missing_penalty_rejected_even_if_other_terms_pass():
    q = extract_quote(read_pdf(sample_pdfs()[5]))
    found = evaluate_rules(q, load_purchase_request())
    assert any(f.rule == "R3 Penalty clause missing" for f in found)


def test_no_vat_and_delivery_60_both_detected():
    q = extract_quote(read_pdf(sample_pdfs()[9]))
    found = evaluate_rules(q, load_purchase_request())
    assert any(f.rule == "H5 VAT not separately stated" for f in found)
    assert any(f.rule == "R5 Delivery >45d" for f in found)


def test_no_advance_interpreted_zero_not_missing():
    q = extract_quote(read_pdf(sample_pdfs()[1]))
    assert q.advance_pct == Decimal("0")


def test_unknown_delivery_never_gets_approved():
    q = extract_quote(read_pdf(sample_pdfs()[0]))
    modified = replace(q, delivery_days=None)
    result = decide("test.pdf", modified, evaluate_rules(modified, load_purchase_request()))
    assert result.decision == "Needs a person to check"


def test_boundary_3_percent_price_does_not_reject():
    q = extract_quote(read_pdf(sample_pdfs()[0]))
    # A: maximum 480, exactly 3% above is 494.40
    modified = replace(q, unit_price=Decimal("494.40"), line_amount=Decimal("5932800"), subtotal=Decimal("5932800"), vat_amount=Decimal("889920"), total=Decimal("6822720"))
    findings = evaluate_rules(modified, load_purchase_request())
    assert any(f.rule == "H1 Price up to 3%" for f in findings)
    assert not any(f.rule == "R1 Price >3%" for f in findings)


def test_reject_precedes_review():
    q = extract_quote(read_pdf(sample_pdfs()[9]))
    r = decide("test.pdf", q, evaluate_rules(q, load_purchase_request()))
    assert r.decision == "Reject"
    assert any(f.severity == "Needs a person to check" for f in r.findings)


def test_missing_quantity_cannot_be_approved():
    q = extract_quote(read_pdf(sample_pdfs()[0]))
    modified = replace(q, quantity=None)
    r = decide("test.pdf", modified, evaluate_rules(modified, load_purchase_request()))
    assert r.decision == "Needs a person to check"


def test_graph_integration_on_supplied_files_if_available():
    pytest.importorskip("langgraph")
    from docuguard.workflow import analyze_sample
    for path, expected in zip(sample_pdfs(), REF):
        assert analyze_sample(path).decision == expected


def test_every_reported_quote_is_a_literal_pdf_excerpt():
    for path in sample_pdfs():
        doc = read_pdf(path)
        q = extract_quote(doc)
        for f in evaluate_rules(q, load_purchase_request()):
            for excerpt in f.evidence:
                assert excerpt.page == 1
                assert excerpt.quote in doc.pages[0].text, (path, f.rule)


def test_reject_when_price_just_over_3_percent():
    q = extract_quote(read_pdf(sample_pdfs()[0]))
    modified = replace(q, unit_price=Decimal("494.41"))
    f = evaluate_rules(modified, load_purchase_request())
    assert any(x.rule == "R1 Price >3%" for x in f)
