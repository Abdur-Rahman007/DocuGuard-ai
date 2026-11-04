"""Opt-in local model checks; no external/local LLM needed for unit tests."""
import json
from decimal import Decimal

import pytest

from docuguard.analysis import decide, evaluate_rules, extract_quote
from docuguard.config import sample_pdfs
from docuguard.data_loader import load_purchase_request
from docuguard.local_ai import _validated_model_name, ai_review_findings, review_with_ollama
from docuguard.pdf_reader import read_pdf


def model_output(*observations):
    return json.dumps({"observations": list(observations)})


def observation(field, quote, value, needs_review, explanation="Check contract wording"):
    return {"field": field, "evidence_quote": quote, "value": value,
            "needs_review": needs_review, "explanation": explanation}


def get_case(index):
    doc = read_pdf(sample_pdfs()[index])
    return doc, extract_quote(doc)


def test_local_ai_quotes_must_be_verbatim_and_page_grounded():
    doc, q = get_case(8)
    evidence = q.clauses["Payment"].quote
    review = review_with_ollama(doc, q, raw_chat=lambda *_: model_output(
        observation("payment_days", evidence, None, True, "An interval is not a fixed day.")))
    assert review.status == "completed"
    assert review.ungrounded_count == 0
    assert len(review.observations) == 1
    assert review.observations[0].evidence.quote == evidence
    assert review.observations[0].evidence.page == 1
    findings = ai_review_findings(review)
    assert len(findings) == 1
    assert findings[0].severity == "Needs a person to check"


def test_hallucinated_quote_discarded_without_downgrading_supplier():
    doc, q = get_case(0)
    review = review_with_ollama(doc, q, raw_chat=lambda *_: model_output(
        observation("delivery_days", "Magic approval from procurement", 25, False)))
    assert review.ungrounded_count == 1
    assert len(review.observations) == 0
    assert ai_review_findings(review) == ()
    assert decide("supplier-pack-01.pdf", q, evaluate_rules(q, load_purchase_request()) + ai_review_findings(review)).decision == "Approve"


def test_wrong_numeric_value_cannot_hide_without_literal_source_number():
    doc, q = get_case(0)
    evidence = q.clauses["Delivery"].quote
    review = review_with_ollama(doc, q, raw_chat=lambda *_: model_output(
        observation("delivery_days", evidence, 999, False)))
    assert review.ungrounded_count == 1


def test_section_heading_number_does_not_count_as_delivery_days():
    doc, q = get_case(0)
    evidence = q.clauses["Delivery"].quote
    # "2. Delivery" is a heading, NOT "2 days". Do not invent a mismatch.
    review = review_with_ollama(doc, q, raw_chat=lambda *_: model_output(
        observation("delivery_days", evidence, 2, False)))
    assert review.ungrounded_count == 1
    assert review.observations == ()
    assert ai_review_findings(review) == ()
    result = decide("supplier-pack-01.pdf", q, evaluate_rules(q, load_purchase_request()) + ai_review_findings(review), ai_review=review)
    assert result.decision == "Approve"


def test_model_false_ambiguity_for_explicit_24_days_does_not_escalate():
    doc, q = get_case(0)
    assert q.delivery_days == 24
    review = review_with_ollama(doc, q, raw_chat=lambda *_: model_output(
        observation("delivery_days", q.clauses["Delivery"].quote, None, True,
                    "Incorrect model statement that 24 days is unknown"),
        observation("penalty_pct", q.clauses["Delay"].quote, 1, False)))
    assert review.status == "completed"
    assert review.model_only_count == 1
    assert review.ungrounded_count == 0
    assert len(review.observations) == 2
    assert review.observations[0].model_flagged_review is True
    assert review.observations[0].needs_review is False
    assert review.observations[0].parser_value == Decimal(24)
    assert ai_review_findings(review) == ()
    result = decide("supplier-pack-01.pdf", q, evaluate_rules(q, load_purchase_request()) + ai_review_findings(review), ai_review=review)
    assert result.decision == "Approve"


