"""Tests verifying the input data and fail-safe extraction behavior."""
import fitz
import pytest

from docuguard.config import COMPANY_RULES_MD, PURCHASE_REQUEST_CSV, sample_pdfs
from docuguard.data_loader import load_company_rules, load_purchase_request
from docuguard.pdf_reader import PDFExtractionError, read_pdf


def test_all_ten_supplier_pdfs_present():
    assert len(sample_pdfs()) == 10


def test_all_ten_supplier_pdfs_have_selectable_text():
    for path in sample_pdfs():
        result = read_pdf(path)
        assert result.page_count == 1
        assert result.character_count >= 500
        assert "QUOTATION" in result.full_text


def test_page_number_and_supplier_name():
    first = read_pdf(sample_pdfs()[0])
    assert first.pages[0].page_number == 1
    assert "Padma Textile Mills Ltd" in first.pages[0].text


def test_five_purchase_request_items_and_exact_value():
    items = load_purchase_request(PURCHASE_REQUEST_CSV)
    assert set(items) == {"A", "B", "C", "D", "E"}
    assert items["D"].requested_quantity == 50000
    assert str(items["D"].maximum_unit_price_bdt) == "6.50"


def test_company_rules_readable():
    rules = load_company_rules(COMPANY_RULES_MD)
    assert "## Reject" in rules
    assert "## Needs a person to check" in rules
    assert "## Approve" in rules


def test_missing_pdf_does_not_get_silently_ignored(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_pdf(tmp_path / "missing.pdf")


def test_non_pdf_is_rejected(tmp_path):
    fake = tmp_path / "sample.txt"
    fake.write_text("not a PDF", encoding="utf-8")
    with pytest.raises(PDFExtractionError, match="Only PDF"):
        read_pdf(fake)


def test_image_only_or_empty_pdf_requires_review(tmp_path):
    blank_pdf = tmp_path / "blank.pdf"
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(blank_pdf)
    with pytest.raises(PDFExtractionError, match="No selectable text"):
        read_pdf(blank_pdf)