def test_real_ambiguity_in_pdf_triggers_a_human_review():
    from docuguard.pdf_reader import DocumentText, PageText
    doc, original = get_case(0)
    old = original.clauses["Delivery"].quote
    new = "2. Delivery. Delivery within 24 days or within 42 days of receiving the purchase order."
    edited = DocumentText(doc.filename, (PageText(1, doc.full_text.replace(old, new)),))
    quote = extract_quote(edited)
    assert quote.delivery_days == 24  # parser catches only first, AI corroborates conflicting second
    review = review_with_ollama(edited, quote, raw_chat=lambda *_: model_output(
        observation("delivery_days", new, None, True, "Two conflicting delivery periods")))
    assert len(review.observations) == 1
    assert review.observations[0].needs_review
    assert len(ai_review_findings(review)) == 1
    result = decide("fictional-altered.pdf", quote, evaluate_rules(quote, load_purchase_request()) + ai_review_findings(review), ai_review=review)
    assert result.decision == "Needs a person to check"


def test_reject_overrides_ai_human_review():
    doc, q = get_case(9)
    evidence = q.clauses["Payment"].quote
    review = review_with_ollama(doc, q, raw_chat=lambda *_: model_output(
        observation("payment_days", evidence, None, True)))
    combined = evaluate_rules(q, load_purchase_request()) + ai_review_findings(review)
    result = decide("supplier-pack-10.pdf", q, combined, ai_review=review)
    assert result.decision == "Reject"


def test_invalid_json_is_fail_closed():
    doc, q = get_case(0)
    review = review_with_ollama(doc, q, raw_chat=lambda *_: "this is not JSON")
    assert review.status == "failed"
    assert ai_review_findings(review) == ()
    assert decide("supplier-pack-01.pdf", q, evaluate_rules(q, load_purchase_request()) + ai_review_findings(review)).decision == "Approve"


def test_local_only_prevent_hosted_cloud_model():
    assert _validated_model_name("qwen2.5:1.5b") == "qwen2.5:1.5b"
    with pytest.raises(Exception):
        _validated_model_name("gemma4:cloud")
    with pytest.raises(Exception):
        _validated_model_name("https://example.com")


def test_baseline_not_using_ai_by_default():
    pytest.importorskip("langgraph")
    from docuguard.workflow import analyze_sample
    r = analyze_sample(sample_pdfs()[0])
    assert r.ai_review is None
    assert r.decision == "Approve"


def test_graph_optin_uses_ai_and_keeps_reject_priority(monkeypatch):
    """A *real documentary* ambiguity may add review, but never override Reject.

    In the unmodified supplier 10 PDF, payment within 45 days is clear.
    The old test incorrectly expected that a model-only uncertainty would
    become an AI finding. This test inserts a conflicting payment clause in
    memory only, preserving the original sample PDF on disk.
    """
    pytest.importorskip("langgraph")
    from docuguard import workflow
    from docuguard.pdf_reader import DocumentText, PageText

    original_read_pdf = workflow.read_pdf
    original_phrase = "Payment within 45 days of delivery."
    conflicting_phrase = (
        "Payment within 45 days of delivery or within 90 days of delivery, "
        "to be agreed."
    )

    def read_synthetic_ambiguous_pdf(path):
        doc = original_read_pdf(path)
        assert original_phrase in doc.full_text  # verify fixture was not changed
        return DocumentText(
            doc.filename,
            tuple(PageText(page.page_number,
                           page.text.replace(original_phrase, conflicting_phrase))
                  for page in doc.pages),
        )

    def mock_ai(doc, quote, model, timeout):
        evidence = quote.clauses["Payment"].quote
        return review_with_ollama(doc, quote, model=model, raw_chat=lambda *_: model_output(
            observation("payment_days", evidence, None, True,
                        "Two conflicting payment periods are stated.")))

    monkeypatch.setattr(workflow, "read_pdf", read_synthetic_ambiguous_pdf)
    monkeypatch.setattr(workflow, "review_with_ollama", mock_ai)
    result = workflow.analyze_sample(sample_pdfs()[9], use_ai=True)
    assert result.ai_review.status == "completed"
    assert result.ai_review.observations[0].needs_review is True
    assert any(f.rule.startswith("AI") for f in result.findings)
    assert result.decision == "Reject"  # reject always wins
